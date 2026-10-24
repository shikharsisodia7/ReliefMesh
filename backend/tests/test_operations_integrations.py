"""Operations integrations: Gmail, Google Calendar, Drive, and Slack against mocked providers.

The fake providers below speak the real wire formats (OAuth token endpoint, Gmail messages.send
with a base64url RFC 5322 body, Calendar events with client-chosen ids, Drive multipart upload,
Slack Web API envelopes). Nothing here touches the network.
"""

from __future__ import annotations

import base64
import email
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email import policy
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest

from app.main import create_app
from app.operations import templates
from app.integrations import google_calendar
from conftest import FakeUpstream, auth, make_settings, register, settle_jobs, wait_for

ALL_SCOPES = ("openid https://www.googleapis.com/auth/userinfo.email "
              "https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/calendar.app.created "
              "https://www.googleapis.com/auth/drive.file")


@dataclass
class FakeProviders:
    upstream: FakeUpstream
    granted_scope: str = ALL_SCOPES
    refresh_invalid: bool = False
    gmail_failures: list[int] = field(default_factory=list)
    gmail_fail_subject: str = ""  # inject failures only into messages whose subject contains this
    slack_failures: list[Any] = field(default_factory=list)  # HTTP status or Slack error string
    gmail_sent: list[dict[str, Any]] = field(default_factory=list)
    calendar_events: dict[str, dict[str, Any]] = field(default_factory=dict)
    calendar_inserts: int = 0
    slack_posts: list[dict[str, Any]] = field(default_factory=list)
    slack_updates: list[dict[str, Any]] = field(default_factory=list)
    drive_files: dict[str, dict[str, Any]] = field(default_factory=dict)
    token_requests: list[dict[str, str]] = field(default_factory=list)
    counter: int = 0

    def next_id(self, prefix: str) -> str:
        self.counter += 1
        return f"{prefix}{self.counter}"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        host, path = request.url.host, request.url.path
        if host == "oauth2.googleapis.com":
            return self.google_token(request, path)
        if host == "gmail.googleapis.com":
            message = email.message_from_bytes(base64.urlsafe_b64decode(json.loads(request.content)["raw"]),
                                               policy=policy.default)
            if self.gmail_failures and self.gmail_fail_subject in message["Subject"]:
                return httpx.Response(self.gmail_failures.pop(0), json={"error": {"status": "UNAVAILABLE"}})
            self.gmail_sent.append({"message": message, "auth": request.headers["Authorization"]})
            return httpx.Response(200, json={"id": self.next_id("msg-"), "threadId": "thread-1"})
        if host == "www.googleapis.com" and path.startswith("/calendar/v3"):
            return self.calendar(request, path)
        if host == "www.googleapis.com" and ("/drive/v3" in path):
            return self.drive(request, path)
        if host == "slack.com":
            return self.slack(request, path)
        if host == "hooks.slack.com":
            return httpx.Response(200, text="ok")
        return self.upstream(request)

    def google_token(self, request: httpx.Request, path: str) -> httpx.Response:
        if path == "/revoke":
            return httpx.Response(200, json={})
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        self.token_requests.append(form)
        if form["grant_type"] == "authorization_code":
            assert form["code_verifier"], "PKCE verifier must be sent"
            id_token = jwt.encode({"email": "ops@relief.example.org", "email_verified": True}, "x", algorithm="HS256")
            return httpx.Response(200, json={"access_token": "ya29.first", "expires_in": 3599,
                                             "refresh_token": "1//refresh", "scope": self.granted_scope,
                                             "token_type": "Bearer", "id_token": id_token})
        if self.refresh_invalid:
            return httpx.Response(400, json={"error": "invalid_grant", "error_description": "Token has been expired"})
        return httpx.Response(200, json={"access_token": self.next_id("ya29.refreshed-"), "expires_in": 3599,
                                         "scope": self.granted_scope, "token_type": "Bearer"})

    def calendar(self, request: httpx.Request, path: str) -> httpx.Response:
        if path == "/calendar/v3/calendars" and request.method == "POST":
            return httpx.Response(200, json={"id": "reliefmesh-cal@group.calendar.google.com",
                                             "summary": json.loads(request.content)["summary"]})
        parts = path.split("/")
        if len(parts) == 5 and request.method == "GET":  # /calendar/v3/calendars/{id}
            return httpx.Response(200, json={"id": parts[4]})
        if path.endswith("/events") and request.method == "POST":
            body = json.loads(request.content)
            existing = self.calendar_events.get(body["id"])
            if existing:
                return httpx.Response(409, json={"error": {"status": "ALREADY_EXISTS",
                                                            "message": "The requested identifier already exists."}})
            self.calendar_inserts += 1
            self.calendar_events[body["id"]] = body
            return httpx.Response(200, json={**body, "htmlLink": f"https://calendar.google.com/event?eid={body['id']}"})
        event_id = parts[-1]
        if request.method == "PUT":
            self.calendar_events[event_id] = json.loads(request.content)
            return httpx.Response(200, json={**self.calendar_events[event_id], "htmlLink": "https://calendar/x"})
        if request.method == "DELETE":
            if event_id not in self.calendar_events or self.calendar_events[event_id].get("status") == "cancelled":
                return httpx.Response(410, json={"error": {"status": "GONE"}})
            self.calendar_events[event_id]["status"] = "cancelled"
            return httpx.Response(204)
        return httpx.Response(404, json={"error": {"status": "NOT_FOUND"}})

    def drive(self, request: httpx.Request, path: str) -> httpx.Response:
        if request.method == "GET":
            file_id = path.rsplit("/", 1)[-1]
            row = self.drive_files.get(file_id)
            return httpx.Response(200, json=row) if row else httpx.Response(404, json={"error": {"code": 404}})
        if path == "/drive/v3/files":  # folder metadata create
            body = json.loads(request.content)
            file_id = self.next_id("folder-")
            self.drive_files[file_id] = {"id": file_id, **body, "webViewLink": f"https://drive/{file_id}"}
            return httpx.Response(200, json=self.drive_files[file_id])
        raw = request.content
        metadata = json.loads(raw.split(b"\r\n\r\n", 1)[1].split(b"\r\n", 1)[0])
        if request.method == "PATCH":
            file_id = path.rsplit("/", 1)[-1]
            self.drive_files[file_id].update(metadata, bytes=len(raw), version=self.drive_files[file_id]["version"] + 1)
        else:
            file_id = self.next_id("file-")
            self.drive_files[file_id] = {"id": file_id, **metadata, "bytes": len(raw), "version": 1,
                                         "webViewLink": f"https://drive/{file_id}"}
        return httpx.Response(200, json=self.drive_files[file_id])

    def slack(self, request: httpx.Request, path: str) -> httpx.Response:
        method = path.rsplit("/", 1)[-1]
        if method == "oauth.v2.access":
            return httpx.Response(200, json={"ok": True, "access_token": "xoxb-installed", "team": {
                "id": "T1", "name": "Relief Ops"}, "incoming_webhook": {
                "channel": "#relief-operations", "channel_id": "C777", "url": "https://hooks.slack.com/services/T/B/x"}})
        if method == "auth.test":
            return httpx.Response(200, json={"ok": True, "team": "Relief Ops", "team_id": "T1", "user_id": "U1"})
        if method in {"chat.postMessage", "chat.update"} and self.slack_failures:
            failure = self.slack_failures.pop(0)
            if isinstance(failure, int):
                return httpx.Response(failure, headers={"Retry-After": "1"}, text="")
            return httpx.Response(200, json={"ok": False, "error": failure})
        body = json.loads(request.content)
        if method == "chat.postMessage":
            ts = f"1729.{self.next_id('')}"
            self.slack_posts.append({**body, "ts": ts})
            return httpx.Response(200, json={"ok": True, "channel": "C777", "ts": ts})
        if method == "chat.update":
            self.slack_updates.append(body)
            return httpx.Response(200, json={"ok": True, "channel": body["channel"], "ts": body["ts"]})
        if method == "auth.revoke":
            return httpx.Response(200, json={"ok": True, "revoked": True})
        return httpx.Response(200, json={"ok": False, "error": "unknown_method"})


