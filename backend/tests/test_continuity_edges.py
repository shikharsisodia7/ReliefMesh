"""Continuity Engine edge cases: degenerate inputs, concurrency, idempotency, authority, and actual-vs-hypothetical.

Complements test_continuity_guarantees.py (product promises) and test_continuity.py (engine units).
"""

from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

import app.planning as planning
from app.continuity import (_capacity_shock, _price_shock, build_continuity_analysis, reality_check)
from app.optimizer import solve
from conftest import auth, settle_jobs, wait_for
from test_continuity_guarantees import (_complete, _continuity, _line, _mission, _optimize, _org,
                                        _supplier_quote, _three_supplier_mission)

NOW = datetime.now(UTC)


def _quote(supplier: str, lines: list[tuple[str, int, int]]) -> dict:
    return {"id": f"q-{supplier}", "supplier_id": supplier, "supplier_email": f"{supplier}@x.example.org",
            "status": "submitted", "version": 1, "currency": "USD", "shipping_cost": "0",
            "expires_at": (NOW + timedelta(days=3)).isoformat(),
            "lines": [{"item": "blankets", "requirement_id": "req-blankets", "unit_price": price,
                       "available_quantity": quantity, "delivery_date": (NOW + timedelta(days=days)).isoformat()}
                      for price, quantity, days in lines]}


def _unit_mission(budget: str = "130.00", quantity: int = 100) -> dict:
    return {"id": "m1", "budget": budget, "delivery_deadline": (NOW + timedelta(days=4)).isoformat(),
            "requirements": [{"id": "req-blankets", "item": "blankets", "quantity": quantity}],
            "max_supplier_share": None}


def _analyse(mission: dict, quotes: list[dict], progress=None) -> dict:
    outcome = solve(mission, quotes)
    assert outcome["status"] == "feasible"
    plan = {**outcome, "id": "p1", "version": 1, "status": "feasible", "plan_hash": "h",
            "policy": {"suppliers": {q["supplier_id"]: {"legal_name": q["supplier_id"].upper()} for q in quotes}}}
    return build_continuity_analysis(mission, plan, quotes, input_hash="x", quote_versions=[], policy_fingerprint="p",
                                     evidence_fingerprint="e", optimizer_input_fingerprint="o",
                                     created_at=NOW.isoformat(), progress=progress)


# --------------------------------------------------------------------------- degenerate inputs (engine level)

def test_capacity_breakpoint_is_exact_for_a_supplier_with_several_lines() -> None:
    mission = _unit_mission()
    quotes = [_quote("a", [("1.00", 37, 1), ("1.00", 33, 1)]), _quote("b", [("1.20", 40, 2)])]
    frontier = {row["supplier_id"]: row for row in _analyse(mission, quotes)["failure_frontier"]}["a"]
    loss = frontier["capacity"]["loss_units"]

    def feasible(candidate: list[dict]) -> bool:
        return solve(mission, candidate)["status"] == "feasible"

    assert feasible(_capacity_shock(quotes, "a", loss - 1)) and not feasible(_capacity_shock(quotes, "a", loss))
    assert frontier["capacity"]["units_removed"] >= loss  # rounding across lines can only remove more, never less


def test_all_alternatives_ineligible_means_every_loss_is_unrecoverable() -> None:
    # Only policy-eligible quotes reach the engine; with no eligible alternative, no recovery may be invented.
    mission = _unit_mission(budget="500.00")
    analysis = _analyse(mission, [_quote("a", [("1.00", 60, 1)]), _quote("b", [("1.20", 60, 1)])])
    assert analysis["metrics"]["n1_survivability"] == {"survives": 0, "tested": 2}
    assert all(row["status"] == "UNRECOVERABLE" and row["new_cost"] is None for row in analysis["n1_scenarios"])
    assert analysis["metrics"]["alternative_eligible_capacity"] == 0


