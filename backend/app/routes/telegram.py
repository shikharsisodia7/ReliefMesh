"""Telegram bot webhook for ReliefMesh supplier messaging."""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pymongo.errors import DuplicateKeyError

from ..core import (
    Services, audit, current_user, get_services, invitation_from_token, new_id, now_iso, notify, secret, token_hash,
)
from ..jobs import enqueue
from ..operations import events as ops_events
from ..requirements import assign_quote_lines
from ..workflows import apply_quote_change
from .procurement import ensure_supplier, supplier_backed_out

router = APIRouter(tags=["telegram"])
logger = logging.getLogger(__name__)
PRICE_COMMAND = re.compile(r"^/?(?:PRICE|UPDATE)(?:@[A-Za-z0-9_]+)?\s+(.+?)\s+(?:TO\s+)?\$?([0-9]+(?:\.[0-9]{1,2})?)$", re.I)
CONFIRM_COMMAND = re.compile(r"^CONFIRM\s+(\d{6})$", re.I)
START_COMMAND = re.compile(r"^/start(?:@[A-Za-z0-9_]+)?(?:\s+([A-Za-z0-9_-]{6,64}))?$", re.I)


def help_text() -> str:
    return (
        "ReliefMesh supplier bot\n"
        "• /rfqs — see new requests sent to your verified email\n"
        "• /accept <code> — accept an RFQ\n"
        "• /quote <code> — submit a quote, one item at a time\n"
        "• STATUS — see your active quotes\n"
        "• PRICE <exact item> <new unit price> — request a price update\n"
        "• CONFIRM <6-digit code> — confirm the requested update\n"
        "• /orders — see purchase orders\n"
        "• ACCEPT <PO number> / DECLINE <PO number> [reason]\n"
        "• /ship <PO number> <note> / /delivered <PO number> <note>\n"
        "• STOP — pause bot replies\n\n"
        "New supplier? Open the Telegram button in your ReliefMesh RFQ email to onboard here."
    )


async def supplier_status(services: Services, supplier_id: str) -> str:
    quotes = [q for q in await services.store.find("quotes", supplier_id=supplier_id)
              if q.get("status") == "submitted"]
    if not quotes:
        return "You have no active submitted quotes."
    rows = []
    for quote in quotes[:4]:
        mission = await services.store.get("missions", quote["mission_id"])
        rows.append(f"{(mission or {}).get('name', 'mission')}: {len(quote.get('lines', []))} item(s), "
                    f"quote version {quote.get('version', 1)}")
    return "Your active quotes:\n" + "\n".join(rows)


def find_item_line(quote: dict[str, Any], item: str) -> tuple[int, dict[str, Any]] | None:
    normalized = " ".join(item.casefold().split())
    matches = [(i, line) for i, line in enumerate(quote.get("lines", []))
               if " ".join(str(line.get("item", "")).casefold().split()) == normalized]
    return matches[0] if len(matches) == 1 else None


async def begin_invitation_onboarding(services: Services, telegram_user_id: str, raw_token: str) -> str:
    try:
        invitation = await invitation_from_token(raw_token, services)
    except HTTPException:
        return "That RFQ link is invalid or expired. Ask the buyer to resend the invitation email."
    if invitation.get("status") != "sent":
        # RFQ links are single use (REL-004): a used link must not bind a new Telegram account to the profile.
        return (f"This RFQ is already {invitation.get('status', 'closed')}. To use Telegram with an existing supplier "
                "profile, sign in to ReliefMesh and generate a Telegram link code.")

    # The RFQ link proves control of one invitation, not of an existing supplier account. Only a profile that was
    # created in Telegram by this same chat may be reused; portal accounts must link with a signed-in link code.
    existing = await services.store.find("suppliers", email=invitation["supplier_email"].casefold())
    if any(row.get("user_id") or row.get("telegram_user_id") not in (None, telegram_user_id) for row in existing):
        return ("This email already has a ReliefMesh supplier account. Sign in to accept the RFQ in the portal, or "
                "generate a Telegram link code there to connect this chat.")
    supplier = next((row for row in existing if row.get("telegram_user_id") == telegram_user_id), None)
    state = {
        "id": telegram_user_id, "telegram_user_id": telegram_user_id,
        "invitation_id": invitation["id"], "supplier_email": invitation["supplier_email"].casefold(),
        "supplier_id": supplier["id"] if supplier else None,
        "legal_name": supplier.get("legal_name") if supplier else None,
        "stage": "confirm_rfq" if supplier and supplier.get("legal_name") else "legal_name",
        "status": "pending", "created_at": now_iso(),
    }
    await services.store.upsert("telegram_onboarding", state)
    mission = await services.store.get("missions", invitation["mission_id"]) or {}
    org = await services.store.get("organizations", invitation["organization_id"]) or {}
    if state["stage"] == "legal_name":
        return (f"Welcome. {org.get('name', 'A ReliefMesh buyer')} invited {invitation['supplier_email']} "
                f"to quote {mission.get('name', 'an emergency supply request')}.\n\n"
                "To create your supplier profile in Telegram, send your registered legal business name. "
                "This is used for supplier screening. Send CANCEL to stop.")
    supplier.update(telegram_user_id=telegram_user_id, updated_at=now_iso())
    await services.store.replace("suppliers", supplier["id"], supplier)
    await services.store.upsert("telegram_subscriptions", {
        "id": telegram_user_id, "telegram_user_id": telegram_user_id,
        "supplier_id": supplier["id"], "active": True, "updated_at": now_iso(),
    })
    items = ", ".join(f"{r.get('quantity')} x {r.get('item')}" for r in mission.get("requirements", []))
    return (f"RFQ: {mission.get('name', 'Emergency supply request')}\n"
            f"Buyer: {org.get('name', 'ReliefMesh organization')}\n"
            f"Delivery: {mission.get('delivery_location', 'see request')} by {mission.get('delivery_deadline', 'see request')}\n"
            f"Items: {items}\n\n"
            "Reply ACCEPT to accept this RFQ or DECLINE to decline it.")


