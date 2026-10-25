"""Regressions found in the final adversarial QA of release 9bbe49d. Each test failed before its fix.

Continuity breakpoints (engine level):
- the delay frontier searched only up to the supplier's *latest* line, so a supplier whose essential line is an
  earlier one was reported as having no delay breakpoint at all;
- the proportional capacity shock rounded in a way that was not monotone, so bisection could return a "breakpoint"
  above a smaller loss that already breaks the plan (the tolerance was overstated).

Races (API level). MemoryStore never yields to the event loop, so every handler ran atomically in the existing
tests. MongoStore awaits network I/O on every call, so in production two requests interleave between any two store
calls. ``YieldingStore`` restores exactly that property:
- a double-clicked Approve created two active approvals, and each one could issue a full set of purchase orders;
- two "Generate POs" requests (the UI sends a fresh Idempotency-Key per click) issued two full sets;
- a double-clicked "Confirm & send" emailed the same purchase order twice;
- a slow approval write could land after a real quote change had already made the plan stale, resurrecting it
  as approved with an active approval;
- purchase orders could be issued and sent for a plan that a newer version had already superseded;
- two purchase orders sent close together archived two copies of the mission's audit export in Google Drive.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta

import httpx
import pytest

import app.main as app_main
from app.continuity import _capacity_shock, _delay_shock, build_continuity_analysis
from app.optimizer import solve
from app.store import MemoryStore
from conftest import FakeUpstream, auth, make_settings, register, settle_jobs, wait_for
from test_operations_integrations import FakeProviders, connect_google, ops_settings, settle_deliveries

NOW = datetime.now(UTC).replace(microsecond=0)


# --------------------------------------------------------------------------- continuity breakpoints

def _at(hours: float) -> str:
    return (NOW + timedelta(hours=hours)).isoformat()


def _engine_mission(requirements: dict[str, int], deadline_hours: float = 96) -> dict:
    return {"id": "m1", "budget": "100000.00", "delivery_deadline": _at(deadline_hours), "max_supplier_share": None,
            "requirements": [{"id": key, "item": key, "quantity": quantity} for key, quantity in requirements.items()]}


def _engine_quote(supplier: str, lines: list[tuple[str, str, int, float]]) -> dict:
    """One line per requirement, as the API enforces: (requirement, unit price, quantity, delivery hours)."""
    return {"id": f"q-{supplier}", "supplier_id": supplier, "supplier_email": f"{supplier}@x.example.org",
            "status": "submitted", "version": 1, "currency": "USD", "shipping_cost": "0", "expires_at": _at(200),
            "lines": [{"item": key, "requirement_id": key, "unit_price": price, "available_quantity": quantity,
                       "delivery_date": _at(hours)} for key, price, quantity, hours in lines]}


def _frontier(mission: dict, quotes: list[dict], supplier: str) -> dict:
    outcome = solve(mission, quotes)
    assert outcome["status"] == "feasible", outcome
    plan = {**outcome, "id": "p1", "version": 1, "status": "feasible", "plan_hash": "h",
            "policy": {"suppliers": {q["supplier_id"]: {"legal_name": q["supplier_id"].upper()} for q in quotes}}}
    analysis = build_continuity_analysis(mission, plan, quotes, input_hash="x", quote_versions=[],
                                         policy_fingerprint="p", evidence_fingerprint="e",
                                         optimizer_input_fingerprint="o", created_at=NOW.isoformat())
    return {row["supplier_id"]: row for row in analysis["failure_frontier"]}[supplier]


def _feasible(mission: dict, quotes: list[dict]) -> bool:
    return solve(mission, quotes)["status"] == "feasible"


def test_delay_breakpoint_covers_a_supplier_whose_essential_line_is_not_its_latest() -> None:
    # S is the only water source (delivered 72 h before the deadline); its blankets land 12 h before the deadline and
    # T can replace them. The plan breaks only when S's *water* misses the deadline: a delay of 73 whole hours.
    mission = _engine_mission({"water": 100, "blankets": 50})
    quotes = [_engine_quote("s", [("water", "1.00", 100, 24), ("blankets", "1.00", 50, 84)]),
              _engine_quote("t", [("blankets", "2.00", 50, 24)])]
    frontier = _frontier(mission, quotes, "s")
    assert frontier["delay"] is not None, "a real delay breakpoint was reported as 'no breakpoint'"
    hours = frontier["delay"]["hours"]
    assert hours == 73
    assert _feasible(mission, _delay_shock(quotes, "s", hours - 1))
    assert not _feasible(mission, _delay_shock(quotes, "s", hours))


def test_capacity_breakpoint_is_the_first_loss_that_breaks_the_plan() -> None:
    # S quotes three requirements (3 / 3 / 2 units); only S has z, and z needs both of S's units. T covers x and y.
    mission = _engine_mission({"x": 3, "y": 3, "z": 2})
    quotes = [_engine_quote("s", [("x", "1.00", 3, 24), ("y", "1.00", 3, 24), ("z", "1.00", 2, 24)]),
              _engine_quote("t", [("x", "5.00", 3, 24), ("y", "5.00", 3, 24)])]
    truth = [_feasible(mission, _capacity_shock(quotes, "s", loss)) for loss in range(9)]
    first_breaking = truth.index(False)
    assert all(truth[:first_breaking]) and not any(truth[first_breaking:]), \
        f"the capacity shock must be monotone in the loss: {truth}"
    frontier = _frontier(mission, quotes, "s")
    assert frontier["capacity"]["loss_units"] == first_breaking
    assert frontier["capacity"]["units_removed"] == first_breaking


def test_capacity_shock_removes_exactly_the_requested_units_and_never_grows_a_line() -> None:
    quotes = [_engine_quote("s", [("x", "1.00", 2, 24), ("y", "1.00", 2, 24), ("z", "1.00", 5, 24)])]
    previous = [2, 2, 5]
    for loss in range(10):
        shocked = [line["available_quantity"] for line in _capacity_shock(quotes, "s", loss)[0]["lines"]]
        assert sum(shocked) == 9 - loss
        assert all(now <= before for now, before in zip(shocked, previous)), (loss, shocked, previous)
        previous = shocked


# --------------------------------------------------------------------------- races

class Rendezvous:
    """One-shot meeting point: the first caller waits (bounded) for a second one, so two racing requests reach the
    contested write together. A correctly serialized handler never lets the second caller arrive; the wait then
    times out and the first proceeds alone."""

    def __init__(self, timeout: float = 0.5) -> None:
        self.timeout, self.arrived, self.met = timeout, 0, asyncio.Event()

    async def wait(self) -> None:
        if self.met.is_set():
            return
        self.arrived += 1
        if self.arrived < 2:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.met.wait(), self.timeout)
        self.met.set()


class YieldingStore(MemoryStore):
    """MemoryStore that yields to the event loop on every call, as MongoStore's network I/O does."""

    rendezvous: dict[str, Rendezvous] = {}

    async def get(self, collection, document_id):
        await asyncio.sleep(0)
        return await super().get(collection, document_id)

    async def find(self, collection, **filters):
        await asyncio.sleep(0)
        return await super().find(collection, **filters)

    async def insert(self, collection, document):
        await asyncio.sleep(0)
        if collection in self.rendezvous:
            await self.rendezvous[collection].wait()
        return await super().insert(collection, document)

    async def replace(self, collection, document_id, document):
        await asyncio.sleep(0)
        return await super().replace(collection, document_id, document)

    async def upsert(self, collection, document):
        await asyncio.sleep(0)
        return await super().upsert(collection, document)