def ops_settings(**overrides: Any):
    values = dict(google_oauth_client_id="client-123.apps.googleusercontent.com",
                  google_oauth_client_secret="secret", public_api_url="http://api.test", ops_retry_base_seconds=0.01)
    values.update(overrides)
    return make_settings(**values)


@pytest.fixture
def providers(upstream: FakeUpstream) -> FakeProviders:
    return FakeProviders(upstream=upstream)


@pytest.fixture
async def ops_client(providers: FakeProviders):
    app = create_app(ops_settings(), http_transport=httpx.MockTransport(providers))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            yield app, client


async def connect_google(client: httpx.AsyncClient, token: str, organization_id: str) -> httpx.Response:
    started = await client.post(f"/v1/organizations/{organization_id}/integrations/google/connect",
                                headers=auth(token))
    assert started.status_code == 200, started.text
    query = parse_qs(urlparse(started.json()["authorization_url"]).query)
    assert query["access_type"] == ["offline"] and query["code_challenge_method"] == ["S256"]
    assert set(query["scope"][0].split()) >= {"https://www.googleapis.com/auth/gmail.send",
                                              "https://www.googleapis.com/auth/calendar.app.created",
                                              "https://www.googleapis.com/auth/drive.file"}
    return await client.get(f"/v1/integrations/google/callback?code=auth-code&state={query['state'][0]}")


async def connect_slack(client: httpx.AsyncClient, token: str, organization_id: str) -> httpx.Response:
    return await client.put(f"/v1/organizations/{organization_id}/integrations/slack",
                            json={"bot_token": "xoxb-manual", "channel": "#relief-operations"}, headers=auth(token))