async def finish_invitation_onboarding(services: Services, telegram_user_id: str, body: str) -> str | None:
    state = await services.store.get("telegram_onboarding", telegram_user_id)
    if not state or state.get("status") != "pending":
        return None
    command = body.strip()
    if command.casefold() in {"cancel", "/cancel"}:
        state.update(status="cancelled", updated_at=now_iso())
        await services.store.replace("telegram_onboarding", telegram_user_id, state)
        return "Onboarding cancelled. Your RFQ link remains available until its deadline."
    if state["stage"] == "legal_name":
        legal_name = " ".join(command.split())
        if len(legal_name) < 2 or len(legal_name) > 200 or legal_name.startswith("/"):
            return "Send the registered legal business name (2–200 characters), or CANCEL."
        state.update(legal_name=legal_name, stage="confirm_rfq", updated_at=now_iso())
        await services.store.replace("telegram_onboarding", telegram_user_id, state)
        invitation = await services.store.get("invitations", state["invitation_id"])
        mission = await services.store.get("missions", invitation["mission_id"]) if invitation else None
        org = await services.store.get("organizations", invitation["organization_id"]) if invitation else None
        if not invitation or not mission:
            state.update(status="expired", updated_at=now_iso())
            await services.store.replace("telegram_onboarding", telegram_user_id, state)
            return "This RFQ is no longer available. Ask the buyer to send a new invitation."
        items = ", ".join(f"{row.get('quantity')} × {row.get('item')}" for row in mission.get("requirements", []))
        return (f"Supplier: {legal_name}\nRFQ: {mission['name']}\nBuyer: {(org or {}).get('name', 'ReliefMesh buyer')}\n"
                f"Delivery: {mission['delivery_location']} by {mission['delivery_deadline']}\nItems: {items}\n\n"
                "Reply ACCEPT to accept this RFQ, or DECLINE to decline it.")
    choice = command.upper().removeprefix("/")
    if choice not in {"ACCEPT", "DECLINE"}:
        return "Reply ACCEPT to accept this RFQ or DECLINE to decline it."
    invitation = await services.store.get("invitations", state["invitation_id"])
    if not invitation or invitation.get("status") != "sent" or invitation.get("expires_at", "") <= now_iso():
        state.update(status="expired", updated_at=now_iso())
        await services.store.replace("telegram_onboarding", telegram_user_id, state)
        return "This RFQ is no longer available. Ask the buyer to send a new invitation."
    supplier = await services.store.get("suppliers", state.get("supplier_id") or "")
    if supplier and (supplier.get("user_id") or supplier.get("telegram_user_id") not in (None, telegram_user_id)):
        return "This supplier profile belongs to a ReliefMesh account. Sign in to the portal to respond to this RFQ."
    if not supplier and await services.store.find("suppliers", email=state["supplier_email"]):
        # A portal account was created for this email while onboarding was pending.
        return "This email now has a ReliefMesh supplier account. Sign in to the portal to respond to this RFQ."
    if choice == "DECLINE":
        invitation.update(status="declined", declined_at=now_iso(), declined_via="telegram")
        await services.store.replace("invitations", invitation["id"], invitation)
        state.update(status="declined", updated_at=now_iso())
        await services.store.replace("telegram_onboarding", telegram_user_id, state)
        await audit("rfq.declined.via_telegram", state.get("supplier_id"), invitation["organization_id"],
                    invitation["mission_id"], "invitation", invitation["id"], services)
        return "RFQ declined. You can still see other requests with /rfqs."
    if not supplier:
        supplier = {
            "id": new_id(), "user_id": None, "email": state["supplier_email"],
            "legal_name": state["legal_name"], "telegram_user_id": telegram_user_id,
            "is_demo": False, "data_origin": "USER_SUBMITTED", "created_at": now_iso(), "updated_at": now_iso(),
        }
        await services.store.insert("suppliers", supplier)
    else:
        if supplier.get("telegram_user_id") not in (None, telegram_user_id):
            return "This supplier profile is connected to a different Telegram account. Contact the buyer to update access."
        supplier.update(telegram_user_id=telegram_user_id, updated_at=now_iso())
        await services.store.replace("suppliers", supplier["id"], supplier)
    invitation.update(status="accepted", accepted_by_user_id=supplier["id"], accepted_at=now_iso(),
                      accepted_via="telegram")
    await services.store.replace("invitations", invitation["id"], invitation)
    if invitation.get("lead_id"):
        lead = await services.store.get("supplier_leads", invitation["lead_id"])
        if lead:
            lead.update(status="onboarded", supplier_id=supplier["id"], onboarded_at=now_iso())
            await services.store.replace("supplier_leads", lead["id"], lead)
        supplier["lead_id"] = invitation["lead_id"]
        await services.store.replace("suppliers", supplier["id"], supplier)
    await services.store.upsert("telegram_subscriptions", {
        "id": telegram_user_id, "telegram_user_id": telegram_user_id,
        "supplier_id": supplier["id"], "active": True, "updated_at": now_iso(),
    })
    state.update(status="accepted", supplier_id=supplier["id"], updated_at=now_iso())
    await services.store.replace("telegram_onboarding", telegram_user_id, state)
    await audit("rfq.accepted.via_telegram", supplier["id"], invitation["organization_id"],
                invitation["mission_id"], "invitation", invitation["id"], services)
    return (f"RFQ accepted for {supplier.get('legal_name')}. Your supplier profile is ready in Telegram. "
            "Send /quote to submit your offer, /rfqs for other requests, or /help for commands.")