@pytest.fixture
async def mongo_like(monkeypatch):
    monkeypatch.setattr(app_main, "MemoryStore", YieldingStore)
    app = app_main.create_app(make_settings(), http_transport=httpx.MockTransport(FakeUpstream()))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            yield app, client


async def _quote(client, coordinator: str, mission_id: str, email: str, name: str, quantity: int, price: str):
    supplier = await register(client, email, "supplier")
    token = (await client.post(f"/v1/missions/{mission_id}/invitations", headers=auth(coordinator),
                               json={"supplier_email": email})).json()["token"]
    await client.post(f"/v1/supplier-invitations/{token}/accept", headers=auth(supplier))
    submitted = await client.post("/v1/quotes", headers=auth(supplier), json={
        "invitation_token": token, "expires_at": (datetime.now(UTC) + timedelta(days=3)).isoformat(),
        "shipping_cost": "0", "supplier_profile": {"legal_name": name},
        "lines": [{"item": "blankets", "unit_price": price, "available_quantity": quantity,
                   "delivery_date": (datetime.now(UTC) + timedelta(days=1)).isoformat()}]})
    assert submitted.status_code == 201, submitted.text
    return supplier, submitted.json()


async def _approved_ready_mission(client) -> dict:
    """Two suppliers, one feasible plan v1 (Alpha 60 x $1 + Beta 40 x $2), an independent approver."""
    coordinator = await register(client, "buyer@county.example.org", "coordinator")
    org = (await client.post("/v1/organizations", json={"name": "County OES"}, headers=auth(coordinator))).json()
    invite = (await client.post(f"/v1/organizations/{org['id']}/members", headers=auth(coordinator),
                                json={"email": "approver@county.example.org", "role": "approver"})).json()
    approver = await register(client, "approver@county.example.org", "coordinator")
    await client.post(f"/v1/org-invites/{invite['invite_url'].rsplit('/', 1)[1]}/accept", headers=auth(approver))
    mission = (await client.post("/v1/missions", headers=auth(coordinator), json={
        "organization_id": org["id"], "name": "Shelter blankets", "delivery_location": "Oakland, CA",
        "delivery_deadline": (datetime.now(UTC) + timedelta(days=4)).isoformat(), "budget": "1000.00",
        "requirements": [{"item": "blankets", "quantity": 100}]})).json()
    alpha, alpha_quote = await _quote(client, coordinator, mission["id"], "a@alpha.example.org", "Alpha Textiles",
                                      60, "1.00")
    await _quote(client, coordinator, mission["id"], "b@beta.example.org", "Beta Supply", 60, "2.00")
    await settle_jobs(client, coordinator, mission["id"])
    plan_id = (await client.post(f"/v1/missions/{mission['id']}/optimize", headers=auth(coordinator))).json()["plan_id"]
    await settle_jobs(client, coordinator, mission["id"])
    plan = (await client.get(f"/v1/plans/{plan_id}", headers=auth(coordinator))).json()
    assert plan["status"] == "feasible" and plan["total_cost"] == "140.00", plan
    return {"coordinator": coordinator, "approver": approver, "mission_id": mission["id"], "plan": plan,
            "alpha": alpha, "alpha_quote": alpha_quote}


