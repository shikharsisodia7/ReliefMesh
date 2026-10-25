"""Emergency context: real NASA EONET events, NWS alerts, NASA FIRMS detections, OpenFEMA declarations."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ..core import Services, current_principal, get_services, require_mission_access, secret
from ..integrations import emergency

router = APIRouter()


def section(result: Any, data: Any = None) -> dict[str, Any]:
    return {
        "status": result.status,
        "provenance": result.provenance,
        "retrieved_at": result.retrieved_at,
        "source_url": result.source_url,
        "error": result.error,
        "data": result.data if data is None else data,
    }


@router.get("/v1/emergency-events")
async def emergency_events(category: str | None = None, services: Services = Depends(get_services)) -> list:
    result = await emergency.eonet_events(services.hub, category=category)
    if not result.ok:
        raise HTTPException(status_code=502, detail=f"NASA EONET is unavailable: {result.error}")
    return result.data


@router.get("/v1/emergency-events/{event_id}")
async def emergency_event(event_id: str, services: Services = Depends(get_services)) -> dict:
    result = await emergency.eonet_event(services.hub, event_id)
    if not result.ok:
        raise HTTPException(status_code=502, detail=f"NASA EONET event unavailable: {result.error}")
    return result.data


# California as a center and half-width in degrees; the landing page clips detections to the state outline.
CALIFORNIA_BOX = {"lat": 37.25, "lon": -119.3, "radius_deg": 5.25}


@router.get("/v1/fire-detections/california")
async def california_fire_detections(services: Services = Depends(get_services)) -> dict:
    """Public NASA FIRMS detections over California in the last 48 h, for the landing page map."""
    result = await emergency.firms_detections(services.hub, secret(services.settings.nasa_firms_map_key), days=2,
                                              **CALIFORNIA_BOX)
    points = [{"latitude": row["latitude"], "longitude": row["longitude"], "acquired_at": row["acquired_at"]}
              for row in result.data or []] if result.ok else []
    return {**section(result, data=points), "meta": result.meta if result.ok else {}}


async def build_context(services: Services, mission: dict[str, Any]) -> dict[str, Any]:
    event = mission.get("emergency_event")
    point = (event or {}).get("point")
    state = mission.get("delivery_state") or (event or {}).get("state")
    tasks: dict[str, Any] = {}
    if mission.get("emergency_event_id"):
        tasks["event"] = emergency.eonet_event(services.hub, mission["emergency_event_id"])
    in_us = bool(point and 18 <= point["lat"] <= 72 and -180 <= point["lon"] <= -60)
    if in_us:
        tasks["nws"] = emergency.nws_alerts(services.hub, lat=point["lat"], lon=point["lon"])
    elif state:
        tasks["nws"] = emergency.nws_alerts(services.hub, state=state)
    if point:
        tasks["firms"] = emergency.firms_detections(services.hub, secret(services.settings.nasa_firms_map_key),
                                                    lat=point["lat"], lon=point["lon"])
    fema_state = state or (event or {}).get("state")
    if fema_state:
        tasks["fema"] = emergency.fema_declarations(services.hub, fema_state)
    results = dict(zip(tasks, await asyncio.gather(*tasks.values()), strict=True))
    context: dict[str, Any] = {"mission_id": mission["id"], "delivery_state": state, "point": point}
    if "event" in results:
        live = results["event"]
        context["event"] = section(live) if live.ok else {
            **section(live, data=event), "provenance": "CACHED" if event else None,
            "note": "Showing the snapshot stored when the mission was created.",
        }
    else:
        context["event"] = None
    context["nws"] = section(results["nws"]) if "nws" in results else None
    if "nws" in results and results["nws"].ok:
        context["nws"]["scope"] = "point" if in_us else f"state {state}"
    context["firms"] = section(results["firms"]) if "firms" in results else None
    if context["firms"] and results["firms"].ok:
        context["firms"]["meta"] = results["firms"].meta
    context["fema"] = section(results["fema"]) if "fema" in results else None
    if context["fema"]:
        context["fema"]["note"] = "Declarations are administrative status, not live severity."
    return context


@router.get("/v1/missions/{mission_id}/context")
async def mission_context(mission_id: str, principal: dict = Depends(current_principal),
                          services: Services = Depends(get_services)) -> dict:
    mission, _ = await require_mission_access(mission_id, principal, services)
    return await build_context(services, mission)