async def settle_deliveries(app, mission_id: str | None = None) -> list[dict[str, Any]]:
    store = app.state.services.store

    async def done():
        rows = await store.find("ops_deliveries", mission_id=mission_id) if mission_id else \
            await store.find("ops_deliveries")
        return {"rows": rows} if all(r["status"] not in {"PENDING", "SENDING", "RETRYING"} for r in rows) else None
    return (await wait_for(done, attempts=400))["rows"]


async def build_mission(client: httpx.AsyncClient) -> dict[str, Any]:
    coordinator = await register(client, "coord@relief.example.org", "coordinator")
    approver = await register(client, "approver@relief.example.org", "coordinator")
    suppliers = [await register(client, f"{name}@supply.example.com", "supplier") for name in ("bayside", "sierra")]
    organization_id = (await client.post("/v1/organizations", json={"name": "Oakland Relief"},
                                         headers=auth(coordinator))).json()["id"]
    invite = await client.post(f"/v1/organizations/{organization_id}/members",
                               json={"email": "approver@relief.example.org", "role": "approver"},
                               headers=auth(coordinator))
    await client.post(f"/v1/org-invites/{invite.json()['invite_url'].rsplit('/', 1)[1]}/accept",
                      headers=auth(approver))
    return {"coordinator": coordinator, "approver": approver, "suppliers": suppliers,
            "organization_id": organization_id}


async def create_mission(client: httpx.AsyncClient, ctx: dict[str, Any], days: int = 10) -> str:
    mission = await client.post("/v1/missions", headers=auth(ctx["coordinator"]), json={
        "organization_id": ctx["organization_id"], "name": "Oakland Shelter Supplies",
        "delivery_location": "Oakland, CA", "delivery_deadline": (datetime.now(UTC) + timedelta(days=days)).isoformat(),
        "budget": "100.00", "currency": "USD", "requirements": [{"item": "blankets", "quantity": 10}]})
    assert mission.status_code == 201, mission.text
    return mission.json()["id"]


async def quote_and_plan(client: httpx.AsyncClient, ctx: dict[str, Any], mission_id: str) -> tuple[list[str], str]:
    tokens = []
    for name in ("bayside", "sierra"):
        invitation = await client.post(f"/v1/missions/{mission_id}/invitations", headers=auth(ctx["coordinator"]),
                                       json={"supplier_email": f"{name}@supply.example.com"})
        tokens.append(invitation.json()["token"])
    quote_ids = []
    for token, supplier, price, name in zip(tokens, ctx["suppliers"], ("7.00", "9.00"),
                                            ("Bayside Relief Supply Co", "Sierra Backup Provisions"), strict=True):
        await client.post(f"/v1/supplier-invitations/{token}/accept", headers=auth(supplier))
        quote = await client.post("/v1/quotes", headers=auth(supplier), json={
            "invitation_token": token, "expires_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
            "shipping_cost": "10.00" if price == "7.00" else "0.00",
            "lines": [{"item": "blankets", "unit_price": price, "available_quantity": 10,
                       "delivery_date": (datetime.now(UTC) + timedelta(days=3)).isoformat()}],
            "supplier_profile": {"legal_name": name, "country": "US"}})
        assert quote.status_code == 201, quote.text
        quote_ids.append(quote.json()["id"])
    await settle_jobs(client, ctx["coordinator"], mission_id)
    await client.post(f"/v1/missions/{mission_id}/evidence/refresh", headers=auth(ctx["coordinator"]))
    await settle_jobs(client, ctx["coordinator"], mission_id)
    optimized = await client.post(f"/v1/missions/{mission_id}/optimize", headers=auth(ctx["coordinator"]))
    assert optimized.status_code == 202, optimized.text
    return quote_ids, optimized.json()["plan_id"]


# ---------------------------------------------------------------- payload generation

def sample_mission() -> dict[str, Any]:
    return {"id": "m1", "organization_id": "o1", "name": "Oakland Shelter <Supplies>", "delivery_location": "Oakland, CA",
            "delivery_deadline": "2026-10-30T18:00:00+00:00", "budget": "5000.00",
            "requirements": [{"item": "blankets", "quantity": 500}, {"item": "water", "quantity": 1200}]}


def sample_plan(version: int = 1, **extra: Any) -> dict[str, Any]:
    return {"id": f"p{version}", "version": version, "status": "feasible", "total_cost": "3271.00",
            "allocations": [{"supplier_id": "s1", "quote_id": "q1", "item": "blankets", "quantity": 500},
                            {"supplier_id": "s2", "quote_id": "q2", "item": "water", "quantity": 1200}],
            "difference": {}, **extra}