async def list_telegram_rfqs(services: Services, supplier: dict[str, Any]) -> str:
    rows = [row for row in await services.store.find("invitations", supplier_email=supplier["email"].casefold())
            if row.get("status") == "sent" and row.get("expires_at", "") > now_iso()]
    if not rows:
        return "No new RFQs are waiting for this supplier email."
    results = []
    for row in sorted(rows, key=lambda item: item.get("created_at", ""), reverse=True)[:6]:
        mission = await services.store.get("missions", row["mission_id"]) or {}
        results.append(f"{row['id'][-8:]} · {mission.get('name', 'RFQ')} · due {mission.get('delivery_deadline', '—')}")
    return "New RFQs (use /accept <code>):\n" + "\n".join(results)


async def accept_telegram_rfq(services: Services, supplier: dict[str, Any], code: str) -> str:
    matches = [row for row in await services.store.find("invitations", supplier_email=supplier["email"].casefold())
               if row.get("status") == "sent" and row.get("id", "").endswith(code)]
    if len(matches) != 1:
        return "RFQ code not found or ambiguous. Send /rfqs to see current request codes."
    invitation = matches[0]
    if invitation.get("expires_at", "") <= now_iso():
        return "That RFQ has expired. Ask the buyer to send a new invitation."
    invitation.update(status="accepted", accepted_by_user_id=supplier["id"], accepted_at=now_iso(),
                      accepted_via="telegram")
    await services.store.replace("invitations", invitation["id"], invitation)
    if invitation.get("lead_id"):
        lead = await services.store.get("supplier_leads", invitation["lead_id"])
        if lead:
            lead.update(status="onboarded", supplier_id=supplier["id"], onboarded_at=now_iso())
            await services.store.replace("supplier_leads", lead["id"], lead)
    await audit("rfq.accepted.via_telegram", supplier["id"], invitation["organization_id"],
                invitation["mission_id"], "invitation", invitation["id"], services)
    mission = await services.store.get("missions", invitation["mission_id"]) or {}
    return f"Accepted {mission.get('name', 'the RFQ')}. Send /quote {invitation['id'][-8:]} to submit an offer."


async def begin_telegram_quote(services: Services, telegram_user_id: str, supplier: dict[str, Any],
                              code: str | None = None) -> str:
    invitations = [row for row in await services.store.find("invitations", supplier_email=supplier["email"].casefold())
                   if row.get("status") == "accepted" and row.get("accepted_by_user_id") == supplier["id"]
                   and row.get("expires_at", "") > now_iso()
                   and not await services.store.find("quotes", invitation_id=row["id"])]
    if code:
        invitations = [row for row in invitations if row["id"].endswith(code)]
    if len(invitations) != 1:
        return "Choose one accepted RFQ with /quote <code>. Use /rfqs for new requests and /status for submitted quotes."
    invitation = invitations[0]
    mission = await services.store.get("missions", invitation["mission_id"])
    if not mission:
        return "The mission is no longer available."
    state = {
        "id": telegram_user_id, "telegram_user_id": telegram_user_id, "supplier_id": supplier["id"],
        "invitation_id": invitation["id"], "mission_id": mission["id"], "stage": "shipping",
        "line_index": 0, "lines": [], "status": "draft", "created_at": now_iso(),
    }
    await services.store.upsert("telegram_quote_drafts", state)
    return (f"Quote for {mission['name']}. Items: "
            f"{', '.join(row['item'] for row in mission.get('requirements', []))}.\n"
            "Send your shipping cost in dollars (for example 0 or 18.50)."
            " Send CANCEL to stop.")


