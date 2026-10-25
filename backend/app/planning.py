"""Policy-gated planning, plan comparison, and stale-plan invalidation."""

from __future__ import annotations

import asyncio
import hashlib
from collections import defaultdict
from decimal import Decimal
from typing import Any

from .core import Services, audit, new_id, notify, now_iso
from .continuity import build_continuity_analysis
from .integrations.http import canonical_json
from .operations import events as ops_events
from .optimizer import cents, money, solve
from .policy.engine import EvidenceTTL, evaluate

_mission_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
REPLAN_TRIGGERS = {"supplier_disruption", "policy_change"}
# Purchase orders a supplier has received and not declined/cancelled: their units are already bought.
ACTIVE_ORDER_STATUSES = {"sent", "supplier_accepted", "in_fulfillment", "completed"}


async def continuity_input_snapshot(services: Services, mission: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    """Freeze every material input used by a continuity run.

    The policy fingerprint detects quote/evidence status changes.  The separate evidence
    and optimizer fingerprints make the binding inspectable instead of relying on a
    broad "current" flag.  No counterfactual input is persisted back into a quote.
    """

    report, quotes = await evaluate_mission(services, mission)
    supplier_ids = sorted({quote["supplier_id"] for quote in quotes})
    evidence_rows = []
    for supplier_id in supplier_ids:
        for record in await services.store.find(
            "evidence", organization_id=mission["organization_id"], subject_id=supplier_id
        ):
            evidence_rows.append({
                "id": record["id"], "supplier_id": supplier_id, "type": record.get("type"),
                "status": record.get("status"), "provenance": record.get("provenance"),
                "retrieved_at": record.get("retrieved_at"), "expires_at": record.get("expires_at"),
            })
    evidence_fingerprint = hashlib.sha256(canonical_json(sorted(evidence_rows, key=lambda row: row["id"])).encode()).hexdigest()
    quote_versions = sorted(
        [{"quote_id": quote["id"], "supplier_id": quote["supplier_id"], "version": quote.get("version", 1),
          "status": quote["status"], "provenance": quote.get("provenance")} for quote in quotes],
        key=lambda row: row["quote_id"],
    )
    eligible = [quote for quote in quotes if report["quotes"][quote["id"]]["eligible"]]
    optimizer_inputs = {
        "constraints": {
            "budget": mission["budget"], "delivery_deadline": mission["delivery_deadline"],
            "requirements": mission["requirements"], "max_supplier_share": mission.get("max_supplier_share"),
            "single_source_only": mission.get("single_source_only", False),
        },
        "eligible_quotes": [
            {"id": quote["id"], "version": quote.get("version", 1), "shipping_cost": quote["shipping_cost"],
             "lines": quote["lines"]}
            for quote in sorted(eligible, key=lambda row: row["id"])
        ],
    }
    optimizer_input_fingerprint = hashlib.sha256(canonical_json(optimizer_inputs).encode()).hexdigest()
    orders = await services.store.find("purchase_orders", mission_id=mission["id"])
    commitment_fingerprint = hashlib.sha256(canonical_json([
        {"id": order["id"], "plan_id": order.get("plan_id"), "status": order["status"], "lines": [
            {"quote_id": line.get("quote_id"), "requirement_id": line.get("requirement_id"),
             "quantity": line.get("quantity"), "line_cost": line.get("line_cost")}
            for line in order.get("lines", [])
        ]}
        for order in sorted(orders, key=lambda row: row["id"])
    ]).encode()).hexdigest()
    binding = {
        "mission_id": mission["id"], "plan_id": plan["id"], "plan_version": plan["version"],
        "plan_hash": plan["plan_hash"], "quote_versions": quote_versions,
        "policy_fingerprint": report["fingerprint"], "evidence_fingerprint": evidence_fingerprint,
        "optimizer_input_fingerprint": optimizer_input_fingerprint,
        "commitment_fingerprint": commitment_fingerprint,
    }
    return {
        "report": report, "quotes": quotes, "eligible_quotes": eligible, "quote_versions": quote_versions,
        "policy_fingerprint": report["fingerprint"], "evidence_fingerprint": evidence_fingerprint,
        "optimizer_input_fingerprint": optimizer_input_fingerprint,
        "commitment_fingerprint": commitment_fingerprint, "orders": orders,
        "input_hash": hashlib.sha256(canonical_json(binding).encode()).hexdigest(),
    }


async def compute_continuity_analysis(services: Services, mission_id: str, plan_id: str) -> dict[str, Any]:
    """Persist a counterfactual analysis only if its pinned inputs remain current.

    The same mission lock serializes plan construction and continuity snapshots.  A
    final input re-check protects the record from concurrent supplier edits, which do
    not take this lock because they must remain responsive.
    """

    async with _mission_locks[mission_id]:
        mission = await services.store.get("missions", mission_id)
        plan = await services.store.get("plans", plan_id)
        if not mission or not plan or plan["mission_id"] != mission_id:
            raise RuntimeError("continuity analysis target no longer exists")
        if plan["status"] not in {"feasible", "approved"}:
            return {"status": "skipped", "reason": "plan is not current", "plan_id": plan_id}
        snapshot = await continuity_input_snapshot(services, mission, plan)
        cached = [row for row in await services.store.find("continuity_analyses", mission_id=mission_id)
                  if row.get("plan_id") == plan_id and row.get("input_hash") == snapshot["input_hash"]
                  and row.get("status") == "COMPLETE"]
        if cached:
            return {"status": "cached", "analysis_id": cached[-1]["id"], "plan_id": plan_id}
        # Active purchase orders are fixed historical commitments, not inventory the
        # optimizer is free to move. Stress-test only the uncommitted remainder and
        # remove already-consumed quote capacity, using the same residual-problem
        # transformation as a real replan.
        commitments = committed_lines(snapshot["orders"])
        analysis_mission = mission
        analysis_plan = plan
        analysis_quotes = snapshot["eligible_quotes"]
        scope: dict[str, Any] = {
            "kind": "FULL_MISSION",
            "statement": "All feasible-plan requirements remain available for hypothetical reallocation.",
            "fixed_commitment_cost": "0.00",
            "fixed_commitment_count": 0,
        }
        if commitments:
            remaining, adjusted_quotes, committed_cost = residual_problem(mission, snapshot["quotes"], commitments)
            eligible_ids = {quote["id"] for quote in snapshot["eligible_quotes"]}
            outstanding = [row for row in plan["allocations"] if not row.get("committed")]
            analysis_mission = remaining
            analysis_quotes = [quote for quote in adjusted_quotes if quote["id"] in eligible_ids]
            analysis_plan = {
                **plan,
                "allocations": outstanding,
                "total_cost": plan.get("new_spend") or money(cents(plan["total_cost"]) - committed_cost),
                "latest_delivery": max((row["delivery_date"] for row in outstanding), default=None),
            }
            scope = {
                "kind": "UNCOMMITTED_REMAINDER" if remaining["requirements"] else "NO_UNCOMMITTED_REQUIREMENTS",
                "statement": (
                    "Only requirements not already committed on active purchase orders are stress-tested."
                    if remaining["requirements"]
                    else "All requirements are already committed on active purchase orders; no uncommitted procurement can be reallocated."
                ),
                "fixed_commitment_cost": money(committed_cost),
                "fixed_commitment_count": len(commitments),
                "full_plan_total_cost": plan["total_cost"],
            }
        if not analysis_mission["requirements"]:
            analysis = {
                "status": "COMPLETE", "provenance": "HYPOTHETICAL",
                "counterfactual_label": "HYPOTHETICAL STRESS TEST — does not change a supplier quote, plan, or approval.",
                "input_hash": snapshot["input_hash"], "created_at": now_iso(), "mission_id": mission["id"],
                "plan_id": plan["id"], "plan_version": plan["version"], "plan_hash": plan["plan_hash"],
                "quote_versions": snapshot["quote_versions"], "policy_fingerprint": snapshot["policy_fingerprint"],
                "evidence_fingerprint": snapshot["evidence_fingerprint"],
                "optimizer_input_fingerprint": snapshot["optimizer_input_fingerprint"],
                "baseline": {"total_cost": "0.00", "remaining_budget": plan["remaining_budget"],
                             "latest_delivery": None, "supplier_concentration": []},
                "metrics": {"n1_survivability": {"survives": 0, "tested": 0},
                            "budget_headroom": plan["remaining_budget"], "deadline_slack_hours": None,
                            "largest_supplier_concentration": 0, "alternative_eligible_capacity": 0,
                            "price_shock_tolerance": None, "delay_tolerance": None,
                            "capacity_loss_tolerance": None, "critical_supplier": None},
                "n1_scenarios": [], "failure_frontier": [],
                "resilient_alternative": {"status": "UNAVAILABLE", "reason": scope["statement"]},
            }
        else:
            analysis = build_continuity_analysis(
                analysis_mission, analysis_plan, analysis_quotes, input_hash=snapshot["input_hash"],
                quote_versions=snapshot["quote_versions"], policy_fingerprint=snapshot["policy_fingerprint"],
                evidence_fingerprint=snapshot["evidence_fingerprint"],
                optimizer_input_fingerprint=snapshot["optimizer_input_fingerprint"], created_at=now_iso(),
            )
        analysis["scope"] = scope
        analysis["commitment_fingerprint"] = snapshot["commitment_fingerprint"]
        current = await continuity_input_snapshot(services, mission, plan)
        if current["input_hash"] != snapshot["input_hash"]:
            return {"status": "stale_before_persist", "reason": "quote, evidence, or policy changed", "plan_id": plan_id}
        analysis["id"] = new_id()
        analysis["organization_id"] = mission["organization_id"]
        await services.store.insert("continuity_analyses", analysis)
        await audit("continuity.computed", None, mission["organization_id"], mission_id, "continuity_analysis",
                    analysis["id"], services, {
                        "plan_id": plan_id, "plan_version": plan["version"], "input_hash": analysis["input_hash"],
                        "provenance": analysis["provenance"],
                        "n1": analysis["metrics"]["n1_survivability"],
                    })
        return {"status": "complete", "analysis_id": analysis["id"], "plan_id": plan_id,
                "plan_version": plan["version"]}


async def mark_continuity_stale(services: Services, mission: dict[str, Any], actor_id: str | None, reason: str) -> int:
    """Invalidate visible continuity output after a real input changes.

    Historical analyses remain available as historical *HYPOTHETICAL* work, but never
    present themselves as the current plan's resilience posture.
    """

    changed = 0
    for analysis in await services.store.find("continuity_analyses", mission_id=mission["id"]):
        if analysis.get("status") != "COMPLETE":
            continue
        analysis.update(status="STALE", stale_at=now_iso(), stale_reason=reason)
        await services.store.replace("continuity_analyses", analysis["id"], analysis)
        changed += 1
        await audit("continuity.stale", actor_id, mission["organization_id"], mission["id"],
                    "continuity_analysis", analysis["id"], services,
                    {"plan_id": analysis.get("plan_id"), "reason": reason})
    return changed


def continuity_digital_twin(
    mission: dict[str, Any], plan: dict[str, Any] | None, quotes: list[dict[str, Any]],
    approvals: list[dict[str, Any]], orders: list[dict[str, Any]], analysis: dict[str, Any] | None,
) -> dict[str, Any]:
    """A graph-shaped, persisted-state view for the UI and judge tooling."""

    supplier_ids = sorted({quote["supplier_id"] for quote in quotes})
    names = {
        supplier_id: row.get("legal_name") or row.get("email") or supplier_id
        for supplier_id, row in ((plan or {}).get("policy", {}).get("suppliers", {}) or {}).items()
    }
    nodes = [
        {"id": f"mission:{mission['id']}", "type": "mission", "label": mission["name"], "status": mission["status"]},
        *[{"id": f"requirement:{row.get('id') or row['item']}", "type": "requirement", "label": row["item"],
           "quantity": row["quantity"]} for row in mission["requirements"]],
        *[{"id": f"supplier:{supplier_id}", "type": "supplier", "label": names.get(supplier_id, supplier_id),
           "quote_count": sum(quote["supplier_id"] == supplier_id for quote in quotes)} for supplier_id in supplier_ids],
        *([{ "id": f"plan:{plan['id']}", "type": "plan", "label": f"Plan v{plan['version']}",
             "status": plan["status"], "cost": plan["total_cost"]}] if plan else []),
        *[{"id": f"approval:{row['id']}", "type": "approval", "label": row["status"],
           "plan_version": row.get("plan_version")} for row in approvals],
        *[{"id": f"po:{row['id']}", "type": "purchase_order", "label": row["po_number"],
           "status": row["status"]} for row in orders],
        *([{ "id": f"continuity:{analysis['id']}", "type": "continuity_analysis", "label": "N-1 stress test",
             "status": analysis["status"], "provenance": analysis.get("provenance")} ] if analysis else []),
    ]
    edges = [
        {"from": f"mission:{mission['id']}", "to": f"requirement:{row.get('id') or row['item']}", "type": "requires"}
        for row in mission["requirements"]
    ]
    edges.extend({"from": f"mission:{mission['id']}", "to": f"supplier:{supplier_id}", "type": "received_quote"}
                 for supplier_id in supplier_ids)
    if plan:
        edges.append({"from": f"mission:{mission['id']}", "to": f"plan:{plan['id']}", "type": "planned"})
        edges.extend({"from": f"supplier:{row['supplier_id']}", "to": f"plan:{plan['id']}", "type": "allocated",
                      "quantity": row["quantity"]} for row in plan.get("allocations", []))
        edges.extend({"from": f"plan:{plan['id']}", "to": f"approval:{row['id']}", "type": "approved_by"}
                     for row in approvals if row.get("plan_id") == plan["id"])
        edges.extend({"from": f"plan:{plan['id']}", "to": f"po:{row['id']}", "type": "issued_as"}
                     for row in orders if row.get("plan_id") == plan["id"])
    if analysis and plan:
        edges.append({"from": f"plan:{plan['id']}", "to": f"continuity:{analysis['id']}", "type": "stress_tested"})
    return {
        "label": "Procurement Digital Twin",
        "provenance": "PERSISTED_APPLICATION_STATE",
        "nodes": nodes,
        "edges": edges,
        "disaster_context": mission.get("emergency_event"),
    }


def committed_lines(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**line, "committed": True, "po_number": order["po_number"], "purchase_order_id": order["id"]}
            for order in orders if order["status"] in ACTIVE_ORDER_STATUSES for line in order["lines"]]


