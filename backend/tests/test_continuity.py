from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from app import planning
from app.continuity import build_continuity_analysis
from app.optimizer import solve
from conftest import auth, register, settle_jobs, wait_for


def continuity_fixture() -> tuple[dict, dict, list[dict]]:
    deadline = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    mission = {
        "id": "mission-continuity", "organization_id": "org-1", "budget": "1000.00",
        "delivery_deadline": deadline, "requirements": [{"id": "req_masks", "item": "masks", "quantity": 10}],
        "max_supplier_share": None, "single_source_only": False,
    }
    quotes = [
        {"id": "quote-a", "supplier_id": "supplier-a", "supplier_email": "a@example.test", "status": "submitted",
         "version": 1, "shipping_cost": "0.00", "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
         "lines": [{"requirement_id": "req_masks", "item": "masks", "unit_price": "1.00", "available_quantity": 8,
                    "delivery_date": (datetime.now(UTC) + timedelta(hours=12)).isoformat()}]},
        {"id": "quote-b", "supplier_id": "supplier-b", "supplier_email": "b@example.test", "status": "submitted",
         "version": 4, "shipping_cost": "0.00", "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
         "lines": [{"requirement_id": "req_masks", "item": "masks", "unit_price": "2.00", "available_quantity": 10,
                    "delivery_date": (datetime.now(UTC) + timedelta(hours=16)).isoformat()}]},
    ]
    outcome = solve(mission, quotes)
    assert outcome["status"] == "feasible"
    plan = {
        "id": "plan-continuity", "mission_id": mission["id"], "version": 1, "status": "feasible",
        "plan_hash": "a" * 64, "total_cost": outcome["total_cost"], "remaining_budget": outcome["remaining_budget"],
        "latest_delivery": max(row["delivery_date"] for row in outcome["allocations"]), "allocations": outcome["allocations"],
        "policy": {"suppliers": {
            "supplier-a": {"legal_name": "Alpha Supply"}, "supplier-b": {"legal_name": "Bravo Supply"},
        }},
    }
    return mission, plan, quotes


def test_n1_analysis_is_deterministic_and_does_not_mutate_quotes() -> None:
    mission, plan, quotes = continuity_fixture()
    original = deepcopy(quotes)
    analysis = build_continuity_analysis(
        mission, plan, quotes, input_hash="input-hash", quote_versions=[], policy_fingerprint="policy",
        evidence_fingerprint="evidence", optimizer_input_fingerprint="optimizer", created_at=datetime.now(UTC).isoformat(),
    )
    by_supplier = {row["supplier_id"]: row for row in analysis["n1_scenarios"]}
    assert analysis["provenance"] == "HYPOTHETICAL"
    assert by_supplier["supplier-a"]["status"] == "RECOVERABLE"
    assert by_supplier["supplier-b"]["status"] == "UNRECOVERABLE"
    assert by_supplier["supplier-b"]["lost_quantity"] == 2
    assert analysis["metrics"]["n1_survivability"] == {"survives": 1, "tested": 2}
    assert quotes == original


def test_failure_frontier_and_resilient_alternative_are_derived_from_quotes() -> None:
    mission, plan, quotes = continuity_fixture()
    analysis = build_continuity_analysis(
        mission, plan, quotes, input_hash="input-hash", quote_versions=[], policy_fingerprint="policy",
        evidence_fingerprint="evidence", optimizer_input_fingerprint="optimizer", created_at=datetime.now(UTC).isoformat(),
    )
    frontier = {row["supplier_id"]: row for row in analysis["failure_frontier"]}
    assert frontier["supplier-b"]["price"]["increase_percent"] > 0
    assert frontier["supplier-b"]["delay"]["hours"] > 0
    assert frontier["supplier-b"]["capacity"]["loss_units"] > 0
    alternative = analysis["resilient_alternative"]
    assert alternative["status"] == "AVAILABLE"
    assert float(alternative["total_cost"]) >= float(plan["total_cost"])