async def handle_telegram_quote_draft(services: Services, telegram_user_id: str, body: str) -> str | None:
    draft = await services.store.get("telegram_quote_drafts", telegram_user_id)
    if not draft or draft.get("status") != "draft":
        return None
    command = body.strip()
    if command.upper() in {"CANCEL", "/CANCEL"}:
        draft.update(status="cancelled", updated_at=now_iso())
        await services.store.replace("telegram_quote_drafts", telegram_user_id, draft)
        return "Quote draft cancelled. No quote was submitted."
    mission = await services.store.get("missions", draft["mission_id"])
    invitation = await services.store.get("invitations", draft["invitation_id"])
    supplier = await services.store.get("suppliers", draft["supplier_id"])
    if not mission or not invitation or not supplier or invitation.get("status") != "accepted":
        draft.update(status="expired", updated_at=now_iso())
        await services.store.replace("telegram_quote_drafts", telegram_user_id, draft)
        return "This quote draft is no longer valid. Start again with /quote."
    if draft["stage"] == "review":
        if command.upper() not in {"SUBMIT", "/SUBMIT"}:
            return "Review the quote above. Reply SUBMIT to send this binding supplier offer, or CANCEL."
        if await services.store.find("quotes", invitation_id=invitation["id"]):
            draft.update(status="expired", updated_at=now_iso())
            await services.store.replace("telegram_quote_drafts", telegram_user_id, draft)
            return "A quote already exists for this RFQ. Use PRICE <exact item> <new price> to revise it."
        try:
            lines = assign_quote_lines(draft["lines"], mission)
        except HTTPException:
            return "The quote items no longer match the RFQ. Cancel and start again with /quote."
        quote = {
            "id": new_id(), "mission_id": invitation["mission_id"],
            "organization_id": invitation["organization_id"], "invitation_id": invitation["id"],
            "supplier_id": supplier["id"], "supplier_email": supplier["email"],
            "supplier_name": supplier.get("legal_name"), "status": "submitted", "version": 1,
            "provenance": "USER_SUBMITTED", "currency": mission.get("currency", "USD"),
            "shipping_cost": draft["shipping_cost"], "expires_at": mission["delivery_deadline"],
            "lines": lines, "created_at": now_iso(), "updated_at": now_iso(),
        }
        await services.store.insert("quotes", quote)
        await audit("quote.submitted.via_telegram", supplier["id"], quote["organization_id"],
                    quote["mission_id"], "quote", quote["id"], services,
                    {"invitation_id": invitation["id"], "line_count": len(lines)})
        draft.update(status="submitted", quote_id=quote["id"], updated_at=now_iso())
        await services.store.replace("telegram_quote_drafts", telegram_user_id, draft)
        await enqueue(services, "evidence_refresh", mission,
                      trigger={"kind": "quote_submitted", "supplier_id": supplier["id"], "at": now_iso()})
        return "Quote submitted to the buyer. ReliefMesh will screen the supplier record and notify the coordinator."
    if draft["stage"] == "shipping":
        try:
            amount = Decimal(command.replace("$", ""))
            if not amount.is_finite() or amount < 0 or amount > Decimal("999999999999.99"):
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            return "Send a nonnegative shipping cost, such as 0 or 18.50, or CANCEL."
        draft.update(shipping_cost=f"{amount:.2f}", stage="line", line_index=0, updated_at=now_iso())
        await services.store.replace("telegram_quote_drafts", telegram_user_id, draft)
    requirements = mission.get("requirements", [])
    index = draft["line_index"]
    if index >= len(requirements):
        return "Quote draft state is invalid. Send CANCEL and restart with /quote."
    requirement = requirements[index]
    if draft["stage"] == "line":
        match = re.fullmatch(r"\$?([0-9]+(?:\.[0-9]{1,2})?)\s+([1-9][0-9]{0,5})\s+(\d{4}-\d{2}-\d{2})", command)
        if not match:
            return (f"For {requirement['item']} (request is {requirement['quantity']}), send: "
                    "<unit price> <available quantity> <delivery date YYYY-MM-DD>. Example: 2.50 100 2026-10-30")
        price, quantity, delivery_day = match.groups()
        try:
            delivery_date = datetime.strptime(delivery_day, "%Y-%m-%d").replace(tzinfo=UTC)
            amount = Decimal(price)
        except (ValueError, InvalidOperation):
            return "That price or delivery date is invalid. Try the requested format again."
        deadline = datetime.fromisoformat(str(mission["delivery_deadline"]).replace("Z", "+00:00"))
        if delivery_date.date() < datetime.now(UTC).date() or delivery_date > deadline:
            return f"Delivery must be between today and the mission deadline ({deadline.date().isoformat()})."
        draft["lines"].append({"requirement_id": requirement.get("id"), "item": requirement["item"],
                               "unit_price": f"{amount:.2f}", "available_quantity": int(quantity),
                               "delivery_date": delivery_date.isoformat(), "restrictions": None, "evidence_url": None})
        draft["line_index"] += 1
        if draft["line_index"] >= len(requirements):
            draft["stage"] = "review"
            await services.store.replace("telegram_quote_drafts", telegram_user_id, draft)
            summary = "\n".join(f"{line['item']}: ${line['unit_price']} × {line['available_quantity']} · ETA {line['delivery_date'][:10]}"
                                for line in draft["lines"])
            return (f"Quote preview (shipping ${draft['shipping_cost']}):\n{summary}\n\n"
                    "Reply SUBMIT to send this binding offer, or CANCEL. Nothing is submitted until you confirm.")
        await services.store.replace("telegram_quote_drafts", telegram_user_id, draft)
        next_requirement = requirements[draft["line_index"]]
        return (f"Saved {requirement['item']}. Next: {next_requirement['item']} "
                f"(request is {next_requirement['quantity']}). Send: <unit price> <available quantity> "
                "<delivery date YYYY-MM-DD>.")
    return "Quote draft paused. Continue with the requested price, quantity, and delivery date, or CANCEL."


async def telegram_orders(services: Services, supplier: dict[str, Any]) -> str:
    rows = [row for row in await services.store.find("purchase_orders", supplier_id=supplier["id"])
            if row.get("status") in {"sent", "supplier_accepted", "in_fulfillment"}]
    if not rows:
        return "No open purchase orders."
    results = []
    for order in sorted(rows, key=lambda row: row.get("created_at", ""), reverse=True)[:8]:
        mission = await services.store.get("missions", order["mission_id"]) or {}
        results.append(f"{order['po_number']} · {mission.get('name', 'mission')} · {order['status']} · ${order.get('subtotal', '—')}")
    return "Your open purchase orders:\n" + "\n".join(results)