def test_email_payloads_carry_the_required_fields_and_escape_input() -> None:
    mission = sample_mission()
    subject, html, text = templates.rfq_email({"name": "Oakland Relief"}, mission, "https://rm.app/invitations/tok")
    assert subject == "Urgent RFQ — ReliefMesh Mission Oakland Shelter <Supplies>"
    assert "&lt;Supplies&gt;" in html and "<Supplies>" not in html  # escaped in HTML
    for needle in ("Oakland Relief", "Oakland, CA", "500 × blankets", "1,200 × water", "https://rm.app/invitations/tok"):
        assert needle in text
    subject, html, text = templates.approval_email(mission, sample_plan(), "https://rm.app/missions/m1",
                                                   "2026-10-29T10:00:00+00:00")
    assert subject == "Approval Required — ReliefMesh Plan V1"
    assert "$3,271.00" in text and "Suppliers: 2" in text and "https://rm.app/missions/m1" in text
    replanned = sample_plan(2, total_cost="3466.00", difference={
        "total_cost_before": "3271.00", "cost_delta": "+195.00", "why": ["Bayside Relief Supply Co withdrew its quote"],
        "supplier_delta": [{"supplier": "Bayside Relief Supply Co", "units_before": 500, "units_after": 0},
                           {"supplier": "Sierra Backup Provisions", "units_before": 0, "units_after": 500}]})
    subject, _, text = templates.replan_email(mission, replanned, "https://rm.app/missions/m1", None)
    assert subject == "New Procurement Plan Ready for Approval"
    for needle in ("Old cost: $3,271.00", "New cost: $3,466.00", "Cost delta: +$195.00",
                   "Removed suppliers: Bayside Relief Supply Co", "Added suppliers: Sierra Backup Provisions"):
        assert needle in text
    subject, _, text = templates.disruption_email(mission, {
        "supplier": "Bayside Relief Supply Co", "failure_type": "Supplier withdrew its quote",
        "reason": "Bayside Relief Supply Co withdrew its quote", "stale_versions": [1], "approvals_invalidated": 1},
        "https://rm.app/missions/m1")
    assert subject == "URGENT — Supply Chain Disruption" and "V1 — now STALE" in text
    order = {"id": "po1", "po_number": "RM-1", "buyer_organization": "Oakland Relief", "delivery_location": "Oakland",
             "subtotal": "70.00", "plan_version": 2, "plan_hash": "abc" * 10,
             "lines": [{"item": "blankets", "quantity": 10, "unit_price": "7.00", "line_cost": "70.00",
                        "delivery_date": "2026-10-28T00:00:00+00:00"}]}
    subject, _, text = templates.purchase_order_email(order, mission, "https://rm.app/supplier")
    assert subject == "Purchase Order — ReliefMesh RM-1" and "https://rm.app/supplier" in text


def test_slack_payloads_link_back_and_never_offer_an_approval_action() -> None:
    mission = sample_mission()
    payloads = [templates.slack_approval(mission, sample_plan(), "https://rm.app/missions/m1", None),
                templates.slack_replan(mission, sample_plan(2), "https://rm.app/missions/m1"),
                templates.slack_disruption(mission, {"supplier": "Bayside", "failure_type": "withdrew",
                                                     "reason": "Bayside withdrew", "stale_versions": [1],
                                                     "approvals_invalidated": 1}, "https://rm.app/missions/m1")]
    for text, blocks in payloads:
        assert text
        serialized = json.dumps(blocks)
        assert "action_id" not in serialized and "/approve" not in serialized
        buttons = [el for block in blocks if block["type"] == "actions" for el in block["elements"]]
        assert buttons and all(button.get("url", "").startswith("https://rm.app/") for button in buttons)
    disruption_text = json.dumps(payloads[2][1])
    assert "STALE" in disruption_text and "INVALIDATED" in disruption_text and "replanning has started" in disruption_text
    escaped = templates.slack_approval({**mission, "name": "<!channel> & co"}, sample_plan(), "https://rm.app/x", None)
    assert "<!channel>" not in json.dumps(escaped[1]) and "&lt;!channel&gt; &amp; co" in json.dumps(escaped[1])


def test_calendar_bodies_and_deterministic_event_ids() -> None:
    mission = sample_mission()
    deadline = templates.calendar_deadline(mission, "https://rm.app/missions/m1")
    assert deadline["summary"] == "ReliefMesh — Delivery Deadline: Oakland Shelter <Supplies>"
    assert deadline["end"]["dateTime"].startswith("2026-10-30T18:00:00")
    assert "500 × blankets" in deadline["description"] and "https://rm.app/missions/m1" in deadline["description"]
    quotes = [{"id": "q1", "expires_at": "2026-10-29T09:00:00+00:00"}, {"id": "q9", "expires_at": "2026-10-25T00:00:00Z"}]
    due = templates.approval_due(mission, quotes, sample_plan())  # unallocated q9 must not count
    assert due.startswith("2026-10-29T09:00:00")
    approval = templates.calendar_approval(mission, sample_plan(), due, "https://rm.app/x")
    assert approval["summary"] == "ReliefMesh — Approval Required: Oakland Shelter <Supplies> (Plan V1)"
    first = google_calendar.event_id("o1", "m1", "approval")
    assert first == google_calendar.event_id("o1", "m1", "approval") != google_calendar.event_id("o1", "m1", "deadline")
    assert set(first) <= set("abcdefghijklmnopqrstuv0123456789") and 5 <= len(first) <= 1024


