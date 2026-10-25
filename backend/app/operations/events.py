"""Application events the procurement core emits. The operations layer reacts to them.

The core never calls Gmail, Slack, Calendar, or Drive directly; it records that something
happened and moves on. Emission never raises into the caller and never waits on a provider.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..core import Services

MISSION_CREATED = "mission_created"
MISSION_UPDATED = "mission_updated"
MISSION_CANCELLED = "mission_cancelled"
APPROVAL_REQUIRED = "approval_required"
PLAN_REPLANNED = "plan_replanned"
SUPPLIER_DISRUPTED = "supplier_disrupted"
PLAN_APPROVED = "plan_approved"
PURCHASE_ORDER_SENT = "purchase_order_sent"
PURCHASE_ORDER_ACCEPTED = "purchase_order_accepted"
FULFILLMENT_UPDATED = "fulfillment_updated"

EVENT_TYPES = (MISSION_CREATED, MISSION_UPDATED, MISSION_CANCELLED, APPROVAL_REQUIRED, PLAN_REPLANNED,
               SUPPLIER_DISRUPTED, PLAN_APPROVED, PURCHASE_ORDER_SENT, PURCHASE_ORDER_ACCEPTED, FULFILLMENT_UPDATED)


async def emit(services: Services, event_type: str, mission: dict[str, Any], *, subject_id: str,
               version: Any = None, data: dict[str, Any] | None = None) -> dict[str, Any] | None:
    ops = getattr(services, "ops", None)
    if ops is None:
        return None
    return await ops.emit(event_type, mission, subject_id=subject_id, version=version, data=data or {})