def _po_url(ctx: dict, plan_id: str | None = None) -> str:
    return f"/v1/plans/{plan_id or ctx['plan']['id']}/purchase-orders"


def _keyed(ctx: dict, key: str) -> dict:
    return {**auth(ctx["coordinator"]), "Idempotency-Key": key}


@pytest.mark.anyio
async def test_double_clicked_approve_creates_one_approval_and_one_set_of_orders(mongo_like) -> None:
    app, client = mongo_like
    ctx = await _approved_ready_mission(client)
    app.state.services.store.rendezvous = {"approvals": Rendezvous()}
    url = f"/v1/plans/{ctx['plan']['id']}/approve"
    results = await asyncio.gather(client.post(url, headers=auth(ctx["approver"])),
                                   client.post(url, headers=auth(ctx["approver"])))
    assert sorted(r.status_code for r in results) == [201, 409], [r.text for r in results]
    approvals = await app.state.services.store.find("approvals", plan_id=ctx["plan"]["id"])
    assert [a["status"] for a in approvals] == ["active"]
    assert (await client.post(_po_url(ctx), headers=_keyed(ctx, "first-click"))).status_code == 201
    assert (await client.post(_po_url(ctx), headers=_keyed(ctx, "second-click"))).status_code == 409
    assert len(await app.state.services.store.find("purchase_orders", mission_id=ctx["mission_id"])) == 2