# ---------------------------------------------------------------- OAuth + settings

@pytest.mark.anyio
async def test_google_oauth_connects_with_pkce_and_reports_only_granted_capabilities(ops_client, providers) -> None:
    app, client = ops_client
    ctx = await build_mission(client)
    providers.granted_scope = "openid https://www.googleapis.com/auth/gmail.send"  # user unticked Calendar + Drive
    callback = await connect_google(client, ctx["coordinator"], ctx["organization_id"])
    assert callback.status_code == 303 and "google=connected" in callback.headers["location"]
    replay = await client.get(callback.request.url.path + "?" + callback.request.url.query.decode())
    assert replay.status_code == 400  # state is single use
    view = (await client.get(f"/v1/organizations/{ctx['organization_id']}/integrations",
                             headers=auth(ctx["coordinator"]))).json()
    assert view["google"]["status"] == "CONNECTED" and view["google"]["account_email"] == "ops@relief.example.org"
    assert view["google"]["capabilities"]["gmail"]["state"] == "DEGRADED"  # connected, nothing sent yet
    assert view["google"]["capabilities"]["calendar"]["state"] == "NOT_CONFIGURED"
    stored = await app.state.services.store.get("integration_connections", f"{ctx['organization_id']}:google")
    assert "ya29" not in json.dumps(stored) and "1//refresh" not in json.dumps(stored)  # encrypted at rest
    approver_attempt = await client.post(f"/v1/organizations/{ctx['organization_id']}/integrations/google/connect",
                                         headers=auth(ctx["approver"]))
    assert approver_attempt.status_code == 403  # only admins manage integrations


@pytest.mark.anyio
async def test_unconfigured_server_reports_not_configured_never_connected(client) -> None:
    coordinator = await register(client, "solo@relief.example.org", "coordinator")
    organization_id = (await client.post("/v1/organizations", json={"name": "Solo"},
                                         headers=auth(coordinator))).json()["id"]
    connect = await client.post(f"/v1/organizations/{organization_id}/integrations/google/connect",
                                headers=auth(coordinator))
    assert connect.status_code == 503 and "NOT_CONFIGURED" in connect.text
    view = (await client.get(f"/v1/organizations/{organization_id}/integrations", headers=auth(coordinator))).json()
    assert view["google"]["status"] == "NOT_CONFIGURED"
    assert all(cap["state"] == "NOT_CONFIGURED" for cap in view["google"]["capabilities"].values())
    assert view["slack"]["state"] == "NOT_CONFIGURED"
    status = (await client.get("/v1/integrations/status?refresh=true")).json()
    by_id = {row["id"]: row for row in status["integrations"]}
    assert {by_id[key]["status"] for key in ("gmail", "google_calendar", "google_drive", "slack")} == {"not_configured"}


# ---------------------------------------------------------------- the full operations workflow

