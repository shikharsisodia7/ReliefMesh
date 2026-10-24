from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import pulp


def cents(value: str | Decimal) -> int:
    amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(amount * 100)


def money(value: int) -> str:
    return f"{Decimal(value) / 100:.2f}"


def _dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def solve(mission: dict[str, Any], quotes: list[dict[str, Any]]) -> dict[str, Any]:
    """Solve a deterministic integer purchasing allocation from persisted quote lines."""

    now = datetime.now(UTC)
    deadline = _dt(mission["delivery_deadline"])
    requirements = {row["item"]: int(row["quantity"]) for row in mission["requirements"]}
    rejected: list[dict[str, str]] = []
    candidates: list[tuple[dict[str, Any], int, dict[str, Any]]] = []

    for quote in sorted(quotes, key=lambda row: row["id"]):
        if quote["status"] != "submitted":
            rejected.append({"quote_id": quote["id"], "reason": quote["status"]})
            continue
        if _dt(quote["expires_at"]) <= now:
            rejected.append({"quote_id": quote["id"], "reason": "expired"})
            continue
        usable_lines = 0
        for index, line in enumerate(quote["lines"]):
            if line["item"] not in requirements:
                continue
            if _dt(line["delivery_date"]) > deadline:
                continue
            candidates.append((quote, index, line))
            usable_lines += 1
        if not usable_lines:
            rejected.append({"quote_id": quote["id"], "reason": "no line meets the delivery requirement"})

    available_by_item: dict[str, int] = defaultdict(int)
    for _, _, line in candidates:
        available_by_item[line["item"]] += int(line["available_quantity"])

    problem = pulp.LpProblem("reliefmesh_procurement", pulp.LpMinimize)
    quantities: dict[tuple[str, int], pulp.LpVariable] = {}
    quote_active: dict[str, pulp.LpVariable] = {}
    quotes_by_id = {quote["id"]: quote for quote, _, _ in candidates}
    for quote_id in quotes_by_id:
        quote_active[quote_id] = problem.add_variable(
            f"active_{quote_id.replace('-', '_')}", cat="Binary"
        )
    for quote, index, line in candidates:
        key = (quote["id"], index)
        quantities[key] = problem.add_variable(
            f"q_{quote['id'].replace('-', '_')}_{index}", lowBound=0, cat="Integer"
        )
        problem += quantities[key] <= int(line["available_quantity"]) * quote_active[quote["id"]]

    for item, required in requirements.items():
        item_variables = [
            quantities[(quote["id"], index)]
            for quote, index, line in candidates
            if line["item"] == item
        ]
        problem += pulp.lpSum(item_variables) == required, f"coverage_{item}"

    procurement_cost = pulp.lpSum(
        cents(line["unit_price"]) * quantities[(quote["id"], index)]
        for quote, index, line in candidates
    )
    shipping_cost = pulp.lpSum(
        cents(quote["shipping_cost"]) * quote_active[quote_id]
        for quote_id, quote in quotes_by_id.items()
    )
    total_cost = procurement_cost + shipping_cost
    problem += total_cost <= cents(mission["budget"]), "budget"

    if mission.get("max_supplier_share"):
        maximum = float(mission["max_supplier_share"])
        total_units = sum(requirements.values())
        for supplier_id in {quote["supplier_id"] for quote, _, _ in candidates}:
            supplier_units = [
                quantities[(quote["id"], index)]
                for quote, index, _ in candidates
                if quote["supplier_id"] == supplier_id
            ]
            problem += pulp.lpSum(supplier_units) <= maximum * total_units, f"concentration_{supplier_id}"

    if mission.get("single_source_only") and quote_active:
        problem += pulp.lpSum(quote_active.values()) <= 1, "single_source"

    problem += total_cost
    solver = pulp.COIN_CMD(path=pulp.PULP_CBC_CMD.pulp_cbc_path, msg=False, timeLimit=8)
    status = problem.solve(solver)
    solver_status = pulp.LpStatus[status]
    if solver_status != "Optimal":
        shortages = []
        for item, required in requirements.items():
            available = available_by_item[item]
            cheapest = sorted(
                [cents(line["unit_price"]) for _, _, line in candidates if line["item"] == item]
            )
            reason = "inventory" if available < required else "budget"
            if not cheapest:
                reason = "delivery_or_quote_validity"
            shortages.append(
                {
                    "item": item,
                    "required": required,
                    "available": available,
                    "shortage": max(0, required - available),
                    "reason": reason,
                }
            )
        return {
            "status": "infeasible",
            "solver_status": solver_status,
            "allocations": [],
            "total_cost": "0.00",
            "shipping_cost": "0.00",
            "coverage": [],
            "remaining_budget": mission["budget"],
            "supplier_concentration": [],
            "binding_constraints": ["budget"] if any(row["reason"] == "budget" for row in shortages) else ["inventory"],
            "rejected_quotes": rejected,
            "shortages": shortages,
        }

    allocations = []
    supplier_costs: dict[str, int] = defaultdict(int)
    total_shipping = 0
    for quote_id, active in quote_active.items():
        if (active.value() or 0) >= 0.5:
            total_shipping += cents(quotes_by_id[quote_id]["shipping_cost"])
    for quote, index, line in candidates:
        quantity = int(round(quantities[(quote["id"], index)].value() or 0))
        if quantity:
            landed = cents(line["unit_price"]) * quantity
            supplier_costs[quote["supplier_id"]] += landed
            allocations.append(
                {
                    "quote_id": quote["id"],
                    "supplier_id": quote["supplier_id"],
                    "supplier_email": quote["supplier_email"],
                    "item": line["item"],
                    "quantity": quantity,
                    "unit_price": line["unit_price"],
                    "line_cost": money(landed),
                    "delivery_date": line["delivery_date"],
                }
            )
    total = int(round(pulp.value(total_cost)))
    concentrations = [
        {"supplier_id": supplier_id, "share": round(cost / total, 4) if total else 0}
        for supplier_id, cost in sorted(supplier_costs.items())
    ]
    coverage = [
        {"item": item, "required": required, "allocated": required} for item, required in requirements.items()
    ]
    binding = []
    if total == cents(mission["budget"]):
        binding.append("budget")
    if any(available_by_item[item] == required for item, required in requirements.items()):
        binding.append("inventory")
    return {
        "status": "feasible",
        "solver_status": solver_status,
        "allocations": sorted(allocations, key=lambda row: (row["supplier_email"], row["item"])),
        "total_cost": money(total),
        "shipping_cost": money(total_shipping),
        "coverage": coverage,
        "remaining_budget": money(cents(mission["budget"]) - total),
        "supplier_concentration": concentrations,
        "binding_constraints": binding,
        "rejected_quotes": rejected,
        "shortages": [],
    }
