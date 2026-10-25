"""Continuity answers explain stored deterministic results and never invent or round them away.

Run: python -m pytest agent/test_continuity_answers.py
"""

from __future__ import annotations

import copy

from continuity_answers import (
    cheapest_resilient, classify, fragility_key, most_fragile, plan_changes, single_point_of_failure,
    supplier_from_question, survive_losing,
)

ANALYSIS = {
    "status": "COMPLETE", "provenance": "HYPOTHETICAL", "plan_id": "p2", "plan_version": 2,
    "baseline": {"total_cost": "3350.00", "supplier_concentration": [
        {"supplier_id": "a", "supplier": "Alpha Textiles", "units": 600, "unit_share": 0.6},
        {"supplier_id": "b", "supplier": "Beta Supply", "units": 400, "unit_share": 0.4}]},
    "metrics": {"n1_survivability": {"survives": 1, "tested": 2}, "budget_headroom": "650.00",
                "largest_supplier_concentration": 0.6,
                "critical_supplier": {"supplier_id": "a", "supplier": "Alpha Textiles", "reason": "unrecoverable"}},
    "n1_scenarios": [
        {"supplier_id": "a", "supplier": "Alpha Textiles", "feasible": False, "status": "UNRECOVERABLE",
         "lost_quantity": 250, "new_cost": None, "cost_delta": None, "replacement_suppliers": ["Beta Supply"],
         "budget_feasible": True, "deadline_feasible": False, "deadline_delta_hours": None},
        {"supplier_id": "b", "supplier": "Beta Supply", "feasible": True, "status": "RECOVERABLE",
         "lost_quantity": 0, "new_cost": "3480.00", "cost_delta": "130.00", "replacement_suppliers": ["Gamma Relief"],
         "budget_feasible": True, "deadline_feasible": True, "deadline_delta_hours": 6}],
    "resilient_alternative": {"status": "AVAILABLE", "total_cost": "3610.00", "added_cost": "260.00",
                              "constraint": {"max_supplier_share": "0.50"}, "supplier_count": 3,
                              "n1_survivability": {"survives": 3, "tested": 3}},
}


def test_questions_are_classified_and_supplier_names_extracted() -> None:
    assert classify("Which supplier is the biggest single point of failure?") == "single_point"
    assert classify("Can this plan survive losing Supplier A?") == "survive_losing"
    assert classify("What's the cheapest way to make this plan N-1 resilient?") == "cheapest_resilient"
    assert classify("What changed between V1 and V2?") == "plan_changes"
    assert classify("Which mission is most fragile right now?") == "most_fragile"
    assert classify("what if Beta Supply backs out") == "survive_losing"
    assert classify("list the wildfires near Oakland") is None
    assert supplier_from_question("Can this plan survive losing Alpha Textiles?") == "Alpha Textiles"
    assert supplier_from_question("what if Beta Supply backs out?") == "Beta Supply"


def test_single_point_names_the_unrecoverable_supplier_with_exact_units() -> None:
    answer = single_point_of_failure(ANALYSIS)
    assert "**Alpha Textiles**" in answer and "600 allocated units" in answer and "250 units" in answer
    assert "N-1 survivability 1/2" in answer and "HYPOTHETICAL" in answer and "cannot approve" in answer


def test_single_point_with_full_n1_reports_the_costliest_absorbable_loss() -> None:
    survivable = copy.deepcopy(ANALYSIS)
    survivable["n1_scenarios"][0].update(feasible=True, status="RECOVERABLE", lost_quantity=0, cost_delta="410.00",
                                         new_cost="3760.00")
    survivable["metrics"]["n1_survivability"] = {"survives": 2, "tested": 2}
    answer = single_point_of_failure(survivable)
    assert "No single supplier failure breaks this plan" in answer and "Alpha Textiles" in answer and "+$410.00" in answer


def test_survive_losing_uses_the_matching_scenario_and_its_exact_numbers() -> None:
    yes = survive_losing(ANALYSIS, "beta supply")
    assert "RECOVERABLE" in yes and "$3,480.00 (+$130.00)" in yes and "Gamma Relief" in yes and "+6 h" in yes
    no = survive_losing(ANALYSIS, "Alpha")
    assert "UNRECOVERABLE" in no and "250 units" in no and "no replacement delivers before the deadline" in no
    absent = survive_losing(ANALYSIS, "Delta Freight")
    assert "no allocation" in absent and "does not change" in absent
    assert "Which supplier" in survive_losing(ANALYSIS, None)