async def telegram_order_action(services: Services, supplier: dict[str, Any], telegram_user_id: str,
                                command: str) -> str | None:
    response = re.fullmatch(r"(?:/)?(ACCEPT|DECLINE)\s+(PO-[A-Za-z0-9-]+)(?:\s+(.+))?", command, re.I)
    if response:
        action, po_number, reason = response.group(1).lower(), response.group(2), response.group(3)
        orders = await services.store.find("purchase_orders", supplier_id=supplier["id"], po_number=po_number)
        if len(orders) != 1:
            return "Purchase order not found for this supplier. Send /orders to see your open orders."
        order = orders[0]
        if order.get("status") != "sent":
            return f"{po_number} is {order.get('status')}; only sent orders can be accepted or declined."
        order.update(status="supplier_accepted" if action == "accept" else "supplier_declined",
                     supplier_response_at=now_iso(), supplier_response_reason=reason)
        order["events"].append({"status": order["status"], "at": now_iso(), "actor_id": supplier["id"],
                                "channel": "telegram"})
        await services.store.replace("purchase_orders", order["id"], order)
        await audit("purchase_order.supplier_response.via_telegram", supplier["id"], order["organization_id"],
                    order["mission_id"], "purchase_order", order["id"], services, {"accepted": action == "accept"})
        mission = await services.store.get("missions", order["mission_id"])
        if mission:
            await notify(services, mission, "po_response",
                         f"{po_number} was {'accepted' if action == 'accept' else 'declined'} by the supplier.",
                         "success" if action == "accept" else "warning", {"order_id": order["id"]})
            if action == "accept":
                await ops_events.emit(services, ops_events.PURCHASE_ORDER_ACCEPTED, mission,
                                      subject_id=order["id"], data={"order_id": order["id"]})
            else:
                user = {"id": supplier["id"], "email": supplier["email"], "role": "supplier"}
                await supplier_backed_out(services, mission, order, user,
                                          f"declined {po_number}{': ' + reason if reason else ''}")
        return f"{po_number} {('accepted' if action == 'accept' else 'declined')}."
    fulfillment = re.fullmatch(r"(?:/)?(SHIP|DELIVERED|CANNOT-FULFILL)\s+(PO-[A-Za-z0-9-]+)\s+(.+)", command, re.I)
    if not fulfillment:
        return None
    action, po_number, note = fulfillment.group(1).lower(), fulfillment.group(2), fulfillment.group(3).strip()
    orders = await services.store.find("purchase_orders", supplier_id=supplier["id"], po_number=po_number)
    if len(orders) != 1:
        return "Purchase order not found for this supplier. Send /orders to see your open orders."
    order = orders[0]
    if order.get("status") not in {"supplier_accepted", "in_fulfillment"}:
        return "Only an accepted order can receive shipment or delivery updates."
    status = "in_fulfillment" if action == "ship" else "completed" if action == "delivered" else "cancelled"
    order["status"] = status
    order["events"].append({"status": status, "note": note, "at": now_iso(), "actor_id": supplier["id"],
                            "channel": "telegram"})
    await services.store.replace("purchase_orders", order["id"], order)
    await services.store.insert("fulfillment_events", {
        "id": new_id(), "purchase_order_id": order["id"], "status": status, "note": note,
        "actor_id": supplier["id"], "created_at": now_iso(), "channel": "telegram",
    })
    await audit("fulfillment.updated.via_telegram", supplier["id"], order["organization_id"], order["mission_id"],
                "purchase_order", order["id"], services, {"status": status})
    mission = await services.store.get("missions", order["mission_id"])
    if mission:
        await notify(services, mission, "fulfillment", f"{po_number}: {status} - {note}",
                     "warning" if status == "cancelled" else "info", {"order_id": order["id"]})
        await ops_events.emit(services, ops_events.FULFILLMENT_UPDATED, mission, subject_id=order["id"],
                              version=len(order["events"]), data={"order_id": order["id"], "status": status, "note": note})
        if status == "cancelled":
            user = {"id": supplier["id"], "email": supplier["email"], "role": "supplier"}
            await supplier_backed_out(services, mission, order, user, f"cancelled {po_number}: {note}")
    return f"{po_number} updated to {status}."


async def link_telegram_account(services: Services, telegram_user_id: str, code: str) -> str:
    matches = await services.store.find("telegram_link_tokens", code_hash=token_hash(code))
    token = next((row for row in matches if row.get("status") == "pending"
                  and row.get("expires_at", "") > now_iso()), None)
    if not token:
        logger.warning("Telegram supplier link rejected: no active matching code; pending=%d", len(matches))
        return "That link code is invalid or expired. Generate a new code from your ReliefMesh supplier account."
    linked_elsewhere = [row for row in await services.store.find("suppliers", telegram_user_id=telegram_user_id)
                        if row["id"] != token["supplier_id"]]
    if linked_elsewhere:
        return "This Telegram account is already linked to another supplier profile. Contact your workspace admin."
    supplier = await services.store.get("suppliers", token["supplier_id"])
    if not supplier:
        return "The supplier profile for this link code is unavailable. Generate a new code in ReliefMesh."
    supplier["telegram_user_id"] = telegram_user_id
    supplier["updated_at"] = now_iso()
    await services.store.replace("suppliers", supplier["id"], supplier)
    token.update(status="used", used_at=now_iso())
    await services.store.replace("telegram_link_tokens", token["id"], token)
    await services.store.upsert("telegram_subscriptions", {"id": telegram_user_id,
                                   "telegram_user_id": telegram_user_id, "supplier_id": supplier["id"],
                                   "active": True, "updated_at": now_iso()})
    logger.warning("Telegram supplier account linked")
    return f"Telegram linked to {supplier.get('legal_name') or 'your supplier profile'}. Text STATUS or PRICE <item> <price>."