@pytest.mark.anyio
async def test_other_org_cannot_read_a_mission_continuity_view(client) -> None:
    owner = await register(client, "owner-continuity@example.com", "coordinator")
    outsider = await register(client, "outsider-continuity@example.com", "coordinator")
    organization = await client.post("/v1/organizations", json={"name": "Continuity owner"}, headers=auth(owner))
    mission = await client.post(
        "/v1/missions",
        json={
            "organization_id": organization.json()["id"], "name": "Continuity access",
            "delivery_location": "Oakland, CA", "delivery_deadline": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
            "budget": "100.00", "requirements": [{"item": "masks", "quantity": 5}],
        }, headers=auth(owner),
    )
    response = await client.get(f"/v1/missions/{mission.json()['id']}/continuity", headers=auth(outsider))
    assert response.status_code == 403


async def _demo_plan(client) -> tuple[str, str, str, dict]:
    """Create a policy-eligible plan with deterministic, labeled demo suppliers."""

    token = await register(client, f"continuity-{datetime.now().timestamp()}@ops.example.com", "coordinator")
    organization = await client.post(
        "/v1/organizations", json={"name": "Continuity Test Organization", "demo": True}, headers=auth(token)
    )
    mission = await client.post(
        "/v1/missions",
        json={
            "organization_id": organization.json()["id"], "name": "Continuity readiness",
            "delivery_location": "Oakland, CA", "delivery_deadline": (datetime.now(UTC) + timedelta(days=5)).isoformat(),
            "budget": "5000.00", "requirements": [{"item": "blankets", "quantity": 100}],
        },
        headers=auth(token),
    )
    mission_id = mission.json()["id"]
    seeded = await client.post(f"/v1/missions/{mission_id}/demo/seed", headers=auth(token))
    assert seeded.status_code == 201, seeded.text
    await settle_jobs(client, token, mission_id)
    optimized = await client.post(f"/v1/missions/{mission_id}/optimize", headers=auth(token))
    assert optimized.status_code == 202, optimized.text
    plan = (await client.get(f"/v1/plans/{optimized.json()['plan_id']}", headers=auth(token))).json()
    await settle_jobs(client, token, mission_id)
    return token, mission_id, plan["id"], seeded.json()


@pytest.mark.anyio
async def test_continuity_is_plan_bound_read_only_and_stales_after_real_disruption(client) -> None:
    token, mission_id, plan_id, seeded = await _demo_plan(client)
    quotes_before = (await client.get(f"/v1/missions/{mission_id}/quotes", headers=auth(token))).json()

    current = await client.get(
        f"/v1/missions/{mission_id}/continuity", params={"plan_id": plan_id}, headers=auth(token)
    )
    assert current.status_code == 200, current.text
    payload = current.json()
    assert payload["state"] == "COMPLETE"
    assert payload["analysis"]["provenance"] == "HYPOTHETICAL"
    assert payload["analysis"]["plan_id"] == plan_id
    assert payload["analysis"]["counterfactual_label"].startswith("HYPOTHETICAL STRESS TEST")
    assert any(node["type"] == "continuity_analysis" for node in payload["digital_twin"]["nodes"])
    # Running counterfactuals cannot alter any real supplier quote.
    quotes_after_analysis = (await client.get(f"/v1/missions/{mission_id}/quotes", headers=auth(token))).json()
    assert quotes_after_analysis == quotes_before

    bayside = next(supplier["id"] for supplier in seeded["suppliers"]
                   if supplier["legal_name"] == "Bayside Relief Supply Co")
    disrupted = await client.post(
        f"/v1/missions/{mission_id}/disruptions", json={"kind": "withdraw", "supplier_id": bayside},
        headers=auth(token),
    )
    assert disrupted.status_code == 202, disrupted.text

    async def newer_plan():
        rows = (await client.get(f"/v1/missions/{mission_id}/plans", headers=auth(token))).json()
        return rows[0] if rows and rows[0]["id"] != plan_id else None

    await wait_for(newer_plan)
    historical = await client.get(
        f"/v1/missions/{mission_id}/continuity", params={"plan_id": plan_id}, headers=auth(token)
    )
    assert historical.status_code == 200, historical.text
    assert historical.json()["state"] == "STALE"
    assert historical.json()["analysis"]["status"] == "STALE"


