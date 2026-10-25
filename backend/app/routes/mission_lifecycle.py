"""Mission lifecycle changes after creation: move the delivery deadline, or cancel the mission.

Both are coordinator actions with procurement consequences, so they reuse the core's own
stale-plan path: current plans go stale, their approvals are invalidated, and unsent POs are
voided. A deadline change then replans against the new constraint; a cancellation does not.
Each emits an operations event so the Google Calendar mirror follows ReliefMesh, never leads it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..core import Services, audit, current_user, get_services, notify, now_iso, require_mission_access
from ..jobs import enqueue
from ..operations import events as ops_events
from ..planning import invalidate_for_change

router = APIRouter()
LIFECYCLE_ROLES = {"admin", "coordinator"}
OPEN_ORDER_STATUSES = {"sent", "supplier_accepted", "in_fulfillment"}


class DeadlineChangeRequest(BaseModel):
    delivery_deadline: datetime
    reason: str | None = Field(default=None, max_length=500)


class CancelMissionRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


async def editable_mission(mission_id: str, user: dict[str, Any], services: Services) -> dict[str, Any]:
    mission, membership = await require_mission_access(mission_id, user, services)
    if user["role"] != "coordinator" or membership["role"] not in LIFECYCLE_ROLES:
        raise HTTPException(status_code=403, detail="Only an organization administrator or coordinator can change "
                                                    "a mission")
    if mission.get("status") == "cancelled":
        raise HTTPException(status_code=409, detail="This mission is cancelled")
    return mission


@router.patch("/v1/missions/{mission_id}/deadline")
async def change_deadline(mission_id: str, payload: DeadlineChangeRequest, user: dict = Depends(current_user),
                          services: Services = Depends(get_services)) -> dict:
    mission = await editable_mission(mission_id, user, services)
    deadline = payload.delivery_deadline if payload.delivery_deadline.tzinfo else \
        payload.delivery_deadline.replace(tzinfo=UTC)
    if deadline <= datetime.now(UTC):
        raise HTTPException(status_code=422, detail="Delivery deadline must be in the future")
    before = mission["delivery_deadline"]
    mission["delivery_deadline"] = deadline.isoformat()
    mission["updated_at"] = now_iso()
    await services.store.replace("missions", mission_id, mission)
    reason = f"Delivery deadline changed {before[:16]}Z -> {mission['delivery_deadline'][:16]}Z" + (
        f": {payload.reason}" if payload.reason else "")
    await audit("mission.deadline_changed", user["id"], mission["organization_id"], mission_id, "mission", mission_id,
                services, {"before": before, "after": mission["delivery_deadline"], "reason": payload.reason})
    await notify(services, mission, "deadline_changed", reason, "warning", {"before": before})
    # The plan was optimized and approved against the old deadline, so it cannot carry over.
    stale = await invalidate_for_change(services, mission, user["id"], reason, emit=False)
    job = None
    if stale:
        job = await enqueue(services, "replan", mission, trigger={"kind": "deadline_change", "summary": reason,
                                                                  "at": now_iso()})
    await ops_events.emit(services, ops_events.MISSION_UPDATED, mission, subject_id=mission_id,
                          version=mission["delivery_deadline"],
                          data={"before": before, "after": mission["delivery_deadline"], "reason": reason,
                                "stale_versions": stale})
    return {**mission, "stale_plan_versions": stale, "replan_job_id": job["id"] if job else None}


@router.post("/v1/missions/{mission_id}/cancel")
async def cancel_mission(mission_id: str, payload: CancelMissionRequest, user: dict = Depends(current_user),
                         services: Services = Depends(get_services)) -> dict:
    mission = await editable_mission(mission_id, user, services)
    mission.update(status="cancelled", cancelled_at=now_iso(), cancelled_by=user["id"], cancel_reason=payload.reason)
    await services.store.replace("missions", mission_id, mission)
    reason = f"Mission cancelled: {payload.reason}"
    stale = await invalidate_for_change(services, mission, user["id"], reason, emit=False)
    # Issued orders are commitments with suppliers; cancelling the mission does not silently cancel them.
    open_orders = [order["po_number"] for order in await services.store.find("purchase_orders", mission_id=mission_id)
                   if order["status"] in OPEN_ORDER_STATUSES]
    await audit("mission.cancelled", user["id"], mission["organization_id"], mission_id, "mission", mission_id,
                services, {"reason": payload.reason, "stale_plans": stale, "open_purchase_orders": open_orders})
    await notify(services, mission, "mission_cancelled", reason, "critical", {"open_purchase_orders": open_orders})
    await ops_events.emit(services, ops_events.MISSION_CANCELLED, mission, subject_id=mission_id,
                          data={"reason": payload.reason, "stale_versions": stale, "open_orders": open_orders})
    return {**mission, "stale_plan_versions": stale, "open_purchase_orders": open_orders}
