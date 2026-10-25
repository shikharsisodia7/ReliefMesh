"""Operations notification service: application events -> idempotent external deliveries.

Each event fans out to deliveries (one per channel and recipient/target). A delivery's id is
a hash of ``event_type | mission | subject | version | channel | target``, so a retried
endpoint or a duplicated event cannot create a second email, Slack post, or calendar event.
Deliveries run in the background with backoff; every outcome is persisted with an explicit
status. A provider failure is recorded and retried; it never propagates into procurement.

Statuses: PENDING, SENDING, RETRYING, SENT, FAILED, NOT_CONFIGURED, TEST (EMAIL_MODE=test),
DISABLED (EMAIL_MODE=disabled), SUPPRESSED (recipient allowlist), SKIPPED (superseded).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from pymongo.errors import DuplicateKeyError

from .. import documents
from ..integrations import connections, google_auth, google_calendar, google_drive, slack
from ..integrations.connections import IntegrationError
from ..integrations.gmail import OutgoingEmail
from . import events, templates

if TYPE_CHECKING:
    from ..core import Services

logger = logging.getLogger("reliefmesh.operations")
DONE = {"SENT", "TEST", "DISABLED", "SUPPRESSED", "SKIPPED"}
RUNNABLE = {"PENDING", "RETRYING"}
EMAIL_STATUS = {"sent": "SENT", "test": "TEST", "disabled": "DISABLED", "suppressed": "SUPPRESSED",
                "not_configured": "NOT_CONFIGURED"}
APPROVER_ROLES = {"admin", "approver"}
COORDINATOR_ROLES = {"admin", "coordinator"}


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:40]


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class OperationsService:
    def __init__(self, services: Services) -> None:
        self.services = services
        self.slot_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.folder_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.calendars: dict[str, str] = {}

    @property
    def store(self):
        return self.services.store

    @property
    def settings(self):
        return self.services.settings

    def mission_url(self, mission: dict[str, Any]) -> str:
        return f"{self.settings.frontend_origin.rstrip('/')}/missions/{mission['id']}"

    # ------------------------------------------------------------------ emit
    async def emit(self, event_type: str, mission: dict[str, Any], *, subject_id: str, version: Any = None,
                   data: dict[str, Any] | None = None) -> dict[str, Any] | None:
        try:
            return await self._emit(event_type, mission, subject_id, version, data or {})
        except Exception:  # an integration bug must never break the procurement call that emitted
            logger.exception("operations event %s for mission %s could not be routed", event_type, mission.get("id"))
            return None

    async def _emit(self, event_type: str, mission: dict[str, Any], subject_id: str, version: Any,
                    data: dict[str, Any]) -> dict[str, Any]:
        key = f"{event_type}|{mission['id']}|{subject_id}|{version}"
        event = {"id": digest(key), "key": key, "type": event_type, "organization_id": mission["organization_id"],
                 "mission_id": mission["id"], "subject_id": subject_id, "version": version, "data": data,
                 "created_at": now_iso(), "delivery_ids": []}
        if not await self._insert_once("ops_events", event):
            return await self.store.get("ops_events", event["id"]) or event  # duplicate application event
        specs = await self.route(event, mission)
        for spec in specs:
            delivery = self._delivery(event, spec)
            if await self._insert_once("ops_deliveries", delivery):
                event["delivery_ids"].append(delivery["id"])
                self.services.schedule(self.attempt(delivery["id"]))
        await self.store.replace("ops_events", event["id"], event)
        return event

    async def _insert_once(self, collection: str, document: dict[str, Any]) -> bool:
        try:
            await self.store.insert(collection, document)
            return True
        except (DuplicateKeyError, ValueError):
            return False

    def _delivery(self, event: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
        idempotency_key = f"{event['key']}|{spec['channel']}|{spec['target']}"
        return {
            "id": digest(idempotency_key), "idempotency_key": idempotency_key, "event_id": event["id"],
            "event_type": event["type"], "organization_id": event["organization_id"],
            "mission_id": event["mission_id"], "subject_id": event["subject_id"], "version": event["version"],
            "channel": spec["channel"], "target": spec["target"], "summary": spec.get("summary"),
            "payload": spec["payload"], "status": "PENDING", "attempts": 0,
            "max_attempts": self.settings.ops_delivery_max_attempts, "sequence": time.time_ns(),
            "provider": None, "provider_id": None, "provider_url": None, "last_error": None,
            "next_retry_at": None, "sent_at": None, "history": [], "created_at": now_iso(), "updated_at": now_iso(),
        }

    # ------------------------------------------------------------------ routing
    async def members(self, organization_id: str, roles: set[str] | None = None) -> list[dict[str, Any]]:
        rows = []
        for membership in await self.store.find("memberships", organization_id=organization_id):
            if roles and membership["role"] not in roles:
                continue
            user = await self.store.get("users", membership["user_id"])
            if user and user.get("email") and user.get("active", True):
                rows.append({"user_id": user["id"], "email": user["email"], "role": membership["role"]})
        return rows

    async def approver_emails(self, mission: dict[str, Any]) -> list[str]:
        organization = await self.store.get("organizations", mission["organization_id"]) or {}
        approvers = await self.members(mission["organization_id"], APPROVER_ROLES)
        # Segregation of duties: the requester cannot approve, so they are not asked to (demo orgs excepted).
        eligible = [m for m in approvers if organization.get("is_demo") or m["user_id"] != mission.get("created_by")]
        return sorted({m["email"] for m in eligible})

    def _emails(self, recipients: list[str], subject: str, html: str, text: str, kind: str,
                missing: str) -> list[dict[str, Any]]:
        if not recipients:
            return [{"channel": "gmail", "target": "(no recipient)", "summary": subject,
                     "payload": {"unroutable": missing, "subject": subject}}]
        return [{"channel": "gmail", "target": to, "summary": subject,
                 "payload": {"to": to, "subject": subject, "html": html, "text": text, "kind": kind}}
                for to in recipients]

    def _slack(self, text: str, blocks: list[dict[str, Any]], supersede: list[int] | None = None) -> dict[str, Any]:
        return {"channel": "slack", "target": "operations-channel", "summary": text,
                "payload": {"text": text, "blocks": blocks, "supersede_versions": supersede or []}}

    def _calendar(self, mission: dict[str, Any], slot: str, op: str, body: dict[str, Any] | None,
                  summary: str) -> dict[str, Any]:
        return {"channel": "calendar", "target": slot, "summary": summary,
                "payload": {"op": op, "slot": slot, "body": body,
                            "event_id": google_calendar.event_id(mission["organization_id"], mission["id"], slot)}}

    def _drive(self, doc: str, filename: str, render: dict[str, Any]) -> dict[str, Any]:
        return {"channel": "drive", "target": doc, "summary": f"Archive {filename}",
                "payload": {"doc": doc, "filename": filename, "render": render}}

    async def route(self, event: dict[str, Any], mission: dict[str, Any]) -> list[dict[str, Any]]:
        kind, data, url = event["type"], event["data"], self.mission_url(mission)
        specs: list[dict[str, Any]] = []
        if kind in {events.MISSION_CREATED, events.MISSION_UPDATED}:
            body = templates.calendar_deadline(mission, url)
            specs.append(self._calendar(mission, "deadline", "upsert", body, body["summary"]))
            if kind == events.MISSION_UPDATED:
                specs += await self._stale_approval_specs(mission, data.get("stale_versions") or [],
                                                          data.get("reason"), url)
                specs.append(self._slack(*templates.slack_deadline_change(mission, data, url)))
        elif kind == events.MISSION_CANCELLED:
            specs.append(self._calendar(mission, "deadline", "cancel", None, "Cancel delivery deadline"))
            specs.append(self._calendar(mission, "approval", "cancel", None, "Cancel approval window"))
            open_orders = set(data.get("open_orders") or [])
            for order in await self.store.find("purchase_orders", mission_id=mission["id"]):
                # An issued order is still a supplier commitment, so its delivery reminder stays.
                if order["po_number"] not in open_orders:
                    specs.append(self._calendar(mission, f"eta:{order['id']}", "cancel", None,
                                                f"Cancel ETA {order['po_number']}"))
            specs.append(self._slack(*templates.slack_mission_cancelled(mission, data, url)))
        elif kind in {events.APPROVAL_REQUIRED, events.PLAN_REPLANNED}:
            specs += await self._plan_specs(kind, mission, data, url)
        elif kind == events.SUPPLIER_DISRUPTED:
            specs += await self._disruption_specs(mission, data, url)
        elif kind == events.PLAN_APPROVED:
            plan = await self.store.get("plans", data["plan_id"])
            if plan:
                due = templates.approval_due(mission, await self.store.find("quotes", mission_id=mission["id"]), plan)
                body = templates.calendar_approval(mission, plan, due, url, "approved")
                specs.append(self._calendar(mission, "approval", "upsert", body, body["summary"]))
                specs.append(self._drive(f"plan:v{plan['version']}", f"Plan-V{plan['version']}.pdf",
                                         {"kind": "plan", "plan_id": plan["id"], "approval_id": data.get("approval_id")}))
        elif kind == events.PURCHASE_ORDER_SENT:
            order = await self.store.get("purchase_orders", data["order_id"])
            if order:
                supplier = await self._supplier_name(order)
                text, blocks = templates.slack_purchase_order(order, mission, supplier, url)
                specs.append(self._slack(text, blocks))
                specs.append(self._drive(f"po:{order['id']}", f"{order['po_number']}.pdf",
                                         {"kind": "purchase_order", "order_id": order["id"]}))
                specs.append(self._drive("audit", "Audit-Export.json", {"kind": "audit"}))
        elif kind == events.PURCHASE_ORDER_ACCEPTED:
            order = await self.store.get("purchase_orders", data["order_id"])
            if order:
                body = templates.calendar_supplier_eta(order, mission, await self._supplier_name(order), url)
                if body:
                    specs.append(self._calendar(mission, f"eta:{order['id']}", "upsert", body, body["summary"]))
        elif kind == events.FULFILLMENT_UPDATED:
            order = await self.store.get("purchase_orders", data["order_id"])
            if order:
                supplier = await self._supplier_name(order)
                text, blocks = templates.slack_fulfillment(order, mission, supplier, data["status"],
                                                           data.get("note") or "", url)
                specs.append(self._slack(text, blocks))
                slot = f"eta:{order['id']}"
                if data["status"] == "cancelled":
                    specs.append(self._calendar(mission, slot, "cancel", None, f"Cancel ETA {order['po_number']}"))
                elif data["status"] == "completed":
                    body = templates.calendar_supplier_eta(order, mission, supplier, url, delivered=True)
                    if body:
                        specs.append(self._calendar(mission, slot, "upsert", body, body["summary"]))
        return specs

    async def _plan_specs(self, kind: str, mission: dict[str, Any], data: dict[str, Any],
                          url: str) -> list[dict[str, Any]]:
        plan = await self.store.get("plans", data["plan_id"])
        if not plan:
            return []
        quotes = await self.store.find("quotes", mission_id=mission["id"])
        due = templates.approval_due(mission, quotes, plan)
        specs = []
        if plan["status"] == "infeasible":
            subject, html, text = templates.replan_email(mission, plan, url, due)
            recipients = sorted({m["email"] for m in await self.members(mission["organization_id"],
                                                                         COORDINATOR_ROLES)})
            specs += self._emails(recipients, subject, html, text, "replan_infeasible", "No coordinator to notify")
            specs.append(self._slack(*templates.slack_replan(mission, plan, url)))
            body = templates.calendar_approval(mission, plan, due, url, "infeasible")
            specs.append(self._calendar(mission, "approval", "upsert", body, body["summary"]))
            return specs
        if kind == events.PLAN_REPLANNED:
            subject, html, text = templates.replan_email(mission, plan, url, due)
            slack_text, blocks = templates.slack_replan(mission, plan, url)
        else:
            subject, html, text = templates.approval_email(mission, plan, url, due)
            slack_text, blocks = templates.slack_approval(mission, plan, url, due)
        specs += self._emails(await self.approver_emails(mission), subject, html, text, kind,
                              "No approver other than the requester is in this organization; add an approver")
        specs.append(self._slack(slack_text, blocks))
        body = templates.calendar_approval(mission, plan, due, url, "required")
        specs.append(self._calendar(mission, "approval", "upsert", body, body["summary"]))
        return specs

    async def _disruption_specs(self, mission: dict[str, Any], data: dict[str, Any],
                                url: str) -> list[dict[str, Any]]:
        subject, html, text = templates.disruption_email(mission, data, url)
        recipients = sorted({m["email"] for m in await self.members(mission["organization_id"])})
        specs = self._emails(recipients, subject, html, text, "supplier_disrupted", "No organization member to notify")
        slack_text, blocks = templates.slack_disruption(mission, data, url)
        specs.append(self._slack(slack_text, blocks, supersede=data.get("stale_versions")))
        specs += await self._stale_approval_specs(mission, data.get("stale_versions") or [], data.get("reason"), url)
        return specs

    async def _stale_approval_specs(self, mission: dict[str, Any], stale_versions: list[int], reason: str | None,
                                    url: str) -> list[dict[str, Any]]:
        if not stale_versions:
            return []
        plans = {p["version"]: p for p in await self.store.find("plans", mission_id=mission["id"])}
        plan = plans.get(max(stale_versions))
        if not plan:
            return []
        quotes = await self.store.find("quotes", mission_id=mission["id"])
        due = templates.approval_due(mission, quotes, plan)
        body = templates.calendar_approval(mission, plan, due, url, "stale", reason)
        return [self._calendar(mission, "approval", "upsert", body, body["summary"])]

    async def _supplier_name(self, order: dict[str, Any]) -> str:
        supplier = await self.store.get("suppliers", order["supplier_id"]) or {}
        return supplier.get("legal_name") or order.get("supplier_email") or "supplier"

    # ------------------------------------------------------------------ delivery
    def backoff(self, attempts: int) -> float:
        return min(60.0, self.settings.ops_retry_base_seconds * 2 ** (attempts - 1))

    async def attempt(self, delivery_id: str) -> None:
        delivery = await self.store.get("ops_deliveries", delivery_id)
        if not delivery or delivery["status"] not in RUNNABLE:
            return
        delivery.update(status="SENDING", attempts=delivery["attempts"] + 1, updated_at=now_iso())
        await self.store.replace("ops_deliveries", delivery_id, delivery)
        try:
            outcome = await self._dispatch(delivery)
            delivery.update(status=outcome.pop("status", "SENT"), last_error=outcome.pop("error", None),
                            next_retry_at=None, **outcome)
            if delivery["status"] == "SENT":
                delivery["sent_at"] = now_iso()
        except IntegrationError as exc:
            self._record_failure(delivery, exc)
        except Exception as exc:  # unexpected adapter bug: visible failure, no retry storm
            logger.exception("delivery %s crashed", delivery_id)
            delivery.update(status="FAILED", last_error=f"{type(exc).__name__}: {exc}", next_retry_at=None)
        delivery["updated_at"] = now_iso()
        delivery["history"] = (delivery.get("history") or [])[-9:] + [{
            "attempt": delivery["attempts"], "status": delivery["status"], "error": delivery["last_error"],
            "at": delivery["updated_at"]}]
        await self.store.replace("ops_deliveries", delivery_id, delivery)
        if delivery["status"] == "RETRYING":
            delay = self.backoff(delivery["attempts"])
            self.services.schedule(self.attempt(delivery_id), delay=delay)

    def _record_failure(self, delivery: dict[str, Any], exc: IntegrationError) -> None:
        if exc.not_configured:
            delivery.update(status="NOT_CONFIGURED", last_error=str(exc), next_retry_at=None)
        elif exc.retryable and delivery["attempts"] < delivery.get("max_attempts", 4):
            delay = self.backoff(delivery["attempts"])
            delivery.update(status="RETRYING", last_error=str(exc),
                            next_retry_at=(datetime.now(UTC) + timedelta(seconds=delay)).isoformat())
        else:
            suffix = " (reconnect required)" if exc.reauth else ""
            delivery.update(status="FAILED", last_error=f"{exc}{suffix}", next_retry_at=None)

    async def _dispatch(self, delivery: dict[str, Any]) -> dict[str, Any]:
        handler = {"gmail": self._send_gmail, "slack": self._send_slack, "calendar": self._send_calendar,
                   "drive": self._send_drive}[delivery["channel"]]
        return await handler(delivery)

    async def _send_gmail(self, delivery: dict[str, Any]) -> dict[str, Any]:
        payload = delivery["payload"]
        if payload.get("unroutable"):
            raise IntegrationError(payload["unroutable"], not_configured=True)
        result = await self.services.email.send(
            OutgoingEmail(to=payload["to"], subject=payload["subject"], html=payload["html"], text=payload["text"],
                          headers={"X-ReliefMesh-Event": delivery["event_type"]}),
            delivery["organization_id"], inline_retries=0)
        if result.status == "failed":
            raise IntegrationError(result.error or "email failed", retryable=result.retryable)
        status = EMAIL_STATUS[result.status]
        return {"status": status, "provider": result.provider, "provider_id": result.provider_id,
                "thread_id": result.thread_id, "error": result.error if status != "SENT" else None}

    async def slack_connection(self, organization_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        connection = await connections.load(self.store, organization_id, "slack")
        if not connection or connection.get("status") == "disconnected":
            raise IntegrationError("Slack is not connected for this organization", not_configured=True)
        if connection.get("status") == "needs_reauth":
            raise IntegrationError(connection.get("last_error") or "Slack must be reconnected", reauth=True)
        secrets_ = self.services.vault.open(connection.get("token_ciphertext"))
        if not secrets_:
            raise IntegrationError("Stored Slack credentials are unreadable; reconnect Slack", reauth=True)
        return connection, secrets_

    async def _send_slack(self, delivery: dict[str, Any]) -> dict[str, Any]:
        connection, secrets_ = await self.slack_connection(delivery["organization_id"])
        payload = delivery["payload"]
        try:
            async with self.services.hub.client(timeout=15) as client:
                if connection["mode"] == "bot":
                    body = await slack.post_message(client, secrets_["bot_token"], connection["channel_id"],
                                                    payload["text"], payload["blocks"])
                    outcome = {"provider": "slack", "provider_id": body["ts"], "slack_channel": body.get("channel")}
                    await self._supersede(client, secrets_["bot_token"], delivery)
                else:
                    await slack.post_webhook(client, secrets_["webhook_url"], payload["text"], payload["blocks"])
                    outcome = {"provider": "slack_webhook", "provider_id": None}
        except IntegrationError as exc:
            if exc.reauth:
                connection.update(status="needs_reauth", last_error=str(exc), last_error_at=now_iso())
                await connections.save(self.store, connection)
            raise
        connection.setdefault("last_success", {})["slack"] = now_iso()
        await connections.save(self.store, connection)
        return outcome

    async def _supersede(self, client: Any, token: str, delivery: dict[str, Any]) -> None:
        """Strike through earlier approval posts for plans this disruption made stale (best effort)."""

        versions = set(delivery["payload"].get("supersede_versions") or [])
        if not versions:
            return
        for prior in await self.store.find("ops_deliveries", mission_id=delivery["mission_id"], channel="slack",
                                           status="SENT"):
            if prior["event_type"] not in {events.APPROVAL_REQUIRED, events.PLAN_REPLANNED} \
                    or prior.get("version") not in versions or not prior.get("provider_id") or prior.get("superseded"):
                continue
            text, blocks = templates.slack_superseded(prior["payload"]["text"], delivery["payload"]["text"])
            try:
                await slack.update_message(client, token, prior["slack_channel"], prior["provider_id"], text, blocks)
                prior["superseded"] = now_iso()
                await self.store.replace("ops_deliveries", prior["id"], prior)
            except IntegrationError as exc:
                logger.warning("could not mark Slack message %s stale: %s", prior["provider_id"], exc)

    async def calendar_id_for(self, client: Any, token: str, connection: dict[str, Any], refresh: bool = False) -> str:
        org = connection["organization_id"]
        if org in self.calendars and not refresh:
            return self.calendars[org]
        calendar = await google_calendar.ensure_calendar(client, token, None if refresh else
                                                         connection.get("calendar_id"))
        if calendar["id"] != connection.get("calendar_id"):
            latest = await connections.load(self.store, org, "google") or connection
            latest["calendar_id"] = calendar["id"]
            await connections.save(self.store, latest)
        self.calendars[org] = calendar["id"]
        return calendar["id"]

    async def _send_calendar(self, delivery: dict[str, Any]) -> dict[str, Any]:
        payload = delivery["payload"]
        event_id = payload["event_id"]
        async with self.slot_locks[event_id]:
            slot = await self.store.get("calendar_slots", event_id)
            if slot and slot["sequence"] > delivery["sequence"]:
                return {"status": "SKIPPED", "provider": "google_calendar", "provider_id": event_id,
                        "error": "superseded by a newer update to the same calendar event"}
            async with self.services.hub.client(timeout=15) as client:
                token, connection = await google_auth.access_token(
                    self.store, self.services.vault, self.settings, client, delivery["organization_id"], "calendar")
                calendar_id = await self.calendar_id_for(client, token, connection)
                try:
                    result = await self._apply_calendar(client, token, calendar_id, payload)
                except IntegrationError as exc:
                    if "404" not in str(exc):
                        raise
                    calendar_id = await self.calendar_id_for(client, token, connection, refresh=True)
                    result = await self._apply_calendar(client, token, calendar_id, payload)
            await self.store.upsert("calendar_slots", {
                "id": event_id, "organization_id": delivery["organization_id"], "mission_id": delivery["mission_id"],
                "slot": payload["slot"], "sequence": delivery["sequence"], "op": payload["op"],
                "calendar_id": calendar_id, "html_link": result.get("htmlLink"), "updated_at": now_iso()})
        connection = await connections.load(self.store, delivery["organization_id"], "google")
        if connection:
            connection.setdefault("last_success", {})["calendar"] = now_iso()
            await connections.save(self.store, connection)
        return {"provider": "google_calendar", "provider_id": event_id, "provider_url": result.get("htmlLink")}

    async def _apply_calendar(self, client: Any, token: str, calendar_id: str, payload: dict[str, Any]) -> dict:
        if payload["op"] == "cancel":
            await google_calendar.cancel_event(client, token, calendar_id, payload["event_id"])
            return {}
        return await google_calendar.upsert_event(client, token, calendar_id, payload["event_id"], payload["body"])

    async def _render_document(self, delivery: dict[str, Any]) -> tuple[bytes, str]:
        render = delivery["payload"]["render"]
        mission = await self.store.get("missions", delivery["mission_id"])
        if not mission:
            raise IntegrationError("mission no longer exists")
        if render["kind"] == "purchase_order":
            order = await self.store.get("purchase_orders", render["order_id"])
            if not order:
                raise IntegrationError("purchase order no longer exists")
            return documents.purchase_order_pdf(order), "application/pdf"
        if render["kind"] == "plan":
            plan = await self.store.get("plans", render["plan_id"])
            if not plan:
                raise IntegrationError("plan no longer exists")
            approval = await self.store.get("approvals", render["approval_id"]) if render.get("approval_id") else None
            return documents.plan_pdf(plan, mission, approval), "application/pdf"
        from ..core import audit_head_key, verify_chain

        chain_key = f"mission:{mission['id']}"
        audit_events = await self.store.find("audit_events", chain_key=chain_key)
        verification = verify_chain(audit_events, await self.store.get("audit_chain_heads", chain_key),
                                    secret_key=audit_head_key(self.services))
        return documents.audit_export(mission, audit_events, verification), "application/json"

    async def _send_drive(self, delivery: dict[str, Any]) -> dict[str, Any]:
        org, mission_id = delivery["organization_id"], delivery["mission_id"]
        content, mime_type = await self._render_document(delivery)
        mission = await self.store.get("missions", mission_id) or {"name": mission_id}
        async with self.services.hub.client(timeout=30) as client:
            token, connection = await google_auth.access_token(
                self.store, self.services.vault, self.settings, client, org, "drive")
            async with self.folder_locks[org]:
                folder = await self._mission_folder(client, token, connection, mission_id, mission["name"])
            doc_key = f"{org}:{mission_id}:{delivery['payload']['doc']}"
            known = await self.store.get("drive_files", doc_key)
            uploaded = await google_drive.upload(client, token, delivery["payload"]["filename"], content, mime_type,
                                                 folder, known["file_id"] if known else None)
        await self.store.upsert("drive_files", {"id": doc_key, "organization_id": org, "mission_id": mission_id,
                                                "file_id": uploaded["id"], "web_view_link": uploaded.get("webViewLink"),
                                                "filename": uploaded.get("name"), "updated_at": now_iso()})
        latest = await connections.load(self.store, org, "google")
        if latest:
            latest.setdefault("last_success", {})["drive"] = now_iso()
            await connections.save(self.store, latest)
        return {"provider": "google_drive", "provider_id": uploaded["id"], "provider_url": uploaded.get("webViewLink")}

    async def _mission_folder(self, client: Any, token: str, connection: dict[str, Any], mission_id: str,
                              name: str) -> str:
        latest = await connections.load(self.store, connection["organization_id"], "google") or connection
        root = await google_drive.ensure_folder(client, token, "ReliefMesh", None, latest.get("drive_root_id"))
        missions = await google_drive.ensure_folder(client, token, "Missions", root["id"],
                                                    latest.get("drive_missions_id")
                                                    if latest.get("drive_root_id") == root["id"] else None)
        if (latest.get("drive_root_id"), latest.get("drive_missions_id")) != (root["id"], missions["id"]):
            latest.update(drive_root_id=root["id"], drive_missions_id=missions["id"])
            await connections.save(self.store, latest)
        folder_key = f"{connection['organization_id']}:{mission_id}"
        known = await self.store.get("drive_folders", folder_key)
        folder = await google_drive.ensure_folder(
            client, token, name[:120], missions["id"],
            known["folder_id"] if known and known.get("parent_id") == missions["id"] else None)
        if not known or known["folder_id"] != folder["id"]:
            await self.store.upsert("drive_folders", {"id": folder_key, "folder_id": folder["id"],
                                                      "parent_id": missions["id"], "web_view_link":
                                                      folder.get("webViewLink"), "updated_at": now_iso()})
        return folder["id"]

    # ------------------------------------------------------------------ maintenance
    async def retry(self, delivery: dict[str, Any]) -> dict[str, Any]:
        delivery.update(status="PENDING", attempts=0, next_retry_at=None, updated_at=now_iso())
        await self.store.replace("ops_deliveries", delivery["id"], delivery)
        self.services.schedule(self.attempt(delivery["id"]))
        return delivery

    async def recover(self) -> None:
        """Resume deliveries interrupted by a restart (SENDING means the process died mid-call)."""

        for status in ("PENDING", "RETRYING", "SENDING"):
            for delivery in await self.store.find("ops_deliveries", status=status):
                if status == "SENDING":
                    delivery["status"] = "RETRYING"
                    await self.store.replace("ops_deliveries", delivery["id"], delivery)
                self.services.schedule(self.attempt(delivery["id"]), delay=1.0)
