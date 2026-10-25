"""Deterministic, read-only procurement continuity analysis.

The continuity engine is deliberately separate from policy and planning.  It takes a
persisted plan plus the policy-eligible quote snapshot, creates *counterfactual*
copies, and re-solves them with the same MILP used for the real plan.  It never
writes quote, supplier, policy, or plan state.

Every output is therefore an explainable answer to a bounded question such as
"what if this allocated supplier were unavailable?", rather than a prediction or
an AI-generated risk score.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal, ROUND_CEILING
from typing import Any, Callable

from .optimizer import cents, money, solve
from .requirements import line_requirement, requirement_map

HYPOTHETICAL_PROVENANCE = "HYPOTHETICAL"
RESILIENT_MAX_SHARE = Decimal("0.50")


def _dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _supplier_names(plan: dict[str, Any]) -> dict[str, str]:
    return {
        supplier_id: row.get("legal_name") or row.get("email") or supplier_id
        for supplier_id, row in (plan.get("policy", {}).get("suppliers", {}) or {}).items()
    }


def _allocated_supplier_ids(plan: dict[str, Any]) -> list[str]:
    return sorted({row["supplier_id"] for row in plan.get("allocations", []) if not row.get("committed")})


def _allocation_units(plan: dict[str, Any]) -> dict[str, int]:
    units: dict[str, int] = {}
    for row in plan.get("allocations", []):
        if row.get("committed"):
            continue
        units[row["supplier_id"]] = units.get(row["supplier_id"], 0) + int(row["quantity"])
    return units


def _latest_delivery(outcome: dict[str, Any]) -> str | None:
    return max((row["delivery_date"] for row in outcome.get("allocations", [])), default=None)


def _shortage_units(outcome: dict[str, Any]) -> int:
    return sum(int(row.get("shortage", 0)) for row in outcome.get("shortages", []))


def _feasibility(outcome: dict[str, Any]) -> tuple[bool, bool]:
    """Return (budget_feasible, deadline_feasible) without masking an infeasible result."""

    if outcome["status"] == "feasible":
        return True, True
    reasons = {row.get("reason") for row in outcome.get("shortages", [])}
    return "budget" not in reasons, "delivery_or_quote_validity" not in reasons


def _without_supplier(quotes: list[dict[str, Any]], supplier_id: str) -> list[dict[str, Any]]:
    return [deepcopy(quote) for quote in quotes if quote["supplier_id"] != supplier_id]


def _price_shock(quotes: list[dict[str, Any]], supplier_id: str, basis_points: int) -> list[dict[str, Any]]:
    """Increase all relevant lines for one supplier; inputs remain untouched."""

    multiplier = Decimal(10_000 + basis_points) / Decimal(10_000)
    result = deepcopy(quotes)
    for quote in result:
        if quote["supplier_id"] != supplier_id:
            continue
        for line in quote["lines"]:
            original = cents(line["unit_price"])
            shocked = int((Decimal(original) * multiplier).to_integral_value(rounding=ROUND_CEILING))
            line["unit_price"] = money(shocked)
    return result


def _delay_shock(quotes: list[dict[str, Any]], supplier_id: str, hours: int) -> list[dict[str, Any]]:
    result = deepcopy(quotes)
    for quote in result:
        if quote["supplier_id"] != supplier_id:
            continue
        for line in quote["lines"]:
            delivered = _dt(line["delivery_date"])
            line["delivery_date"] = (delivered.timestamp() + hours * 3600)
            line["delivery_date"] = datetime.fromtimestamp(line["delivery_date"], UTC).isoformat()
    return result


def _capacity_shock(quotes: list[dict[str, Any]], supplier_id: str, loss_units: int) -> list[dict[str, Any]]:
    """Remove exactly ``loss_units`` of one supplier's quoted units, in proportion to each line's quantity.

    This is a published stress-test method rather than an assertion about actual inventory. The retained units
    are apportioned with the D'Hondt highest-averages rule (ties go to the earlier line). D'Hondt is
    house-monotone: a larger loss never leaves any line with more units than a smaller loss did. Feasibility is
    therefore monotone in ``loss_units``, so the bisection in ``_first_infeasible`` finds the *first* loss that
    breaks the plan rather than one boundary among several.
    """

    result = deepcopy(quotes)
    targets = [line for quote in result if quote["supplier_id"] == supplier_id for line in quote["lines"]]
    weights = [int(line["available_quantity"]) for line in targets]
    total = sum(weights)
    if total <= 0 or loss_units <= 0:
        return result
    retained = total - min(loss_units, total)
    # Every D'Hondt apportionment meets the lower quota, so start there; fewer than len(targets) units remain.
    shares = [(weight * retained) // total for weight in weights]
    for _ in range(retained - sum(shares)):
        best = None
        for index, weight in enumerate(weights):
            if shares[index] >= weight:
                continue
            # Highest average weight / (share + 1), compared exactly; a tie keeps the earlier line.
            if best is None or weight * (shares[best] + 1) > weights[best] * (shares[index] + 1):
                best = index
        if best is None:
            break
        shares[best] += 1
    for line, share in zip(targets, shares):
        line["available_quantity"] = share
    return result


def _actual_capacity_loss(before: list[dict[str, Any]], after: list[dict[str, Any]], supplier_id: str) -> int:
    def total(rows: list[dict[str, Any]]) -> int:
        return sum(int(line["available_quantity"]) for quote in rows if quote["supplier_id"] == supplier_id
                   for line in quote["lines"])

    return total(before) - total(after)


def _first_infeasible(maximum: int, feasible: Callable[[int], bool]) -> int | None:
    """Find a monotonic shock boundary.  ``0`` must be feasible."""

    if maximum <= 0 or feasible(maximum):
        return None
    low, high = 0, maximum
    while high - low > 1:
        middle = (low + high) // 2
        if feasible(middle):
            low = middle
        else:
            high = middle
    return high


def _scenario(
    mission: dict[str, Any],
    baseline: dict[str, Any],
    quotes: list[dict[str, Any]],
    supplier_id: str,
    names: dict[str, str],
) -> dict[str, Any]:
    recovery = solve(mission, _without_supplier(quotes, supplier_id))
    budget_feasible, deadline_feasible = _feasibility(recovery)
    replacements = sorted({row["supplier_id"] for row in recovery.get("allocations", []) if row["supplier_id"] != supplier_id})
    cost_delta = None
    if recovery["status"] == "feasible":
        cost_delta = money(cents(recovery["total_cost"]) - cents(baseline["total_cost"]))
    return {
        "type": "supplier_unavailable",
        "provenance": HYPOTHETICAL_PROVENANCE,
        "label": f"Stress test: {names.get(supplier_id, supplier_id)} unavailable",
        "supplier_id": supplier_id,
        "supplier": names.get(supplier_id, supplier_id),
        "feasible": recovery["status"] == "feasible",
        "status": "RECOVERABLE" if recovery["status"] == "feasible" else "UNRECOVERABLE",
        "replacement_supplier_ids": replacements,
        "replacement_suppliers": [names.get(row, row) for row in replacements],
        "new_cost": recovery["total_cost"] if recovery["status"] == "feasible" else None,
        "cost_delta": cost_delta,
        "latest_delivery": _latest_delivery(recovery),
        "deadline_delta_hours": _deadline_delta_hours(baseline, recovery),
        "lost_quantity": _shortage_units(recovery),
        "budget_feasible": budget_feasible,
        "deadline_feasible": deadline_feasible,
        "shortages": recovery.get("shortages", []),
        # This is a counterfactual recovery proposal, not a real plan and cannot be approved.
        "recovery_plan": {
            "status": recovery["status"],
            "allocations": recovery.get("allocations", []),
            "total_cost": recovery.get("total_cost"),
        },
    }


def _deadline_delta_hours(baseline: dict[str, Any], outcome: dict[str, Any]) -> int | None:
    before, after = _latest_delivery(baseline), _latest_delivery(outcome)
    if not before or not after:
        return None
    return round((_dt(after) - _dt(before)).total_seconds() / 3600)


def _frontier_for_supplier(
    mission: dict[str, Any], quotes: list[dict[str, Any]], supplier_id: str, names: dict[str, str]
) -> dict[str, Any]:
    """Compute exact monotonic breakpoints from the actual quote snapshot."""

    unavailable = solve(mission, _without_supplier(quotes, supplier_id))
    if unavailable["status"] == "feasible":
        return {
            "supplier_id": supplier_id,
            "supplier": names.get(supplier_id, supplier_id),
            "price": None,
            "delay": None,
            "capacity": None,
            "note": "Removing this supplier remains feasible; no single-supplier failure frontier applies.",
        }

    supplier_lines = [line for quote in quotes if quote["supplier_id"] == supplier_id for line in quote["lines"]]
    budget_cents = cents(mission["budget"])
    smallest_price = min((cents(line["unit_price"]) for line in supplier_lines), default=1)
    # At this cap, one unit from even the cheapest affected line exceeds the full mission budget.
    max_price_bps = max(1, ((budget_cents // max(1, smallest_price)) + 2) * 10_000)
    price_bps = _first_infeasible(
        max_price_bps,
        lambda value: solve(mission, _price_shock(quotes, supplier_id, value))["status"] == "feasible",
    )

    deadline = _dt(mission["delivery_deadline"])
    # At this cap even the supplier's earliest line lands after the deadline, which equals removing the supplier.
    # (Bounding by the latest line stopped the search before an earlier, essential line was ever pushed out.)
    earliest = min((_dt(line["delivery_date"]) for line in supplier_lines), default=deadline)
    max_delay_hours = max(1, int((deadline - earliest).total_seconds() // 3600) + 2)
    delay_hours = _first_infeasible(
        max_delay_hours,
        lambda value: solve(mission, _delay_shock(quotes, supplier_id, value))["status"] == "feasible",
    )

    capacity = sum(int(line["available_quantity"]) for line in supplier_lines)
    capacity_loss = _first_infeasible(
        capacity,
        lambda value: solve(mission, _capacity_shock(quotes, supplier_id, value))["status"] == "feasible",
    )
    removed_units = None
    if capacity_loss is not None:
        removed_units = _actual_capacity_loss(quotes, _capacity_shock(quotes, supplier_id, capacity_loss), supplier_id)

    return {
        "supplier_id": supplier_id,
        "supplier": names.get(supplier_id, supplier_id),
        "price": {
            "increase_basis_points": price_bps,
            "increase_percent": round(price_bps / 100, 2),
        } if price_bps is not None else None,
        "delay": {"hours": delay_hours} if delay_hours is not None else None,
        # loss_units is the first loss _capacity_shock cannot survive: every smaller loss is survivable.
        # units_removed is what that shock removes from the quote lines (exactly loss_units).
        "capacity": {
            "loss_units": capacity_loss,
            "units_removed": removed_units,
            "loss_percent": round(capacity_loss / capacity * 100, 2) if capacity else None,
            "method": "proportional reduction across the supplier's policy-eligible quote lines",
        } if capacity_loss is not None else None,
    }


def _alternative_capacity(mission: dict[str, Any], plan: dict[str, Any], quotes: list[dict[str, Any]]) -> int:
    allocated = set(_allocated_supplier_ids(plan))
    required = requirement_map(mission)
    total = 0
    for key, requirement in required.items():
        available = sum(
            int(line["available_quantity"])
            for quote in quotes if quote["supplier_id"] not in allocated
            for line in quote["lines"] if line_requirement(line, mission) == key
        )
        total += min(int(requirement["quantity"]), available)
    return total


def _resilient_alternative(
    mission: dict[str, Any], baseline: dict[str, Any], quotes: list[dict[str, Any]], names: dict[str, str]
) -> dict[str, Any]:
    configured = Decimal(str(mission.get("max_supplier_share") or "1"))
    max_share = min(configured, RESILIENT_MAX_SHARE)
    constrained_mission = {**deepcopy(mission), "max_supplier_share": str(max_share)}
    outcome = solve(constrained_mission, quotes)
    if outcome["status"] != "feasible":
        return {
            "status": "UNAVAILABLE",
            "constraint": {"max_supplier_share": str(max_share)},
            "reason": "No feasible plan satisfies the 50% supplier concentration guardrail.",
        }
    proposal = {**outcome, "allocations": outcome["allocations"]}
    # Stress-test the alternative under the mission's real recovery rules, exactly like the current plan: after a
    # real supplier loss the replan uses the mission's constraints, not this proposal's stronger guardrail.
    scenarios = [_scenario(mission, proposal, quotes, supplier_id, names)
                 for supplier_id in _allocated_supplier_ids(proposal)]
    survivable = sum(row["feasible"] for row in scenarios)
    return {
        "status": "AVAILABLE",
        "provenance": HYPOTHETICAL_PROVENANCE,
        "constraint": {"max_supplier_share": str(max_share)},
        "total_cost": outcome["total_cost"],
        "added_cost": money(cents(outcome["total_cost"]) - cents(baseline["total_cost"])),
        "allocations": [{**row, "supplier": names.get(row["supplier_id"], row["supplier_email"])}
                        for row in outcome["allocations"]],
        "supplier_count": len(_allocated_supplier_ids(proposal)),
        "n1_survivability": {"survives": survivable, "tested": len(scenarios)},
        "scenarios": scenarios,
        "improvement": "Constrained optimization; no supplier may receive more than 50% of required units."
        if max_share == RESILIENT_MAX_SHARE else "Preserves the mission's stricter supplier concentration guardrail.",
    }


def build_continuity_analysis(
    mission: dict[str, Any],
    plan: dict[str, Any],
    eligible_quotes: list[dict[str, Any]],
    *,
    input_hash: str,
    quote_versions: list[dict[str, Any]],
    policy_fingerprint: str,
    evidence_fingerprint: str,
    optimizer_input_fingerprint: str,
    created_at: str,
    progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, Any]:
    """Build a deterministic counterfactual record from a fixed input snapshot.

    ``progress(done, total, label)`` reports finished scenario groups: one N-1 scenario and one failure
    frontier per allocated supplier, plus the resilient alternative (which includes its own N-1).
    """

    if plan["status"] not in {"feasible", "approved"}:
        raise ValueError("Only a current feasible or approved plan can be stress-tested")
    names = _supplier_names(plan)
    supplier_ids = _allocated_supplier_ids(plan)
    total_steps = 2 * len(supplier_ids) + 1
    done = 0

    def step(label: str) -> None:
        nonlocal done
        done += 1
        if progress:
            progress(done, total_steps, label)

    scenarios = []
    for supplier_id in supplier_ids:
        scenarios.append(_scenario(mission, plan, eligible_quotes, supplier_id, names))
        step(f"Stress test: {names.get(supplier_id, supplier_id)} unavailable")
    survivable = sum(row["feasible"] for row in scenarios)
    units = _allocation_units(plan)
    total_units = sum(units.values())
    concentration = [
        {
            "supplier_id": supplier_id,
            "supplier": names.get(supplier_id, supplier_id),
            "units": supplier_units,
            "unit_share": round(supplier_units / total_units, 4) if total_units else 0,
        }
        for supplier_id, supplier_units in sorted(units.items(), key=lambda item: (-item[1], item[0]))
    ]
    latest_delivery = _latest_delivery(plan)
    deadline_slack = None
    if latest_delivery:
        deadline_slack = max(0, round((_dt(mission["delivery_deadline"]) - _dt(latest_delivery)).total_seconds() / 3600, 2))
    frontiers = []
    for supplier_id in supplier_ids:
        frontiers.append(_frontier_for_supplier(mission, eligible_quotes, supplier_id, names))
        step(f"Failure frontier: {names.get(supplier_id, supplier_id)}")
    price_values = [row["price"] for row in frontiers if row.get("price")]
    delay_values = [row["delay"] for row in frontiers if row.get("delay")]
    capacity_values = [row["capacity"] for row in frontiers if row.get("capacity")]
    unrecoverable = [row for row in scenarios if not row["feasible"]]
    critical = max(unrecoverable, key=lambda row: units.get(row["supplier_id"], 0), default=None)
    alternative = _resilient_alternative(mission, plan, eligible_quotes, names)
    step("Resilient alternative")
    return {
        "status": "COMPLETE",
        "provenance": HYPOTHETICAL_PROVENANCE,
        "counterfactual_label": "HYPOTHETICAL STRESS TEST — does not change a supplier quote, plan, or approval.",
        "input_hash": input_hash,
        "created_at": created_at,
        "mission_id": mission["id"],
        "plan_id": plan["id"],
        "plan_version": plan["version"],
        "plan_hash": plan["plan_hash"],
        "quote_versions": quote_versions,
        "policy_fingerprint": policy_fingerprint,
        "evidence_fingerprint": evidence_fingerprint,
        "optimizer_input_fingerprint": optimizer_input_fingerprint,
        "baseline": {
            "total_cost": plan["total_cost"],
            "remaining_budget": plan["remaining_budget"],
            "latest_delivery": latest_delivery,
            "supplier_concentration": concentration,
        },
        "metrics": {
            "n1_survivability": {"survives": survivable, "tested": len(scenarios)},
            "budget_headroom": plan["remaining_budget"],
            "deadline_slack_hours": deadline_slack,
            "largest_supplier_concentration": concentration[0]["unit_share"] if concentration else 0,
            "alternative_eligible_capacity": _alternative_capacity(mission, plan, eligible_quotes),
            "price_shock_tolerance": min(price_values, key=lambda row: row["increase_basis_points"], default=None),
            "delay_tolerance": min(delay_values, key=lambda row: row["hours"], default=None),
            "capacity_loss_tolerance": min(capacity_values, key=lambda row: row["loss_units"], default=None),
            "critical_supplier": {
                "supplier_id": critical["supplier_id"], "supplier": critical["supplier"],
                "reason": "N-1 stress test is unrecoverable.",
            } if critical else None,
        },
        "n1_scenarios": scenarios,
        "failure_frontier": frontiers,
        "resilient_alternative": alternative,
    }


# --------------------------------------------------------------------------- actual vs. hypothetical

def _quote_change(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Exact, signed differences between two persisted versions of one quote."""

    old_lines, new_lines = before.get("lines", []), after.get("lines", [])
    price_bps: list[int] = []
    delays: list[float] = []
    for old, new in zip(old_lines, new_lines):
        old_cents, new_cents = cents(old["unit_price"]), cents(new["unit_price"])
        if old_cents:
            price_bps.append(int((Decimal(new_cents - old_cents) * 10_000 / old_cents).to_integral_value()))
        delays.append((_dt(new["delivery_date"]) - _dt(old["delivery_date"])).total_seconds() / 3600)
    capacity_loss = (sum(int(row["available_quantity"]) for row in old_lines)
                     - sum(int(row["available_quantity"]) for row in new_lines))
    return {
        "price_change_basis_points": max(price_bps, default=0),
        "price_change_percent": round(max(price_bps, default=0) / 100, 2),
        "capacity_loss_units": capacity_loss,
        "delay_hours": round(max(delays, default=0.0), 2),
    }