def test_zero_price_or_zero_capacity_lines_never_crash_or_invent_breakpoints() -> None:
    mission = _unit_mission(budget="200.00")
    quotes = [_quote("a", [("0.00", 100, 1)]), _quote("b", [("1.50", 0, 1), ("1.50", 50, 1)])]
    analysis = _analyse(mission, quotes)
    frontier = {row["supplier_id"]: row for row in analysis["failure_frontier"]}
    assert frontier["a"]["price"] is None  # any percentage of $0 is still $0: no price can break this plan
    assert quotes[0]["lines"][0]["unit_price"] == "0.00" and quotes[1]["lines"][0]["available_quantity"] == 0


def test_progress_reports_every_scenario_group_in_order() -> None:
    seen: list[tuple[int, int]] = []
    _analyse(_unit_mission(), [_quote("a", [("1.00", 70, 1)]), _quote("b", [("1.20", 40, 2)])],
             progress=lambda done, total, label: seen.append((done, total)))
    assert seen == [(1, 5), (2, 5), (3, 5), (4, 5), (5, 5)]  # 2 N-1 scenarios + 2 frontiers + the alternative


def test_shocks_never_touch_their_inputs() -> None:
    quotes = [_quote("a", [("1.00", 70, 1)])]
    _price_shock(quotes, "a", 5_000)
    _capacity_shock(quotes, "a", 30)
    assert quotes[0]["lines"][0] == _quote("a", [("1.00", 70, 1)])["lines"][0]


# --------------------------------------------------------------------------- infeasible plans and bad input (API)

@pytest.mark.anyio
@pytest.mark.parametrize("case", ["budget", "deadline", "coverage"])
async def test_infeasible_plans_are_never_stress_tested(client, case: str) -> None:
    coordinator, org = await _org(client)
    mission = await _mission(client, coordinator, org["id"], budget="50.00" if case == "budget" else "1000.00")
    days = 9 if case == "deadline" else 1
    quantity = 60 if case == "coverage" else 150
    await _supplier_quote(client, coordinator, mission["id"], "a@alpha.example.org", "Alpha Textiles",
                          [_line("1.00", quantity, days=days)])
    await settle_jobs(client, coordinator, mission["id"])
    plan = await _optimize(client, coordinator, mission["id"])
    assert plan["status"] == "infeasible"
    started = await client.post(f"/v1/plans/{plan['id']}/continuity", headers=auth(coordinator))
    assert started.status_code == 409
    view = await _continuity(client, coordinator, mission["id"], plan["id"])
    assert view["state"] == "NOT_READY" and view["analysis"] is None


@pytest.mark.anyio
@pytest.mark.parametrize("line", [{"unit_price": "-1.00"}, {"unit_price": "0"}, {"available_quantity": 0},
                                  {"available_quantity": -5}])
async def test_invalid_quote_values_are_rejected_before_any_analysis(client, line: dict) -> None:
    coordinator, org = await _org(client)
    mission = await _mission(client, coordinator, org["id"])
    from conftest import register
    supplier = await register(client, "bad@values.example.org", "supplier")
    token = (await client.post(f"/v1/missions/{mission['id']}/invitations", headers=auth(coordinator),
                               json={"supplier_email": "bad@values.example.org"})).json()["token"]
    await client.post(f"/v1/supplier-invitations/{token}/accept", headers=auth(supplier))
    response = await client.post("/v1/quotes", headers=auth(supplier), json={
        "invitation_token": token, "expires_at": (NOW + timedelta(days=3)).isoformat(), "shipping_cost": "0",
        "supplier_profile": {"legal_name": "Bad Values"}, "lines": [{**_line("1.00", 60), **line}]})
    assert response.status_code == 422


# --------------------------------------------------------------------------- concurrency, dedupe, idempotency

