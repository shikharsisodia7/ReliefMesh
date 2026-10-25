"""Human-reviewed explanations of current recovery plans."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ..core import Services, audit, current_user, get_services, require_mission_access, secret
from ..integrations import anthropic

router = APIRouter()


def _recovery_snapshot(mission: dict[str, Any], plan: dict[str, Any],
                       previous: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, str]]:
    deadline = datetime.fromisoformat(str(mission["delivery_deadline"]).replace("Z", "+00:00"))
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=UTC)
    totals: dict[str, int] = defaultdict(int)
    on_time: dict[str, int] = defaultdict(int)
    undated: dict[str, int] = defaultdict(int)
    for row in plan.get("allocations", []):
        item = str(row.get("item") or "unknown item").lower()
        quantity = int(row.get("quantity") or 0)
        totals[item] += quantity
        try:
            arrival = datetime.fromisoformat(str(row.get("delivery_date")).replace("Z", "+00:00"))
            if arrival.tzinfo is None:
                arrival = arrival.replace(tzinfo=UTC)
            if arrival <= deadline:
                on_time[item] += quantity
        except (TypeError, ValueError):
            undated[item] += quantity
    coverage = []
    for row in mission.get("requirements", []):
        item = str(row["item"]).lower()
        required = int(row["quantity"])
        coverage.append({"item": item, "required": required, "planned": totals[item],
                         "planned_by_deadline": on_time[item],
                         "planned_without_delivery_date": undated[item],
                         "short_by_deadline": max(0, required - on_time[item])})
    facts = {
        "mission": {"name": mission.get("name"), "community_label": mission.get("community_label"),
                    "location": mission.get("delivery_location"), "delivery_deadline": deadline.isoformat(),
                    "requirements": mission.get("requirements", [])},
        "current_plan": {"version": plan.get("version"), "status": plan.get("status"),
                         "total_cost": plan.get("total_cost"), "latest_delivery": plan.get("latest_delivery"),
                         "plan_hash_prefix": str(plan.get("plan_hash", ""))[:16]},
        "previous_plan": ({"version": previous.get("version"), "status": previous.get("status"),
                           "total_cost": previous.get("total_cost")} if previous else None),
        "why_it_changed": (plan.get("difference") or {}).get("why") or [],
        "trigger": plan.get("trigger"),
        "trigger_details": [row.get("summary") for row in plan.get("trigger_detail", []) if row.get("summary")],
        "item_coverage": coverage,
        "shortages": plan.get("shortages") or [],
        "notice": "Allocations are planned quantities, not proof of delivery.",
    }
    source_labels = {
        "mission_request": "Mission request and deadline",
        "current_plan": "Current plan status and cost",
        "item_coverage": "Requested vs planned quantities and delivery dates",
    }
    if previous or facts["why_it_changed"] or facts["trigger_details"]:
        source_labels["plan_change"] = "Plan comparison and recorded change reason"
    return facts, source_labels


@router.post("/v1/missions/{mission_id}/recovery-explanation")
async def create_recovery_explanation(mission_id: str, user: dict = Depends(current_user),
                                     services: Services = Depends(get_services)) -> dict:
    mission, _ = await require_mission_access(mission_id, user, services)
    if user.get("role") != "coordinator":
        raise HTTPException(status_code=403, detail="Only coordinators can request a recovery explanation")
    if not mission.get("community_label"):
        raise HTTPException(status_code=409, detail="Name the specific community served before requesting a public-benefit explanation")
    plans = await services.store.find("plans", mission_id=mission_id)
    plan = max(plans, key=lambda row: row["version"]) if plans else None
    if not plan:
        raise HTTPException(status_code=409, detail="Build a recovery plan before requesting an explanation")
    if plan.get("status") == "stale":
        raise HTTPException(status_code=409, detail="Wait for the current recovery plan to finish recomputing")
    previous = next((row for row in plans if row.get("id") == (plan.get("difference") or {}).get("previous_plan_id")), None)
    services.assist_limiter.check(f"recovery-explanation:{user['id']}")
    facts, source_labels = _recovery_snapshot(mission, plan, previous)
    result = await anthropic.explain_recovery(
        services.hub, secret(services.settings.anthropic_api_key), services.settings.anthropic_model,
        facts, source_labels,
    )
    if result.status == "BLOCKED_EXTERNAL":
        raise HTTPException(status_code=503, detail={"code": "ANTHROPIC_NOT_CONFIGURED", "message": result.error})
    if not result.ok:
        raise HTTPException(status_code=502, detail={"code": "EXPLANATION_UNAVAILABLE",
                                                     "message": result.error or "Claude could not draft an explanation"})
    await audit("recovery.explanation_drafted", user["id"], mission["organization_id"], mission_id,
                "plan", plan["id"], services, {"model": result.meta.get("model"), "citations": result.data["citations"]})
    return {**result.data, "plan_id": plan["id"], "plan_version": plan["version"],
            "human_review_required": True,
            "notice": "Claude drafted this from mission and plan records. Review the citations; the plan and approval state are unchanged."}
