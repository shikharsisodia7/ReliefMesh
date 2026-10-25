"""Continuity Engine HTTP contract.

All scenarios returned here have ``provenance=HYPOTHETICAL``.  Starting or
viewing an analysis never changes real quote, supplier, policy, approval, or
purchase-order records.  A human coordinator may enqueue work; all organization
members who can read the mission may inspect the resulting evidence.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ..core import Services, current_principal, current_user, get_services, require_mission_access
from ..jobs import enqueue
from ..planning import continuity_digital_twin, continuity_input_snapshot

router = APIRouter()


def _latest(rows: list[dict]) -> dict | None:
    return max(rows, key=lambda row: row.get("created_at", "")) if rows else None


@router.post("/v1/plans/{plan_id}/continuity", status_code=status.HTTP_202_ACCEPTED)
async def run_continuity_analysis(
    plan_id: str, user: dict = Depends(current_user), services: Services = Depends(get_services)
) -> dict:
    """Queue a deterministic N-1 / failure-frontier analysis for one current plan."""

    if not services.settings.continuity_engine_enabled:
        raise HTTPException(status_code=404, detail="Continuity Engine is disabled")
    plan = await services.store.get("plans", plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    mission, membership = await require_mission_access(plan["mission_id"], user, services)
    if user["role"] != "coordinator" or membership["role"] not in {"admin", "coordinator"}:
        raise HTTPException(status_code=403, detail="Only a buyer coordinator can run continuity analysis")
    if plan["status"] not in {"feasible", "approved"}:
        raise HTTPException(status_code=409, detail="Continuity analysis requires a current feasible or approved plan")
    job = await enqueue(services, "continuity_analysis", mission, coalesce=False, payload={"plan_id": plan_id},
                        trigger={"kind": "manual_continuity", "plan_id": plan_id, "actor_id": user["id"]})
    return {"job_id": job["id"], "status": job["status"], "plan_id": plan_id,
            "provenance": "HYPOTHETICAL", "message": "Continuity analysis queued; no real supplier data changes."}


@router.get("/v1/missions/{mission_id}/continuity")
async def mission_continuity(
    mission_id: str, plan_id: str | None = None, principal: dict = Depends(current_principal),
    services: Services = Depends(get_services),
) -> dict:
    """Return a plan-bound analysis plus the persisted Procurement Digital Twin."""

    mission, _ = await require_mission_access(mission_id, principal, services)
    plans = await services.store.find("plans", mission_id=mission_id)
    plan = await services.store.get("plans", plan_id) if plan_id else (
        max(plans, key=lambda row: row["version"]) if plans else None
    )
    if plan and plan["mission_id"] != mission_id:
        raise HTTPException(status_code=404, detail="Plan does not belong to this mission")
    analyses = await services.store.find("continuity_analyses", mission_id=mission_id)
    matching = [row for row in analyses if not plan or row.get("plan_id") == plan["id"]]
    analysis = _latest(matching)
    analysis_state = "NOT_READY"
    if analysis:
        analysis_state = analysis.get("status", "STALE")
        if plan and analysis.get("status") == "COMPLETE":
            # A direct current-input check guards viewers even if an external write
            # slipped between a supplier change and its normal stale marker.
            snapshot = await continuity_input_snapshot(services, mission, plan)
            if plan["status"] not in {"feasible", "approved"} or snapshot["input_hash"] != analysis.get("input_hash"):
                analysis_state = "STALE"
                analysis = {**analysis, "status": "STALE", "stale_reason": "Continuity inputs changed after analysis."}
    active = [row for row in await services.store.find("jobs", mission_id=mission_id)
              if row.get("type") == "continuity_analysis" and row.get("status") in {"queued", "running"}
              and (not plan or row.get("payload", {}).get("plan_id") == plan["id"])]
    if active and analysis_state == "NOT_READY":
        analysis_state = "RUNNING"
    quotes = await services.store.find("quotes", mission_id=mission_id)
    approvals = await services.store.find("approvals", mission_id=mission_id)
    orders = await services.store.find("purchase_orders", mission_id=mission_id)
    return {
        "mission_id": mission_id,
        "plan_id": plan["id"] if plan else None,
        "plan_version": plan["version"] if plan else None,
        "state": analysis_state,
        "analysis": analysis,
        "active_jobs": [{"id": row["id"], "status": row["status"], "created_at": row["created_at"]} for row in active],
        "digital_twin": continuity_digital_twin(mission, plan, quotes, approvals, orders, analysis),
    }