@pytest.mark.anyio
async def test_two_generate_po_requests_issue_one_set_of_orders(mongo_like) -> None:
    app, client = mongo_like
    ctx = await _approved_ready_mission(client)
    assert (await client.post(f"/v1/plans/{ctx['plan']['id']}/approve", headers=auth(ctx["approver"]))).status_code == 201
    app.state.services.store.rendezvous = {"purchase_orders": Rendezvous()}
    results = await asyncio.gather(client.post(_po_url(ctx), headers=_keyed(ctx, "tab-1")),
                                   client.post(_po_url(ctx), headers=_keyed(ctx, "tab-2")))
    assert sorted(r.status_code for r in results) == [201, 409], [r.text for r in results]
    orders = await app.state.services.store.find("purchase_orders", mission_id=ctx["mission_id"])
    assert sorted(o["supplier_email"] for o in orders) == ["a@alpha.example.org", "b@beta.example.org"]


@pytest.mark.anyio
async def test_double_clicked_send_emails_the_purchase_order_once(mongo_like) -> None:
    app, client = mongo_like
    ctx = await _approved_ready_mission(client)
    assert (await client.post(f"/v1/plans/{ctx['plan']['id']}/approve", headers=auth(ctx["approver"]))).status_code == 201
    order = (await client.post(_po_url(ctx), headers=_keyed(ctx, "k"))).json()[0]
    services = app.state.services
    meeting, original_send = Rendezvous(), services.email.send

    async def provider_send(message, organization_id=None, **kwargs):  # both clicks reach the provider call together
        await meeting.wait()
        return await original_send(message, organization_id, **kwargs)

    services.email.send = provider_send
    url = f"/v1/purchase-orders/{order['id']}/send"
    results = await asyncio.gather(*[client.post(url, json={"confirm": True}, headers=auth(ctx["coordinator"]))
                                     for _ in range(2)])
    services.email.send = original_send
    assert sorted(r.status_code for r in results) == [200, 409], [r.text for r in results]
    assert len(await app.state.services.store.find("email_dispatches", entity_id=order["id"])) == 1


async def _reoptimize(client, ctx: dict) -> str:
    """The coordinator re-runs the optimizer ("Run optimization" stays available under an approved plan)."""
    response = await client.post(f"/v1/missions/{ctx['mission_id']}/optimize", headers=auth(ctx["coordinator"]))
    assert response.status_code == 202, response.text
    return response.json()["plan_id"]


@pytest.mark.anyio
async def test_orders_cannot_be_issued_for_a_superseded_approved_plan(mongo_like) -> None:
    app, client = mongo_like
    ctx = await _approved_ready_mission(client)
    assert (await client.post(f"/v1/plans/{ctx['plan']['id']}/approve", headers=auth(ctx["approver"]))).status_code == 201
    v2_id = await _reoptimize(client, ctx)
    assert (await client.post(f"/v1/plans/{v2_id}/approve", headers=auth(ctx["approver"]))).status_code == 201
    assert (await client.post(_po_url(ctx, v2_id), headers=_keyed(ctx, "v2"))).status_code == 201
    stale = await client.post(_po_url(ctx), headers=_keyed(ctx, "v1"))
    assert stale.status_code == 409, "orders were issued for v1 after v2 superseded it (both sets would be bought)"
    orders = await app.state.services.store.find("purchase_orders", mission_id=ctx["mission_id"])
    assert {o["plan_version"] for o in orders} == {2} and len(orders) == 2


@pytest.mark.anyio
async def test_a_superseded_plans_draft_order_cannot_be_sent(mongo_like) -> None:
    app, client = mongo_like
    ctx = await _approved_ready_mission(client)
    assert (await client.post(f"/v1/plans/{ctx['plan']['id']}/approve", headers=auth(ctx["approver"]))).status_code == 201
    v1_drafts = (await client.post(_po_url(ctx), headers=_keyed(ctx, "v1"))).json()
    v2_id = await _reoptimize(client, ctx)
    assert (await client.post(f"/v1/plans/{v2_id}/approve", headers=auth(ctx["approver"]))).status_code == 201
    v2_drafts = (await client.post(_po_url(ctx, v2_id), headers=_keyed(ctx, "v2"))).json()
    assert len(v2_drafts) == 2  # v2 re-buys everything: v1's drafts were never committed
    stale_send = await client.post(f"/v1/purchase-orders/{v1_drafts[0]['id']}/send", json={"confirm": True},
                                   headers=auth(ctx["coordinator"]))
    assert stale_send.status_code == 409, "a superseded plan's draft was sent alongside the current plan's orders"
    assert await app.state.services.store.find("email_dispatches", entity_id=v1_drafts[0]["id"]) == []