def residual_problem(mission: dict[str, Any], quotes: list[dict[str, Any]],
                     commitments: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
    """What is still unbought: requirements, budget, and quote inventory minus active purchase orders."""

    from .requirements import requirement_key

    covered: dict[str, int] = defaultdict(int)
    taken: dict[tuple[str, str], int] = defaultdict(int)
    spent = 0
    for line in commitments:
        covered[line["requirement_id"]] += line["quantity"]
        taken[(line["quote_id"], line["requirement_id"])] += line["quantity"]
        spent += cents(line["line_cost"])
    by_id = {quote["id"]: quote for quote in quotes}
    spent += sum(cents(by_id[qid].get("shipping_cost") or "0") for qid in {line["quote_id"] for line in commitments}
                 if qid in by_id)
    requirements = [{**row, "quantity": row["quantity"] - covered.get(requirement_key(row), 0)}
                    for row in mission["requirements"] if row["quantity"] > covered.get(requirement_key(row), 0)]
    remaining = {**mission, "requirements": requirements, "budget": money(max(0, cents(mission["budget"]) - spent))}
    adjusted = []
    for quote in quotes:
        lines = []
        for line in quote["lines"]:
            left = line["available_quantity"] - taken.get((quote["id"], line.get("requirement_id")), 0)
            if left > 0:
                lines.append({**line, "available_quantity": left})
        if lines:
            adjusted.append({**quote, "lines": lines})
    return remaining, adjusted, spent


def merge_commitments(mission: dict[str, Any], outcome: dict[str, Any], commitments: list[dict[str, Any]],
                      spent: int) -> dict[str, Any]:
    """Present the full picture: fixed purchase-order lines plus the optimized remainder."""

    new_spend = cents(outcome["total_cost"])
    total = spent + new_spend
    merged = {**outcome, "allocations": commitments + outcome["allocations"], "committed_cost": money(spent),
              "new_spend": money(new_spend)}
    if outcome["status"] == "feasible":
        merged["total_cost"] = money(total)
        merged["remaining_budget"] = money(cents(mission["budget"]) - total)
        merged["coverage"] = [{"item": row["item"], "requirement_id": row.get("id"), "required": row["quantity"],
                               "allocated": row["quantity"]} for row in mission["requirements"]]
    return merged


def evidence_ttl(services: Services) -> EvidenceTTL:
    settings = services.settings
    return EvidenceTTL(settings.ofac_evidence_ttl_hours, settings.sam_evidence_ttl_hours,
                       settings.fda_evidence_ttl_hours, settings.crs_evidence_ttl_hours)


async def mission_suppliers(services: Services, mission: dict[str, Any],
                            quotes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    suppliers: dict[str, dict[str, Any]] = {}
    for quote in quotes:
        supplier = await services.store.get("suppliers", quote["supplier_id"])
        suppliers[quote["supplier_id"]] = supplier or {"id": quote["supplier_id"], "email": quote["supplier_email"]}
    return suppliers


async def evaluate_mission(services: Services, mission: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    quotes = await services.store.find("quotes", mission_id=mission["id"])
    suppliers = await mission_suppliers(services, mission, quotes)
    evidence = {
        sid: await services.store.find("evidence", organization_id=mission["organization_id"], subject_id=sid)
        for sid in suppliers
    }
    reviews = {
        sid: await services.store.find("supplier_reviews", organization_id=mission["organization_id"], supplier_id=sid)
        for sid in suppliers
    }
    report = evaluate(mission, quotes, suppliers, evidence, reviews, ttl=evidence_ttl(services))
    return report, quotes


def plan_hash(plan: dict[str, Any]) -> str:
    material = {
        "mission_id": plan["mission_id"],
        "version": plan["version"],
        "status": "feasible" if plan["status"] in {"feasible", "approved"} else plan["status"],
        "currency": plan.get("currency"),
        "total_cost": plan["total_cost"],
        "allocations": [
            [row["quote_id"], row["supplier_id"], row["item"], row["quantity"], row["unit_price"]]
            for row in plan["allocations"]
        ],
        "policy_fingerprint": (plan.get("policy") or {}).get("fingerprint"),
    }
    return hashlib.sha256(canonical_json(material).encode()).hexdigest()


def _supplier_totals(plan: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    totals: dict[str, dict[str, Any]] = {}
    if not plan:
        return totals
    for row in plan["allocations"]:
        entry = totals.setdefault(row["supplier_id"], {"units": 0, "cost": Decimal("0"), "email": row["supplier_email"]})
        entry["units"] += row["quantity"]
        entry["cost"] += Decimal(row["line_cost"])
    return totals


def describe_difference(prior: dict[str, Any] | None, plan: dict[str, Any],
                        trigger_detail: list[dict[str, Any]] | None) -> dict[str, Any]:
    before = _supplier_totals(prior)
    after = _supplier_totals(plan)
    names = {
        sid: (row.get("legal_name") or row.get("email"))
        for sid, row in ((plan.get("policy") or {}).get("suppliers") or {}).items()
    }
    supplier_delta = []
    for sid in sorted(set(before) | set(after)):
        b, a = before.get(sid), after.get(sid)
        supplier_delta.append({
            "supplier_id": sid,
            "supplier": names.get(sid) or (a or b or {}).get("email"),
            "units_before": b["units"] if b else 0,
            "units_after": a["units"] if a else 0,
            "cost_before": f"{b['cost']:.2f}" if b else "0.00",
            "cost_after": f"{a['cost']:.2f}" if a else "0.00",
        })
    why: list[str] = [item["summary"] for item in (trigger_detail or []) if item.get("summary")]
    if prior:
        old_status = {sid: row["status"] for sid, row in ((prior.get("policy") or {}).get("suppliers") or {}).items()}
        for sid, row in ((plan.get("policy") or {}).get("suppliers") or {}).items():
            if sid in old_status and old_status[sid] != row["status"]:
                why.append(f"{names.get(sid)} policy status changed {old_status[sid]} -> {row['status']}")
    cost_before = Decimal(prior["total_cost"]) if prior and prior["status"] != "infeasible" else None
    cost_after = Decimal(plan["total_cost"]) if plan["status"] != "infeasible" else None
    return {
        "previous_plan_id": prior["id"] if prior else None,
        "previous_version": prior["version"] if prior else None,
        "previous_status": prior["status"] if prior else None,
        "total_cost_before": prior["total_cost"] if prior else None,
        "total_cost_after": plan["total_cost"],
        "cost_delta": f"{cost_after - cost_before:+.2f}" if cost_before is not None and cost_after is not None else None,
        "allocation_changed": {k: v["units"] for k, v in before.items()} != {k: v["units"] for k, v in after.items()},
        "supplier_delta": supplier_delta,
        "why": why,
    }


async def compute_plan(services: Services, mission_id: str, trigger: str,
                       trigger_detail: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    async with _mission_locks[mission_id]:
        mission = await services.store.get("missions", mission_id)
        if not mission:
            raise RuntimeError(f"mission {mission_id} disappeared while optimizing")
        report, quotes = await evaluate_mission(services, mission)
        eligible = [quote for quote in quotes if report["quotes"][quote["id"]]["eligible"]]
        commitments = committed_lines(await services.store.find("purchase_orders", mission_id=mission_id))
        if commitments:
            remaining, open_quotes, spent = residual_problem(mission, quotes, commitments)
            open_ids = {quote["id"] for quote in eligible}
            open_quotes = [quote for quote in open_quotes if quote["id"] in open_ids]
            outcome = solve(remaining, open_quotes) if remaining["requirements"] else {
                "status": "feasible", "solver_status": "already_covered", "allocations": [], "total_cost": "0.00",
                "shipping_cost": "0.00", "coverage": [], "remaining_budget": remaining["budget"],
                "supplier_concentration": [], "binding_constraints": [], "rejected_quotes": [], "shortages": []}
            outcome = merge_commitments(mission, outcome, commitments, spent)
        else:
            outcome = solve(mission, eligible)
        by_id = {quote["id"]: quote for quote in quotes}
        policy_rejections = []
        for quote_id, row in sorted(report["quotes"].items()):
            if row["eligible"]:
                continue
            blocking = [d for d in row["decisions"] if d["status"] in {"NEEDS_REVIEW", "BLOCK"}]
            supplier_blocking = [
                d for d in report["suppliers"][row["supplier_id"]]["decisions"] if d["status"] in {"NEEDS_REVIEW", "BLOCK"}
            ]
            policy_rejections.append({
                "quote_id": quote_id,
                "supplier_id": row["supplier_id"],
                "supplier_email": by_id[quote_id]["supplier_email"],
                "reason": f"policy:{row['status']}",
                "rules": [d["rule_id"] for d in blocking + supplier_blocking],
                "explanations": [d["reason"] for d in blocking + supplier_blocking],
            })
        outcome["rejected_quotes"] = policy_rejections + outcome["rejected_quotes"]
        existing = await services.store.find("plans", mission_id=mission_id)
        prior = max(existing, key=lambda plan: plan["version"]) if existing else None
        latest_delivery = max((row["delivery_date"] for row in outcome["allocations"]), default=None)
        plan = {
            "id": new_id(),
            "mission_id": mission_id,
            "organization_id": mission["organization_id"],
            "version": (prior["version"] if prior else 0) + 1,
            "trigger": trigger,
            "trigger_detail": trigger_detail or [],
            "computed_at": now_iso(),
            "currency": mission.get("currency", "USD"),
            "constraints": {
                "budget": mission["budget"],
                "delivery_deadline": mission["delivery_deadline"],
                "max_supplier_share": mission.get("max_supplier_share"),
                "single_source_only": mission.get("single_source_only", False),
                "requirements": mission["requirements"],
            },
            "latest_delivery": latest_delivery,
            **outcome,
            "policy": {
                "fingerprint": report["fingerprint"],
                "evaluated_at": report["evaluated_at"],
                "eligible_quote_ids": report["eligible_quote_ids"],
                "suppliers": report["suppliers"],
                "quotes": report["quotes"],
            },
        }
        plan["difference"] = describe_difference(prior, plan, trigger_detail)
        plan["plan_hash"] = plan_hash(plan)
        await services.store.insert("plans", plan)
        await audit("plan.computed", None, mission["organization_id"], mission_id, "plan", plan["id"], services, {
            "version": plan["version"], "status": plan["status"], "trigger": trigger,
            "plan_hash": plan["plan_hash"], "total_cost": plan["total_cost"],
            "policy_fingerprint": report["fingerprint"],
        })
        if plan["status"] == "feasible" or (prior and trigger in REPLAN_TRIGGERS):
            await ops_events.emit(
                services, ops_events.PLAN_REPLANNED if prior and trigger in REPLAN_TRIGGERS
                else ops_events.APPROVAL_REQUIRED, mission, subject_id=plan["id"], version=plan["version"],
                data={"plan_id": plan["id"], "trigger": trigger})
        # Counterfactual work is durable and asynchronous. It never changes this
        # plan; its result is bound to an exact input hash before display.
        if plan["status"] == "feasible" and services.settings.continuity_engine_enabled:
            from .jobs import enqueue  # avoids a module cycle during app wiring

            await enqueue(services, "continuity_analysis", mission, coalesce=False,
                          payload={"plan_id": plan["id"]},
                          trigger={"kind": "plan_computed", "plan_id": plan["id"], "at": now_iso()})
        return plan


async def invalidate_for_change(services: Services, mission: dict[str, Any], actor_id: str | None,
                                reason: str, cause: dict[str, Any] | None = None, emit: bool = True) -> list[int]:
    """Mark every current plan stale, invalidate its approvals, and void unsent POs.

    ``cause`` (supplier_id/supplier/failure_type) only enriches the operations alert.
    """

    affected: list[int] = []
    invalidated = flagged = 0
    plans = await services.store.find("plans", mission_id=mission["id"])
    for plan in sorted(plans, key=lambda row: row["version"]):
        if plan["status"] not in {"feasible", "approved"}:
            continue
        plan.update(status="stale", stale_at=now_iso(), stale_reason=reason)
        await services.store.replace("plans", plan["id"], plan)
        affected.append(plan["version"])
        await audit("plan.stale", actor_id, mission["organization_id"], mission["id"], "plan", plan["id"], services,
                    {"version": plan["version"], "reason": reason})
        await notify(services, mission, "plan_stale", f"Plan v{plan['version']} became stale: {reason}", "warning",
                     {"plan_id": plan["id"], "version": plan["version"]})
        for approval in await services.store.find("approvals", plan_id=plan["id"]):
            if approval["status"] != "active":
                continue
            approval.update(status="invalidated", invalidated_at=now_iso(), invalidation_reason=reason)
            invalidated += 1
            await services.store.replace("approvals", approval["id"], approval)
            await audit("approval.invalidated", actor_id, mission["organization_id"], mission["id"], "approval",
                        approval["id"], services, {"plan_id": plan["id"], "reason": reason})
            await notify(services, mission, "approval_invalidated",
                         f"Approval for plan v{plan['version']} (${approval['amount']}) was invalidated.", "warning",
                         {"approval_id": approval["id"], "plan_id": plan["id"]})
        for order in await services.store.find("purchase_orders", plan_id=plan["id"]):
            if order["status"] == "draft":
                order["status"] = "void"
                order["events"].append({"status": "void", "at": now_iso(), "actor_id": actor_id, "note": reason})
                await services.store.replace("purchase_orders", order["id"], order)
                await audit("purchase_order.voided", actor_id, mission["organization_id"], mission["id"],
                            "purchase_order", order["id"], services, {"reason": reason})
            elif order["status"] in {"sent", "supplier_accepted", "in_fulfillment"}:
                order["plan_stale"] = True
                flagged += 1
                await services.store.replace("purchase_orders", order["id"], order)
    if affected and emit:
        details = cause or {}
        await ops_events.emit(services, ops_events.SUPPLIER_DISRUPTED, mission,
                              subject_id=details.get("supplier_id") or "policy",
                              version=",".join(str(v) for v in affected), data={
                                  "reason": reason, "supplier": details.get("supplier"),
                                  "supplier_id": details.get("supplier_id"),
                                  "failure_type": details.get("failure_type") or "Policy or evidence change",
                                  "stale_versions": affected, "approvals_invalidated": invalidated,
                                  "sent_orders_affected": flagged, "replanning": "queued automatically"})
    # A prior counterfactual remains historical evidence only: quote, policy, or
    # evidence changes mean it must never be displayed as the current posture.
    if affected:
        await mark_continuity_stale(services, mission, actor_id, reason)
    return affected