async def reply_for_telegram(services: Services, telegram_user_id: str, body: str) -> str:
    command = body.strip()
    subscription = await services.store.get("telegram_subscriptions", telegram_user_id)
    if command.upper() in {"HELP", "/HELP"}:
        return help_text()
    if command.upper() in {"STOP", "/STOP"}:
        await services.store.upsert("telegram_subscriptions", {"id": telegram_user_id,
                                       "telegram_user_id": telegram_user_id,
                                       "supplier_id": subscription.get("supplier_id") if subscription else None,
                                       "active": False, "updated_at": now_iso()})
        return "ReliefMesh replies paused. Send /start to resume."
    start = START_COMMAND.fullmatch(command)
    if start:
        code = start.group(1)
        if code:
            link_tokens = await services.store.find("telegram_link_tokens", code_hash=token_hash(code))
            if any(row.get("status") == "pending" and row.get("expires_at", "") > now_iso()
                   for row in link_tokens):
                return await link_telegram_account(services, telegram_user_id, code)
            return await begin_invitation_onboarding(services, telegram_user_id, code)
        # `/start` without a fresh one-time code may resume a valid linked chat, but must
        # never reconnect an identity that the supplier disconnected in ReliefMesh.
        linked_supplier = await services.store.get("suppliers", subscription.get("supplier_id", "")) if subscription else None
        if subscription and subscription.get("supplier_id") and (
                not linked_supplier or linked_supplier.get("telegram_user_id") != telegram_user_id):
            subscription.update(supplier_id=None, active=False, updated_at=now_iso())
            await services.store.replace("telegram_subscriptions", telegram_user_id, subscription)
            return "This Telegram connection was removed. Sign in to ReliefMesh and generate a new secure link to reconnect."
        await services.store.upsert("telegram_subscriptions", {"id": telegram_user_id,
                                       "telegram_user_id": telegram_user_id,
                                       "supplier_id": subscription.get("supplier_id") if subscription else None,
                                       "active": True, "updated_at": now_iso()})
        state = await services.store.get("telegram_onboarding", telegram_user_id)
        if state and state.get("status") == "pending":
            return "Continue your supplier setup by replying to the last question, or send CANCEL."
        if subscription and subscription.get("supplier_id"):
            return "Welcome back to ReliefMesh. Text /help for commands."
        return "Welcome to ReliefMesh. Open the Telegram button in your ReliefMesh RFQ email to set up your supplier account here."

    onboarding_reply = await finish_invitation_onboarding(services, telegram_user_id, command)
    if onboarding_reply is not None:
        return onboarding_reply

    quote_reply = await handle_telegram_quote_draft(services, telegram_user_id, command)
    if quote_reply is not None:
        return quote_reply

    suppliers = await services.store.find("suppliers", telegram_user_id=telegram_user_id)
    if len(suppliers) != 1:
        if command.upper() in {"STATUS", "/STATUS"}:
            logger.warning("Telegram status lookup: matching supplier records=%d", len(suppliers))
        return "This Telegram account is not linked to a supplier profile. Log in to ReliefMesh, generate a Telegram link code, then send /start <code> here."
    supplier = suppliers[0]
    if not subscription or not subscription.get("active"):
        if command.upper() in {"STATUS", "/STATUS"}:
            logger.info("Telegram status lookup: linked supplier found but replies paused")
        return "Bot replies are paused. Send /start to resume."

    confirm = CONFIRM_COMMAND.fullmatch(command)
    if confirm:
        code_hash = hashlib.sha256(confirm.group(1).encode()).hexdigest()
        pending_actions = await services.store.find("telegram_pending_actions",
                                                     telegram_user_id=telegram_user_id, status="pending")
        pending = [row for row in pending_actions if row.get("code_hash") == code_hash
                   and row.get("expires_at", "") > now_iso()]
        if len(pending) != 1:
            return "That confirmation code is invalid or expired. Send the price change again to start over."
        action = pending[0]
        quote = await services.store.get("quotes", action["quote_id"])
        mission = await services.store.get("missions", action["mission_id"])
        if (not quote or not mission or quote.get("supplier_id") != supplier["id"]
                or quote.get("version") != action["quote_version"] or quote.get("status") != "submitted"):
            action.update(status="expired", updated_at=now_iso())
            await services.store.replace("telegram_pending_actions", action["id"], action)
            return "The quote changed or closed while this request was pending. Please send the price update again."
        index = action["line_index"]
        if index >= len(quote.get("lines", [])) or quote["lines"][index].get("item") != action["item"]:
            return "The quote line changed. Please send the price update again."
        lines = [dict(line) for line in quote["lines"]]
        lines[index]["unit_price"] = action["unit_price"]
        quote, job = await apply_quote_change(
            services, quote, mission, supplier["id"], kind="updated",
            summary=f"{supplier.get('legal_name') or 'Supplier'} revised {action['item']} price via Telegram",
            updates={"lines": lines},
        )
        await audit("quote.updated.via_telegram", supplier["id"], quote["organization_id"], quote["mission_id"],
                    "quote", quote["id"], services, {"job_id": job["id"], "line_item": action["item"]})
        action.update(status="confirmed", updated_at=now_iso())
        await services.store.replace("telegram_pending_actions", action["id"], action)
        return (f"Quote updated: {action['item']} is now ${action['unit_price']} per unit. "
                "A recovery replan is queued; coordinator approval is still required.")

    if command.casefold() in {"/rfqs", "rfqs"}:
        return await list_telegram_rfqs(services, supplier)
    rfq_accept = re.fullmatch(r"(?:/)?accept\s+([A-Za-z0-9_-]{4,16})", command, re.I)
    if rfq_accept:
        return await accept_telegram_rfq(services, supplier, rfq_accept.group(1))
    quote_start = re.fullmatch(r"/quote(?:@[A-Za-z0-9_]+)?(?:\s+([A-Za-z0-9_-]{4,16}))?", command, re.I)
    if quote_start:
        return await begin_telegram_quote(services, telegram_user_id, supplier, quote_start.group(1))
    if command.casefold() in {"/orders", "orders"}:
        return await telegram_orders(services, supplier)
    order_reply = await telegram_order_action(services, supplier, telegram_user_id, command)
    if order_reply is not None:
        return order_reply

    if command.upper() in {"STATUS", "/STATUS"}:
        return await supplier_status(services, supplier["id"])
    match = PRICE_COMMAND.fullmatch(command)
    if not match:
        return "I couldn't read that. Use STATUS or PRICE <exact item name> <new unit price>. Send HELP for commands."
    item, price = match.group(1).strip(), match.group(2)
    try:
        amount = Decimal(str(price))
        if not amount.is_finite() or amount <= 0 or amount > Decimal("999999999999.99"):
            raise InvalidOperation
        amount_text = f"{amount:.2f}"
    except (InvalidOperation, ValueError):
        return "Please provide a positive unit price, for example: PRICE bottled water 2.50."
    quotes = await services.store.find("quotes", supplier_id=supplier["id"], status="submitted")
    matched = [(quote, find_item_line(quote, str(item))) for quote in quotes]
    matched = [(quote, line) for quote, line in matched if line]
    if len(matched) != 1:
        if len(matched) > 1:
            return "That item appears in multiple active quotes; select the mission in the ReliefMesh portal."
        return "I couldn't find that exact item in an active submitted quote. Check the item name in your supplier portal."
    quote, line_result = matched[0]
    line_index, line = line_result
    mission = await services.store.get("missions", quote["mission_id"])
    if not mission:
        return "The mission for this quote is unavailable. Contact the coordinator."
    code = f"{secrets.randbelow(1_000_000):06d}"
    action = {
        "id": new_id(), "telegram_user_id": telegram_user_id, "supplier_id": supplier["id"],
        "quote_id": quote["id"], "mission_id": mission["id"], "quote_version": quote.get("version", 1),
        "line_index": line_index, "item": line["item"], "unit_price": amount_text,
        "code_hash": hashlib.sha256(code.encode()).hexdigest(), "status": "pending",
        "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(), "created_at": now_iso(),
    }
    await services.store.insert("telegram_pending_actions", action)
    return (f"Confirm {line['item']}: ${line['unit_price']} → ${amount_text} per unit? "
            f"Reply CONFIRM {code} within 5 minutes. No change is made until confirmed.")