@pytest.mark.anyio
async def test_full_workflow_fans_out_idempotent_notifications(ops_client, providers) -> None:
    app, client = ops_client
    store = app.state.services.store
    ctx = await build_mission(client)
    assert (await connect_google(client, ctx["coordinator"], ctx["organization_id"])).status_code == 303
    assert (await connect_slack(client, ctx["coordinator"], ctx["organization_id"])).status_code == 200
    mission_id = await create_mission(client, ctx)
    await settle_deliveries(app, mission_id)
    deadline_id = google_calendar.event_id(ctx["organization_id"], mission_id, "deadline")
    assert providers.calendar_events[deadline_id]["summary"] == "ReliefMesh — Delivery Deadline: Oakland Shelter Supplies"

    quote_ids, plan_id = await quote_and_plan(client, ctx, mission_id)
    rows = await settle_deliveries(app, mission_id)
    v1 = [r for r in rows if r["event_type"] == "approval_required"]
    assert {(r["channel"], r["status"]) for r in v1} == {("gmail", "TEST"), ("slack", "SENT"), ("calendar", "SENT")}
    # Segregation of duties: only the independent approver is asked to approve.
    assert [r["target"] for r in v1 if r["channel"] == "gmail"] == ["approver@relief.example.org"]
    approval_id = google_calendar.event_id(ctx["organization_id"], mission_id, "approval")
    assert providers.calendar_events[approval_id]["summary"].endswith("(Plan V1)")
    approval_post = next(p for p in providers.slack_posts if "approval required" in p["text"])

    # A duplicated application event creates nothing new.
    plan = await store.get("plans", plan_id)
    mission = await store.get("missions", mission_id)
    before = len(await store.find("ops_deliveries"))
    await app.state.services.ops.emit("approval_required", mission, subject_id=plan_id, version=plan["version"],
                                      data={"plan_id": plan_id})
    assert len(await store.find("ops_deliveries")) == before

    assert (await client.post(f"/v1/plans/{plan_id}/approve", headers=auth(ctx["approver"]))).status_code == 201
    await settle_deliveries(app, mission_id)
    assert providers.calendar_events[approval_id]["summary"].startswith("Approved — ReliefMesh Plan V1")

    withdrawn = await client.post(f"/v1/quotes/{quote_ids[0]}/withdraw", headers=auth(ctx["suppliers"][0]))
    assert withdrawn.status_code == 202
    await settle_jobs(client, ctx["coordinator"], mission_id)
    rows = await settle_deliveries(app, mission_id)
    disruption = [r for r in rows if r["event_type"] == "supplier_disrupted"]
    assert {r["channel"] for r in disruption} == {"gmail", "slack", "calendar"}
    assert all(r["status"] in {"SENT", "TEST", "SKIPPED"} for r in disruption)
    slack_alert = next(p for p in providers.slack_posts if "Supplier disruption" in p["text"])
    assert "Bayside Relief Supply Co" in json.dumps(slack_alert["blocks"]) and "STALE" in json.dumps(slack_alert["blocks"])
    assert any(u["ts"] == approval_post["ts"] for u in providers.slack_updates)  # old approval post struck through

    replanned = [r for r in rows if r["event_type"] == "plan_replanned"]
    assert {(r["channel"], r["status"]) for r in replanned} == {("gmail", "TEST"), ("slack", "SENT"),
                                                                ("calendar", "SENT")}
    # Plan V1 -> V2 replaces the one approval event; it is never duplicated.
    assert providers.calendar_events[approval_id]["summary"].endswith("(Plan V2)")
    assert sum(1 for key in providers.calendar_events if key == approval_id) == 1
    replan_post = next(p for p in providers.slack_posts if "rebuilt the supply plan" in p["text"])
    assert "+$10.00" in replan_post["text"]
    outbox = await store.find("email_outbox")
    assert any(row["subject"] == "New Procurement Plan Ready for Approval" for row in outbox)
    assert any(row["subject"] == "URGENT — Supply Chain Disruption" for row in outbox)

    plans = sorted(await store.find("plans", mission_id=mission_id), key=lambda p: p["version"])
    v2 = plans[-1]
    assert (await client.post(f"/v1/plans/{v2['id']}/approve", headers=auth(ctx["approver"]))).status_code == 201
    orders = await client.post(f"/v1/plans/{v2['id']}/purchase-orders",
                               headers={**auth(ctx["coordinator"]), "Idempotency-Key": "po-ops-1"})
    order = orders.json()[0]
    sent = await client.post(f"/v1/purchase-orders/{order['id']}/send", json={"confirm": True},
                             headers=auth(ctx["coordinator"]))
    assert sent.status_code == 200, sent.text
    po_mail = next(row for row in await store.find("email_outbox") if row["subject"].startswith("Purchase Order"))
    assert po_mail["to"] == "sierra@supply.example.com" and po_mail["attachments"][0]["filename"].endswith(".pdf")
    accepted = await client.post(f"/v1/purchase-orders/{order['id']}/supplier-response", json={"accepted": True},
                                 headers=auth(ctx["suppliers"][1]))
    assert accepted.status_code == 200
    await client.post(f"/v1/purchase-orders/{order['id']}/fulfillment",
                      json={"status": "completed", "note": "Delivered to shelter dock 3"},
                      headers=auth(ctx["suppliers"][1]))
    rows = await settle_deliveries(app, mission_id)
    assert any("Purchase order issued" in p["text"] for p in providers.slack_posts)
    eta_id = google_calendar.event_id(ctx["organization_id"], mission_id, f"eta:{order['id']}")
    assert providers.calendar_events[eta_id]["summary"].startswith("Delivered — Sierra Backup Provisions")
    archived = {r["target"]: r for r in rows if r["channel"] == "drive"}
    assert {"plan:v1", "plan:v2", f"po:{order['id']}", "audit"} <= set(archived)
    assert all(r["status"] == "SENT" and r["provider_url"] for r in archived.values())
    names = {row.get("name") for row in providers.drive_files.values()}
    assert {"ReliefMesh", "Missions", "Oakland Shelter Supplies", "Plan-V2.pdf", "Audit-Export.json"} <= names
    view = (await client.get(f"/v1/organizations/{ctx['organization_id']}/integrations",
                             headers=auth(ctx["coordinator"]))).json()
    assert view["slack"]["state"] == "LIVE" and view["google"]["capabilities"]["calendar"]["state"] == "LIVE"
    assert view["google"]["capabilities"]["drive"]["state"] == "LIVE"
    assert all("payload" not in row for row in view["deliveries"])  # rendered bodies are not exposed


# ---------------------------------------------------------------- live Gmail, failures, retries