def test_cheapest_resilient_is_honest_about_whether_the_alternative_is_truly_n1() -> None:
    answer = cheapest_resilient(ANALYSIS)
    assert "$3,610.00 (+$260.00)" in answer and "**is N-1 resilient**" in answer and "new human approval" in answer
    partial = copy.deepcopy(ANALYSIS)
    partial["resilient_alternative"]["n1_survivability"] = {"survives": 2, "tested": 3}
    assert "not fully N-1 resilient" in cheapest_resilient(partial) and "(2/3" in cheapest_resilient(partial)
    none = copy.deepcopy(ANALYSIS)
    none["resilient_alternative"] = {"status": "UNAVAILABLE", "reason": "No feasible plan"}
    assert "No feasible alternative" in cheapest_resilient(none)
    already = copy.deepcopy(ANALYSIS)
    already["metrics"]["n1_survivability"] = {"survives": 2, "tested": 2}
    assert "costs nothing extra" in cheapest_resilient(already)


def test_stale_or_missing_analysis_is_never_presented_as_current() -> None:
    stale = {**ANALYSIS, "status": "STALE"}
    for answer in (single_point_of_failure(stale), survive_losing(stale, "Alpha"), cheapest_resilient(stale)):
        assert "STALE" in answer and "Alpha Textiles" not in answer and "$" not in answer
    assert "no current continuity analysis" in single_point_of_failure(None)


def test_plan_changes_prefers_the_planners_stored_difference() -> None:
    v1 = {"id": "p1", "version": 1, "status": "superseded", "total_cost": "3350.00", "allocations": []}
    v2 = {"id": "p2", "version": 2, "status": "feasible", "total_cost": "3610.00", "allocations": [],
          "difference": {"previous_plan_id": "p1", "cost_delta": "+260.00",
                         "why": ["Alpha Textiles revised its quote: quantity 600 -> 350"],
                         "supplier_delta": [
                             {"supplier_id": "a", "supplier": "Alpha Textiles", "units_before": 600, "units_after": 350},
                             {"supplier_id": "g", "supplier": "Gamma Relief", "units_before": 0, "units_after": 250},
                             {"supplier_id": "b", "supplier": "Beta Supply", "units_before": 400, "units_after": 400}]}}
    answer = plan_changes(v1, v2)
    assert "v1 → v2" in answer and "(+$260.00)" in answer and "quantity 600 -> 350" in answer
    assert "Alpha Textiles: 600 → 350 units" in answer and "Gamma Relief: added (250 units)" in answer
    assert "Beta Supply" not in answer and "new human approval" in answer


def test_plan_changes_falls_back_to_allocations_for_non_adjacent_plans() -> None:
    v1 = {"id": "p1", "version": 1, "status": "superseded", "total_cost": "100.00",
          "allocations": [{"supplier_id": "a", "supplier_email": "a@x", "quantity": 100, "line_cost": "100.00"}]}
    v3 = {"id": "p3", "version": 3, "status": "feasible", "total_cost": "120.00",
          "allocations": [{"supplier_id": "b", "supplier_email": "b@x", "quantity": 100, "line_cost": "120.00"}],
          "difference": {"previous_plan_id": "p2"}}
    answer = plan_changes(v1, v3)
    assert "(+$20.00)" in answer and "a@x: removed (was 100 units)" in answer and "b@x: added (100 units)" in answer


def test_most_fragile_ranking_is_deterministic_and_skips_missions_without_current_analysis() -> None:
    robust = copy.deepcopy(ANALYSIS)
    robust["metrics"].update(n1_survivability={"survives": 2, "tested": 2}, critical_supplier=None,
                             budget_headroom="900.00", largest_supplier_concentration=0.5)
    missions = [({"name": "Robust shelter"}, robust), ({"name": "Fragile water"}, ANALYSIS),
                ({"name": "New mission"}, None)]
    answer = most_fragile(missions)
    assert answer.index("Fragile water") < answer.index("Robust shelter")
    assert "single point of failure: Alpha Textiles" in answer and "Not ranked (no current analysis): New mission" in answer
    assert most_fragile(list(reversed(missions))) == answer  # input order never changes the ranking
    assert fragility_key(ANALYSIS) < fragility_key(robust)
    assert "can't rank" in most_fragile([({"name": "x"}, None)])
