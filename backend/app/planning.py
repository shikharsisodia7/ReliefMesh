"""Policy-gated planning, plan comparison, and stale-plan invalidation."""

from __future__ import annotations

import asyncio
import hashlib
from collections import defaultdict
from decimal import Decimal
from typing import Any

from .core import Services, audit, new_id, notify, now_iso
from .integrations.http import canonical_json
from .optimizer import solve
from .policy.engine import EvidenceTTL, evaluate

_mission_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


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
        return plan


async def invalidate_for_change(services: Services, mission: dict[str, Any], actor_id: str | None,
                                reason: str) -> list[int]:
    """Mark every current plan stale, invalidate its approvals, and void unsent POs."""

    affected: list[int] = []
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
                await services.store.replace("purchase_orders", order["id"], order)
    return affected