@pytest.mark.anyio
async def test_live_gmail_sends_rfq_through_the_org_account_and_records_message_id(providers) -> None:
    app = create_app(ops_settings(email_mode="live"), http_transport=httpx.MockTransport(providers))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            ctx = await build_mission(client)
            await connect_google(client, ctx["coordinator"], ctx["organization_id"])
            mission_id = await create_mission(client, ctx)
            invitation = await client.post(f"/v1/missions/{mission_id}/invitations", headers=auth(ctx["coordinator"]),
                                           json={"supplier_email": "bayside@supply.example.com"})
            assert invitation.json()["delivery_status"] == "sent"
            message = providers.gmail_sent[-1]["message"]
            assert message["Subject"] == "Urgent RFQ — ReliefMesh Mission Oakland Shelter Supplies"
            assert message["To"] == "bayside@supply.example.com" and "ops@relief.example.org" in message["From"]
            html_part = message.get_body(("html",)).get_content()
            assert f"/invitations/{invitation.json()['token']}" in html_part
            dispatches = await client.get(f"/v1/missions/{mission_id}/email-dispatches",
                                          headers=auth(ctx["coordinator"]))
            row = dispatches.json()[0]
            assert row["provider"] == "gmail" and row["provider_id"].startswith("msg-") and row["sent_at"]


@pytest.mark.anyio
async def test_retries_then_succeeds_and_failures_never_block_procurement(providers) -> None:
    app = create_app(ops_settings(email_mode="live"), http_transport=httpx.MockTransport(providers))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            ctx = await build_mission(client)
            await connect_google(client, ctx["coordinator"], ctx["organization_id"])
            await connect_slack(client, ctx["coordinator"], ctx["organization_id"])
            providers.gmail_failures = [503, 500]  # Gmail flaps twice on the approval email, then accepts
            providers.gmail_fail_subject = "Approval Required"
            providers.slack_failures = [500, 500, 500, 500]  # Slack is down for every attempt
            mission_id = await create_mission(client, ctx)
            _, plan_id = await quote_and_plan(client, ctx, mission_id)
            rows = await settle_deliveries(app, mission_id)
            email_row = next(r for r in rows if r["event_type"] == "approval_required" and r["channel"] == "gmail")
            assert email_row["status"] == "SENT" and email_row["attempts"] == 3
            assert [h["status"] for h in email_row["history"]] == ["RETRYING", "RETRYING", "SENT"]
            slack_row = next(r for r in rows if r["event_type"] == "approval_required" and r["channel"] == "slack")
            assert slack_row["status"] == "FAILED" and slack_row["attempts"] == 4
            # Procurement is unaffected: the plan is approvable while Slack is down.
            assert (await client.post(f"/v1/plans/{plan_id}/approve", headers=auth(ctx["approver"]))).status_code == 201
            retried = await client.post(f"/v1/integrations/deliveries/{slack_row['id']}/retry",
                                        headers=auth(ctx["coordinator"]))
            assert retried.status_code == 200
            rows = await settle_deliveries(app, mission_id)
            assert next(r for r in rows if r["id"] == slack_row["id"])["status"] == "SENT"


@pytest.mark.anyio
async def test_expired_google_token_blocks_google_channels_but_not_procurement(ops_client, providers) -> None:
    app, client = ops_client
    store = app.state.services.store
    ctx = await build_mission(client)
    await connect_google(client, ctx["coordinator"], ctx["organization_id"])
    connection = await store.get("integration_connections", f"{ctx['organization_id']}:google")
    tokens = app.state.services.vault.open(connection["token_ciphertext"])
    tokens["expires_at"] = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()  # access token expired
    connection["token_ciphertext"] = app.state.services.vault.seal(tokens)
    await store.replace("integration_connections", connection["id"], connection)
    providers.refresh_invalid = True  # and the refresh token was revoked
    mission_id = await create_mission(client, ctx)
    assert (await client.get(f"/v1/missions/{mission_id}", headers=auth(ctx["coordinator"]))).status_code == 200
    rows = await settle_deliveries(app, mission_id)
    calendar_row = next(r for r in rows if r["channel"] == "calendar")
    assert calendar_row["status"] == "FAILED" and "reconnect" in calendar_row["last_error"].lower()
    assert calendar_row["attempts"] == 1  # invalid_grant is not retried
    view = (await client.get(f"/v1/organizations/{ctx['organization_id']}/integrations",
                             headers=auth(ctx["coordinator"]))).json()
    assert view["google"]["status"] == "NEEDS_REAUTH" and view["google"]["capabilities"]["calendar"]["state"] == "BLOCKED"
    health = {row["id"]: row for row in (await client.get("/v1/integrations/status?refresh=true")).json()["integrations"]}
    assert health["google_calendar"]["status"] == "error" and health["google_calendar"]["detail"].startswith("BLOCKED")
    # Reconnecting restores service.
    providers.refresh_invalid = False
    assert (await connect_google(client, ctx["coordinator"], ctx["organization_id"])).status_code == 303
    retried = await client.post(f"/v1/integrations/deliveries/{calendar_row['id']}/retry",
                                headers=auth(ctx["coordinator"]))
    assert retried.status_code == 200
    rows = await settle_deliveries(app, mission_id)
    assert next(r for r in rows if r["id"] == calendar_row["id"])["status"] == "SENT"