async def telegram_send_message(services: Services, chat_id: int | str, text: str) -> None:
    bot_token = secret(services.settings.telegram_bot_token)
    if not bot_token:
        raise HTTPException(status_code=503, detail="Telegram bot is not configured")
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        async with services.hub.client(timeout=10) as client:
            response = await client.post(url, json={"chat_id": chat_id, "text": text[:4000]})
            response.raise_for_status()
            if not response.json().get("ok"):
                raise ValueError("Telegram rejected sendMessage")
    except (httpx.HTTPError, ValueError, TypeError):
        # Do not propagate exception details because Telegram's token is embedded in the API URL.
        raise HTTPException(status_code=502, detail="Telegram could not send the bot reply") from None


async def process_telegram_update(update: dict[str, Any], services: Services) -> None:
    """Process one Telegram update for either webhook or private local polling mode."""
    if not isinstance(update, dict) or not isinstance(update.get("update_id"), (int, str)):
        return
    update_id = str(update["update_id"])
    async with services.telegram_locks[update_id]:
        record = {"id": update_id, "status": "processing", "created_at": now_iso()}
        try:
            # Reserve the update before any mutation. The unique Mongo index makes a redelivery to another worker
            # (Telegram retries until it sees a 2xx) a no-op instead of a second quote change.
            await services.store.insert("telegram_updates", record)
        except (DuplicateKeyError, ValueError):
            return
        # Only new messages are commands; an edit must not replay CONFIRM/SUBMIT under a new update_id.
        message = update.get("message")
        sender = (message or {}).get("from") or {}
        chat = (message or {}).get("chat") or {}
        text = (message or {}).get("text")
        if (not isinstance(message, dict) or sender.get("is_bot") or not isinstance(text, str)
                or not isinstance(sender.get("id"), (int, str))):
            record.update(status="ignored")
            await services.store.replace("telegram_updates", update_id, record)
            return
        record["telegram_user_id"] = str(sender["id"])
        if chat.get("type") != "private":
            reply = "For privacy, use ReliefMesh in a private chat with this bot."
        else:
            try:
                reply = await reply_for_telegram(services, str(sender["id"]), text[:1200])
            except Exception:
                logger.exception("Telegram update processing failed")
                reply = "ReliefMesh couldn't process that message right now. Please retry or use the supplier portal."
        record.update(reply=reply[:4000], status="processed", processed_at=now_iso())
        await services.store.replace("telegram_updates", update_id, record)
        try:
            await telegram_send_message(services, chat.get("id", sender["id"]), reply)
        except HTTPException:
            # The update is already applied and recorded; a failed reply must not make Telegram redeliver it.
            record.update(status="reply_failed")
            await services.store.replace("telegram_updates", update_id, record)
            return
        record.update(status="replied")
        await services.store.replace("telegram_updates", update_id, record)