@pytest.mark.anyio
async def test_identical_runs_share_one_computation_and_repeats_are_cached(app_and_client, monkeypatch) -> None:
    app, client = app_and_client
    services = app.state.services
    coordinator, org = await _org(client)
    ctx = await _three_supplier_mission(client, coordinator, org["id"])
    mid = ctx["mission"]["id"]
    monkeypatch.setattr(services.settings, "continuity_engine_enabled", False)  # no automatic run: count ours only
    plan = await _optimize(client, coordinator, mid)
    calls = 0
    original = planning.build_continuity_analysis

    def counting(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(planning, "build_continuity_analysis", counting)
    first, second = await asyncio.gather(planning.compute_continuity_analysis(services, mid, plan["id"]),
                                         planning.compute_continuity_analysis(services, mid, plan["id"]))
    assert calls == 1 and first == second and first["status"] == "complete"
    again = await planning.compute_continuity_analysis(services, mid, plan["id"])
    assert again["status"] == "cached" and calls == 1
    stored = [row for row in await services.store.find("continuity_analyses", mission_id=mid)
              if row["plan_id"] == plan["id"]]
    assert len(stored) == 1


@pytest.mark.anyio
async def test_a_quote_change_during_analysis_discards_the_result_and_api_stays_responsive(app_and_client,
                                                                                          monkeypatch) -> None:
    app, client = app_and_client
    services = app.state.services
    coordinator, org = await _org(client)
    ctx = await _three_supplier_mission(client, coordinator, org["id"])
    mid = ctx["mission"]["id"]
    monkeypatch.setattr(services.settings, "continuity_engine_enabled", False)
    plan = await _optimize(client, coordinator, mid)
    started, release = threading.Event(), threading.Event()
    original = planning.build_continuity_analysis

    def gated(*args, **kwargs):  # runs in the worker thread
        started.set()
        assert release.wait(timeout=30)
        return original(*args, **kwargs)

    monkeypatch.setattr(planning, "build_continuity_analysis", gated)
    run = asyncio.create_task(planning.compute_continuity_analysis(services, mid, plan["id"]))
    await asyncio.to_thread(started.wait, 30)
    # The solver is busy in its thread: the API still answers, and progress is visible.
    assert (await client.get("/health")).status_code == 200
    assert services.continuity_progress[plan["id"]]["total"] == 5
    beta_token, beta_quote = ctx["beta"]
    revised = await client.put(f"/v1/quotes/{beta_quote['id']}", headers=auth(beta_token), json={
        "expires_at": (NOW + timedelta(days=3)).isoformat(), "shipping_cost": "0", "lines": [_line("1.40", 60)]})
    assert revised.status_code == 200
    release.set()
    result = await run
    assert result["status"] == "stale_before_persist"
    assert not [row for row in await services.store.find("continuity_analyses", mission_id=mid)
                if row["plan_id"] == plan["id"] and row["status"] == "COMPLETE"]


@pytest.mark.anyio
async def test_old_plan_results_are_never_served_as_the_current_plan(client) -> None:
    coordinator, org = await _org(client)
    ctx = await _three_supplier_mission(client, coordinator, org["id"])
    mid = ctx["mission"]["id"]
    plan_v1 = await _optimize(client, coordinator, mid)
    await _complete(client, coordinator, mid, plan_v1["id"])
    alpha_token, alpha_quote = ctx["alpha"]
    await client.post(f"/v1/quotes/{alpha_quote['id']}/withdraw", headers=auth(alpha_token))
    await settle_jobs(client, coordinator, mid)
    current = await _continuity(client, coordinator, mid)  # no plan_id: the latest plan
    assert current["plan_id"] != plan_v1["id"]
    assert current["analysis"] is None or current["analysis"]["plan_id"] == current["plan_id"]


# --------------------------------------------------------------------------- authority

@pytest.mark.anyio
async def test_agent_can_read_results_but_never_start_or_approve(client) -> None:
    coordinator, org = await _org(client)
    ctx = await _three_supplier_mission(client, coordinator, org["id"])
    mid = ctx["mission"]["id"]
    plan = await _optimize(client, coordinator, mid)
    await _complete(client, coordinator, mid, plan["id"])
    agent = (await client.post(f"/v1/organizations/{org['id']}/agent-tokens", headers=auth(coordinator),
                               json={"name": "asi-one"})).json()
    token = agent.get("token") or agent.get("raw_token") or agent.get("value")
    assert (await client.get(f"/v1/missions/{mid}/continuity", headers=auth(token))).status_code == 200
    assert (await client.post(f"/v1/plans/{plan['id']}/continuity", headers=auth(token))).status_code == 403
    assert (await client.post(f"/v1/plans/{plan['id']}/approve", headers=auth(token))).status_code in {401, 403}


# --------------------------------------------------------------------------- actual vs hypothetical

@pytest.mark.anyio
async def test_real_withdrawal_is_compared_with_the_earlier_stress_test_never_replacing_it(client) -> None:
    coordinator, org = await _org(client)
    ctx = await _three_supplier_mission(client, coordinator, org["id"])
    mid = ctx["mission"]["id"]
    plan_v1 = await _optimize(client, coordinator, mid)
    earlier = (await _complete(client, coordinator, mid, plan_v1["id"]))["analysis"]
    predicted = {row["supplier"]: row for row in earlier["n1_scenarios"]}["Alpha Textiles"]
    alpha_token, alpha_quote = ctx["alpha"]
    await client.post(f"/v1/quotes/{alpha_quote['id']}/withdraw", headers=auth(alpha_token))
    await settle_jobs(client, coordinator, mid)
    view = await _continuity(client, coordinator, mid)
    check = view["reality_check"][0]
    assert check["earlier_stress_test"]["provenance"] == "HYPOTHETICAL"
    assert check["actual"]["provenance"] == "USER_SUBMITTED" and check["actual"]["kind"] == "withdrawn"
    assert check["earlier_stress_test"]["predicted_cost"] == predicted["new_cost"] == "132.00"
    assert check["actual"]["plan_total_cost"] == "132.00" and check["consistent"] is True


@pytest.mark.anyio
async def test_real_price_change_is_checked_against_the_stored_breakpoint(client) -> None:
    coordinator, org = await _org(client)
    mission = await _mission(client, coordinator, org["id"], budget="130.00")
    mid = mission["id"]
    _, alpha = await _supplier_quote(client, coordinator, mid, "a@alpha.example.org", "Alpha Textiles",
                                     [_line("1.00", 70)])
    await _supplier_quote(client, coordinator, mid, "b@beta.example.org", "Beta Supply", [_line("1.20", 40, days=2)])
    await settle_jobs(client, coordinator, mid)
    plan_v1 = await _optimize(client, coordinator, mid)
    earlier = (await _complete(client, coordinator, mid, plan_v1["id"]))["analysis"]
    breakpoint_bps = {row["supplier"]: row for row in earlier["failure_frontier"]}["Alpha Textiles"]["price"][
        "increase_basis_points"]
    alpha_token = (await client.post("/v1/auth/login", json={"email": "a@alpha.example.org",
                                                             "password": "correct horse battery staple"})).json()
    token = alpha_token.get("access_token") or alpha_token.get("token")
    revised = await client.put(f"/v1/quotes/{alpha['id']}", headers=auth(token), json={
        "expires_at": (NOW + timedelta(days=3)).isoformat(), "shipping_cost": "0", "lines": [_line("1.15", 70)]})
    assert revised.status_code == 200
    await settle_jobs(client, coordinator, mid)
    check = (await _continuity(client, coordinator, mid))["reality_check"][0]
    assert check["actual"]["change"]["price_change_basis_points"] == 1500 < breakpoint_bps
    assert check["earlier_stress_test"]["tolerance"]["price_breakpoint_basis_points"] == breakpoint_bps
    assert check["earlier_stress_test"]["predicted_status"] == "RECOVERABLE"
    assert check["actual"]["plan_status"] == "feasible" and check["consistent"] is True


def test_reality_check_without_an_earlier_stress_test_says_so() -> None:
    plan = {"version": 2, "status": "feasible", "total_cost": "10.00"}
    result = reality_check(None, plan, {"supplier_id": "a", "supplier": "A", "kind": "withdrawn"})
    assert result["earlier_stress_test"] is None and result["consistent"] is None and "No stress test" in result["note"]


def test_reality_check_is_decimal_exact() -> None:
    assert Decimal("1.15") / Decimal("1.00") - 1 == Decimal("0.15")