@pytest.mark.anyio
async def test_revoked_slack_token_marks_connection_blocked(ops_client, providers) -> None:
    app, client = ops_client
    ctx = await build_mission(client)
    await connect_slack(client, ctx["coordinator"], ctx["organization_id"])
    providers.slack_failures = ["token_revoked"]
    test = await client.post(f"/v1/organizations/{ctx['organization_id']}/integrations/test",
                             json={"channel": "slack"}, headers=auth(ctx["coordinator"]))
    assert test.json()["status"] == "FAILED" and "token_revoked" in test.json()["last_error"]
    mission_id = await create_mission(client, ctx)
    _, plan_id = await quote_and_plan(client, ctx, mission_id)
    providers.slack_failures = ["token_revoked"]
    rows = await settle_deliveries(app, mission_id)
    slack_row = next(r for r in rows if r["channel"] == "slack")
    assert slack_row["status"] == "FAILED" and "reconnect required" in slack_row["last_error"]
    view = (await client.get(f"/v1/organizations/{ctx['organization_id']}/integrations",
                             headers=auth(ctx["coordinator"]))).json()
    assert view["slack"]["state"] == "BLOCKED"
    assert (await client.post(f"/v1/plans/{plan_id}/approve", headers=auth(ctx["approver"]))).status_code == 201


@pytest.mark.anyio
async def test_email_modes_disabled_and_allowlist(providers) -> None:
    app = create_app(ops_settings(email_mode="disabled"), http_transport=httpx.MockTransport(providers))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            ctx = await build_mission(client)
            await connect_google(client, ctx["coordinator"], ctx["organization_id"])
            mission_id = await create_mission(client, ctx)
            invitation = await client.post(f"/v1/missions/{mission_id}/invitations", headers=auth(ctx["coordinator"]),
                                           json={"supplier_email": "bayside@supply.example.com"})
            assert invitation.json()["delivery_status"] == "disabled" and not providers.gmail_sent
    app = create_app(ops_settings(email_mode="live", email_allowed_recipients=["@relief.example.org"]),
                     http_transport=httpx.MockTransport(providers))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            ctx = await build_mission(client)
            await connect_google(client, ctx["coordinator"], ctx["organization_id"])
            mission_id = await create_mission(client, ctx)
            blocked = await client.post(f"/v1/missions/{mission_id}/invitations", headers=auth(ctx["coordinator"]),
                                        json={"supplier_email": "someone@real-business.example"})
            assert blocked.json()["delivery_status"] == "suppressed" and not providers.gmail_sent


@pytest.mark.anyio
async def test_mission_deadline_change_and_cancellation_update_the_same_calendar_events(ops_client, providers) -> None:
    app, client = ops_client
    ops, store = app.state.services.ops, app.state.services.store
    ctx = await build_mission(client)
    await connect_google(client, ctx["coordinator"], ctx["organization_id"])
    mission_id = await create_mission(client, ctx)
    await settle_deliveries(app, mission_id)
    deadline_id = google_calendar.event_id(ctx["organization_id"], mission_id, "deadline")
    mission = await store.get("missions", mission_id)
    mission["delivery_deadline"] = (datetime.now(UTC) + timedelta(days=4)).replace(microsecond=0).isoformat()
    await store.replace("missions", mission_id, mission)
    await ops.emit("mission_updated", mission, subject_id=mission_id, version=mission["delivery_deadline"])
    await settle_deliveries(app, mission_id)
    assert providers.calendar_events[deadline_id]["end"]["dateTime"] == mission["delivery_deadline"]
    assert providers.calendar_inserts == 1  # updated in place, not re-created
    await ops.emit("mission_cancelled", mission, subject_id=mission_id, data={"reason": "Shelter consolidated"})
    rows = await settle_deliveries(app, mission_id)
    assert providers.calendar_events[deadline_id]["status"] == "cancelled"
    assert all(r["status"] in {"SENT", "NOT_CONFIGURED"} for r in rows if r["event_type"] == "mission_cancelled")


@pytest.mark.anyio
async def test_stale_calendar_update_cannot_overwrite_a_newer_one(ops_client, providers) -> None:
    app, client = ops_client
    store, ops = app.state.services.store, app.state.services.ops
    ctx = await build_mission(client)
    await connect_google(client, ctx["coordinator"], ctx["organization_id"])
    mission_id = await create_mission(client, ctx)
    rows = await settle_deliveries(app, mission_id)
    older = next(r for r in rows if r["channel"] == "calendar")
    await store.upsert("calendar_slots", {**(await store.get("calendar_slots", older["payload"]["event_id"])),
                                          "sequence": older["sequence"] + 10})
    older.update(status="PENDING")
    await store.replace("ops_deliveries", older["id"], older)
    await ops.attempt(older["id"])
    assert (await store.get("ops_deliveries", older["id"]))["status"] == "SKIPPED"