async def poll_telegram_updates(services: Services) -> None:
    """Long-poll Telegram for local demos so no public tunnel or webhook is needed."""
    token = secret(services.settings.telegram_bot_token)
    if not token:
        return
    offset: int | None = None
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    while True:
        try:
            async with services.hub.client(timeout=40) as client:
                response = await client.get(url, params={
                    "timeout": 30,
                    "allowed_updates": '["message"]',
                    **({"offset": offset} if offset is not None else {}),
                })
                response.raise_for_status()
                payload = response.json()
                if not payload.get("ok") or not isinstance(payload.get("result"), list):
                    raise ValueError("Telegram returned an invalid updates response")
                for update in payload["result"]:
                    await process_telegram_update(update, services)
                    if isinstance(update.get("update_id"), int):
                        offset = max(offset or 0, update["update_id"] + 1)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Avoid logging request URLs, which include the private bot token.
            await asyncio.sleep(3)


@router.post("/v1/supplier/telegram/link-code")
async def create_telegram_link_code(user: dict = Depends(current_user),
                                   services: Services = Depends(get_services)) -> dict[str, Any]:
    if user.get("role") != "supplier":
        raise HTTPException(status_code=403, detail="Supplier access required")
    supplier = await ensure_supplier(services, user)
    code = secrets.token_urlsafe(9)
    now = datetime.now(UTC)
    for old in await services.store.find("telegram_link_tokens", supplier_id=supplier["id"], status="pending"):
        old.update(status="superseded", updated_at=now_iso())
        await services.store.replace("telegram_link_tokens", old["id"], old)
    token = {"id": new_id(), "supplier_id": supplier["id"], "code_hash": token_hash(code),
             "status": "pending", "expires_at": (now + timedelta(minutes=10)).isoformat(),
             "created_at": now.isoformat()}
    await services.store.insert("telegram_link_tokens", token)
    username = (services.settings.telegram_bot_username or "").strip().removeprefix("@")
    bot_url = f"https://t.me/{username}?start={code}" if username else None
    return {"code": code, "expires_at": token["expires_at"], "bot_username": username or None,
            "bot_url": bot_url,
            "instruction": "Open the ReliefMesh Telegram bot and send /start <code>. This code expires in 10 minutes."}


@router.delete("/v1/supplier/telegram")
async def disconnect_telegram(user: dict = Depends(current_user),
                              services: Services = Depends(get_services)) -> dict[str, bool]:
    """Disconnect only the authenticated supplier's Telegram identity."""
    if user.get("role") != "supplier":
        raise HTTPException(status_code=403, detail="Supplier access required")
    supplier = await ensure_supplier(services, user)
    telegram_user_id = supplier.pop("telegram_user_id", None)
    supplier["updated_at"] = now_iso()
    await services.store.replace("suppliers", supplier["id"], supplier)
    if telegram_user_id:
        subscription = await services.store.get("telegram_subscriptions", str(telegram_user_id))
        if subscription and subscription.get("supplier_id") == supplier["id"]:
            subscription.update(active=False, disconnected_at=now_iso(), updated_at=now_iso())
            await services.store.replace("telegram_subscriptions", str(telegram_user_id), subscription)
    for pending in await services.store.find("telegram_link_tokens", supplier_id=supplier["id"], status="pending"):
        pending.update(status="revoked", updated_at=now_iso())
        await services.store.replace("telegram_link_tokens", pending["id"], pending)
    for action in await services.store.find("telegram_pending_actions", supplier_id=supplier["id"], status="pending"):
        action.update(status="cancelled", updated_at=now_iso())
        await services.store.replace("telegram_pending_actions", action["id"], action)
    await audit("supplier.telegram_disconnected", user["id"], None, None, "supplier", supplier["id"], services)
    return {"disconnected": True}


@router.post("/v1/webhooks/telegram")
async def receive_telegram_update(request: Request, services: Services = Depends(get_services)) -> dict[str, bool]:
    expected_secret = secret(services.settings.telegram_webhook_secret)
    if not expected_secret or not secret(services.settings.telegram_bot_token):
        raise HTTPException(status_code=503, detail="Telegram webhook is not configured")
    supplied_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(supplied_secret, expected_secret):
        raise HTTPException(status_code=403, detail="Invalid Telegram webhook secret")
    try:
        update = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid Telegram update") from None
    if not isinstance(update, dict) or not isinstance(update.get("update_id"), (int, str)):
        raise HTTPException(status_code=400, detail="Missing Telegram update id")
    await process_telegram_update(update, services)
    return {"ok": True}