@pytest.mark.anyio
async def test_a_slow_approval_write_cannot_resurrect_a_plan_a_quote_change_made_stale(monkeypatch) -> None:
    reached, release = asyncio.Event(), asyncio.Event()

    class SlowApprovalStore(YieldingStore):
        async def insert(self, collection, document):
            if collection == "approvals":
                reached.set()
                with contextlib.suppress(TimeoutError):  # a slow write, bounded so a serialized fix cannot hang
                    await asyncio.wait_for(release.wait(), timeout=1.0)
            return await super().insert(collection, document)

    monkeypatch.setattr(app_main, "MemoryStore", SlowApprovalStore)
    app = app_main.create_app(make_settings(), http_transport=httpx.MockTransport(FakeUpstream()))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            ctx = await _approved_ready_mission(client)

            async def supplier_revises_after_approval_checks_passed() -> httpx.Response:
                await reached.wait()
                line = {"item": "blankets", "unit_price": "1.50", "available_quantity": 60,
                        "delivery_date": (datetime.now(UTC) + timedelta(days=1)).isoformat()}
                response = await client.put(f"/v1/quotes/{ctx['alpha_quote']['id']}", headers=auth(ctx["alpha"]),
                                            json={"expires_at": (datetime.now(UTC) + timedelta(days=3)).isoformat(),
                                                  "shipping_cost": "0", "lines": [line]})
                release.set()
                return response

            approve, revised = await asyncio.gather(
                client.post(f"/v1/plans/{ctx['plan']['id']}/approve", headers=auth(ctx["approver"])),
                supplier_revises_after_approval_checks_passed())
            assert revised.status_code == 200, revised.text
            plan = await app.state.services.store.get("plans", ctx["plan"]["id"])
            approvals = await app.state.services.store.find("approvals", plan_id=ctx["plan"]["id"])
            assert plan["status"] == "stale", f"plan v1 is {plan['status']} after its quote changed"
            assert all(a["status"] != "active" for a in approvals)
            orders = await client.post(_po_url(ctx), headers=_keyed(ctx, "after-change"))
            assert orders.status_code == 409, "purchase orders were issued at the superseded quote price"
            await settle_jobs(client, ctx["coordinator"], ctx["mission_id"])


@pytest.mark.anyio
async def test_a_send_racing_a_quote_change_is_committed_before_the_replan(mongo_like) -> None:
    """The PO email is slow; a quote change during it must not void the order under the send and let the replan
    re-buy units the supplier was just sent."""
    app, client = mongo_like
    services = app.state.services
    ctx = await _approved_ready_mission(client)
    assert (await client.post(f"/v1/plans/{ctx['plan']['id']}/approve", headers=auth(ctx["approver"]))).status_code == 201
    orders = (await client.post(_po_url(ctx), headers=_keyed(ctx, "k"))).json()
    beta_order = next(o for o in orders if o["supplier_email"].startswith("b@"))
    sending, release = asyncio.Event(), asyncio.Event()
    original_send = services.email.send

    async def slow_send(message, organization_id=None, **kwargs):
        sending.set()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(release.wait(), timeout=1.0)
        return await original_send(message, organization_id, **kwargs)

    services.email.send = slow_send

    async def alpha_withdraws_during_the_send() -> httpx.Response:
        await sending.wait()
        response = await client.post(f"/v1/quotes/{ctx['alpha_quote']['id']}/withdraw", headers=auth(ctx["alpha"]))

        async def replanned():
            plans = await services.store.find("plans", mission_id=ctx["mission_id"])
            return any(p["version"] == 2 for p in plans)
        with contextlib.suppress(AssertionError):
            await wait_for(replanned, attempts=25, delay=0.02)
        release.set()
        return response

    sent, withdrawn = await asyncio.gather(
        client.post(f"/v1/purchase-orders/{beta_order['id']}/send", json={"confirm": True},
                    headers=auth(ctx["coordinator"])),
        alpha_withdraws_during_the_send())
    services.email.send = original_send
    assert withdrawn.status_code == 202, withdrawn.text
    await settle_jobs(client, ctx["coordinator"], ctx["mission_id"])
    order = await services.store.get("purchase_orders", beta_order["id"])
    dispatches = await services.store.find("email_dispatches", entity_id=beta_order["id"])
    v2 = max(await services.store.find("plans", mission_id=ctx["mission_id"]), key=lambda p: p["version"])
    assert v2["version"] == 2
    committed = sum(row["quantity"] for row in v2["allocations"] if row.get("committed"))
    if dispatches:  # the supplier was emailed this PO, so the replan must treat its 40 units as bought
        assert sent.status_code == 200 and order["status"] == "sent"
        assert committed == 40, f"replan ignored a PO the supplier was sent (order {order['status']})"
    else:
        assert sent.status_code == 409 and order["status"] == "void" and committed == 0