def reality_check(
    prior_analysis: dict[str, Any] | None,
    plan: dict[str, Any],
    change: dict[str, Any],
) -> dict[str, Any]:
    """Compare one real supplier change with the stress test that was run *before* it happened.

    ``change`` = {supplier_id, supplier, kind: withdrawn|updated, source, before?, after?}. Nothing here
    predicts anything new: the earlier side is copied from the stored HYPOTHETICAL analysis, the actual side
    from persisted quote versions and the real replanned plan.
    """

    actual: dict[str, Any] = {
        "provenance": change.get("source", "USER_SUBMITTED"),
        "supplier": change["supplier"],
        "kind": change["kind"],
        "plan_version": plan["version"],
        "plan_status": plan["status"],
        "plan_total_cost": plan["total_cost"] if plan["status"] in {"feasible", "approved"} else None,
    }
    result: dict[str, Any] = {"supplier_id": change["supplier_id"], "actual": actual, "earlier_stress_test": None,
                              "consistent": None}
    if not prior_analysis:
        result["note"] = "No stress test had been run on the plan this change disrupted."
        return result
    earlier: dict[str, Any] = {"provenance": HYPOTHETICAL_PROVENANCE, "analysis_id": prior_analysis.get("id"),
                               "plan_version": prior_analysis.get("plan_version"),
                               "created_at": prior_analysis.get("created_at")}
    feasible_now = plan["status"] in {"feasible", "approved"}
    if change["kind"] == "withdrawn":
        scenario = next((row for row in prior_analysis.get("n1_scenarios", [])
                         if row["supplier_id"] == change["supplier_id"]), None)
        actual["change"] = "Supplier withdrew its quote"
        if not scenario:
            result["note"] = "This supplier had no allocation in the stress-tested plan, so no N-1 scenario covered it."
            return result
        earlier.update(label=scenario["label"], predicted_status=scenario["status"],
                       predicted_cost=scenario.get("new_cost"), predicted_cost_delta=scenario.get("cost_delta"))
        result["consistent"] = (scenario["status"] == "RECOVERABLE") == feasible_now
    else:
        delta = _quote_change(change["before"], change["after"])
        actual["change"] = delta
        frontier = next((row for row in prior_analysis.get("failure_frontier", [])
                         if row["supplier_id"] == change["supplier_id"]), None)
        if frontier is None:
            result["note"] = "This supplier had no allocation in the stress-tested plan."
            return result
        tolerance = {
            "price_breakpoint_basis_points": (frontier.get("price") or {}).get("increase_basis_points"),
            "delay_breakpoint_hours": (frontier.get("delay") or {}).get("hours"),
            "capacity_breakpoint_units": (frontier.get("capacity") or {}).get("loss_units"),
        }
        breaks = []
        if tolerance["price_breakpoint_basis_points"] is not None and \
                delta["price_change_basis_points"] >= tolerance["price_breakpoint_basis_points"]:
            breaks.append("price")
        if tolerance["delay_breakpoint_hours"] is not None and delta["delay_hours"] >= tolerance["delay_breakpoint_hours"]:
            breaks.append("delay")
        if tolerance["capacity_breakpoint_units"] is not None and \
                delta["capacity_loss_units"] >= tolerance["capacity_breakpoint_units"]:
            breaks.append("capacity")
        changed = [name for name, value in (("price", delta["price_change_basis_points"]),
                                            ("delay", delta["delay_hours"]), ("capacity", delta["capacity_loss_units"]))
                   if value > 0]
        earlier.update(label=f"Stress test: {frontier['supplier']} failure frontier", tolerance=tolerance,
                       predicted_status="UNRECOVERABLE" if breaks else "RECOVERABLE",
                       crossed=breaks)
        if len(changed) > 1:
            result["note"] = ("The real change moved several dimensions at once; the stress test bounded each one "
                              "separately, so agreement is checked per dimension only.")
        if changed:
            result["consistent"] = bool(breaks) != feasible_now if len(changed) == 1 else None
    result["earlier_stress_test"] = earlier
    return result