@pytest.mark.anyio
async def test_continuity_discards_a_snapshot_when_quote_revision_races_it(app_and_client, monkeypatch) -> None:
    app, client = app_and_client
    token, mission_id, plan_id, _ = await _demo_plan(client)
    services = app.state.services
    records_before = await services.store.find("continuity_analyses", mission_id=mission_id)
    quote = (await services.store.find("quotes", mission_id=mission_id, status="submitted"))[0]
    # Defeat the already-computed cache, then revise again between the frozen snapshot and persistence.
    quote["version"] += 1
    await services.store.replace("quotes", quote["id"], quote)

    original_snapshot = planning.continuity_input_snapshot
    calls = 0

    async def snapshot_with_revision(*args, **kwargs):
        nonlocal calls
        snapshot = await original_snapshot(*args, **kwargs)
        calls += 1
        if calls == 1:
            revised = await services.store.get("quotes", quote["id"])
            revised["version"] += 1
            await services.store.replace("quotes", revised["id"], revised)
        return snapshot

    monkeypatch.setattr(planning, "continuity_input_snapshot", snapshot_with_revision)
    result = await planning.compute_continuity_analysis(services, mission_id, plan_id)

    assert result["status"] == "stale_before_persist"
    assert len(await services.store.find("continuity_analyses", mission_id=mission_id)) == len(records_before)


@pytest.mark.anyio
async def test_continuity_never_reallocates_active_purchase_order_lines(app_and_client) -> None:
    app, client = app_and_client
    token, mission_id, plan_id, _ = await _demo_plan(client)
    approved = await client.post(f"/v1/plans/{plan_id}/approve", headers=auth(token))
    assert approved.status_code == 201, approved.text
    orders = await client.post(
        f"/v1/plans/{plan_id}/purchase-orders", headers={**auth(token), "Idempotency-Key": "continuity-po-scope"}
    )
    assert orders.status_code == 201, orders.text
    for order in orders.json():
        sent = await client.post(f"/v1/purchase-orders/{order['id']}/send", json={"confirm": True}, headers=auth(token))
        assert sent.status_code == 200, sent.text

    # The former all-open-plan result cannot masquerade as current after POs are
    # sent; commitment status and lines participate in the analysis input hash.
    historical = await client.get(
        f"/v1/missions/{mission_id}/continuity", params={"plan_id": plan_id}, headers=auth(token)
    )
    assert historical.status_code == 200, historical.text
    assert historical.json()["state"] == "STALE"

    # Build a new plan from the same persisted state. Its active PO lines are fixed
    # commitments, so continuity must expose no free, fictional reallocation.
    committed_plan = await planning.compute_plan(app.state.services, mission_id, "supplier_disruption")
    result = await planning.compute_continuity_analysis(app.state.services, mission_id, committed_plan["id"])
    assert result["status"] in {"complete", "cached"}
    analyses = await app.state.services.store.find("continuity_analyses", mission_id=mission_id)
    analysis = next(row for row in analyses if row["plan_id"] == committed_plan["id"])
    assert analysis["scope"]["kind"] == "NO_UNCOMMITTED_REQUIREMENTS"
    assert analysis["commitment_fingerprint"]
    assert analysis["metrics"]["n1_survivability"] == {"survives": 0, "tested": 0}
    assert analysis["resilient_alternative"]["status"] == "UNAVAILABLE"