@pytest.mark.anyio
async def test_two_orders_sent_together_archive_one_audit_export_in_drive(monkeypatch) -> None:
    monkeypatch.setattr(app_main, "MemoryStore", YieldingStore)
    providers = FakeProviders(upstream=FakeUpstream())

    class RealisticDriveLatency(httpx.AsyncBaseTransport):
        """A multipart upload takes longer than a metadata read, as against the real Drive API."""

        def __init__(self) -> None:
            self.inner = httpx.MockTransport(providers)

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            if request.url.host == "www.googleapis.com":
                await asyncio.sleep(0.3 if "/upload/drive" in request.url.path else 0.02)
            return await self.inner.handle_async_request(request)

    app = app_main.create_app(ops_settings(), http_transport=RealisticDriveLatency())
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            coordinator = await register(client, "coord@relief.example.org", "coordinator")
            approver = await register(client, "approver@relief.example.org", "coordinator")
            org = (await client.post("/v1/organizations", json={"name": "Oakland Relief"},
                                     headers=auth(coordinator))).json()["id"]
            invite = await client.post(f"/v1/organizations/{org}/members", headers=auth(coordinator),
                                       json={"email": "approver@relief.example.org", "role": "approver"})
            await client.post(f"/v1/org-invites/{invite.json()['invite_url'].rsplit('/', 1)[1]}/accept",
                              headers=auth(approver))
            assert (await connect_google(client, coordinator, org)).status_code == 303
            mission_id = (await client.post("/v1/missions", headers=auth(coordinator), json={
                "organization_id": org, "name": "Oakland Shelter Supplies", "delivery_location": "Oakland, CA",
                "delivery_deadline": (datetime.now(UTC) + timedelta(days=10)).isoformat(), "budget": "500.00",
                "requirements": [{"item": "blankets", "quantity": 15}]})).json()["id"]
            for name, legal, price in (("bayside", "Bayside Relief Supply Co", "7.00"),
                                       ("sierra", "Sierra Backup Provisions", "9.00")):
                await _quote(client, coordinator, mission_id, f"{name}@supply.example.com", legal, 10, price)
            await settle_jobs(client, coordinator, mission_id)
            plan_id = (await client.post(f"/v1/missions/{mission_id}/optimize",
                                         headers=auth(coordinator))).json()["plan_id"]
            await settle_jobs(client, coordinator, mission_id)
            assert (await client.post(f"/v1/plans/{plan_id}/approve", headers=auth(approver))).status_code == 201
            orders = (await client.post(f"/v1/plans/{plan_id}/purchase-orders",
                                        headers={**auth(coordinator), "Idempotency-Key": "k"})).json()
            assert len(orders) == 2
            await settle_deliveries(app, mission_id)
            sends = await asyncio.gather(*[client.post(f"/v1/purchase-orders/{order['id']}/send",
                                                       json={"confirm": True}, headers=auth(coordinator))
                                           for order in orders])
            assert [r.status_code for r in sends] == [200, 200], [r.text for r in sends]
            await settle_deliveries(app, mission_id)
            exports = [row for row in providers.drive_files.values() if row.get("name") == "Audit-Export.json"]
            assert len(exports) == 1, f"{len(exports)} copies of the audit export were archived"
            assert exports[0]["version"] == 2  # the second send updated the same file
