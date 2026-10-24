"""Emergency-context adapters: NASA EONET, NWS alerts, NASA FIRMS, OpenFEMA.

These sources describe the operating environment of a mission. They never decide
what to buy and never feed the optimizer directly.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any

from .http import AdapterResult, IntegrationHub

EONET_BASE = "https://eonet.gsfc.nasa.gov/api/v3"
NWS_BASE = "https://api.weather.gov"
FIRMS_BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
FEMA_URL = "https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries"

US_STATES = {
    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR", "CALIFORNIA": "CA", "COLORADO": "CO",
    "CONNECTICUT": "CT", "DELAWARE": "DE", "FLORIDA": "FL", "GEORGIA": "GA", "HAWAII": "HI", "IDAHO": "ID",
    "ILLINOIS": "IL", "INDIANA": "IN", "IOWA": "IA", "KANSAS": "KS", "KENTUCKY": "KY", "LOUISIANA": "LA",
    "MAINE": "ME", "MARYLAND": "MD", "MASSACHUSETTS": "MA", "MICHIGAN": "MI", "MINNESOTA": "MN",
    "MISSISSIPPI": "MS", "MISSOURI": "MO", "MONTANA": "MT", "NEBRASKA": "NE", "NEVADA": "NV",
    "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ", "NEW MEXICO": "NM", "NEW YORK": "NY", "NORTH CAROLINA": "NC",
    "NORTH DAKOTA": "ND", "OHIO": "OH", "OKLAHOMA": "OK", "OREGON": "OR", "PENNSYLVANIA": "PA",
    "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC", "SOUTH DAKOTA": "SD", "TENNESSEE": "TN", "TEXAS": "TX",
    "UTAH": "UT", "VERMONT": "VT", "VIRGINIA": "VA", "WASHINGTON": "WA", "WEST VIRGINIA": "WV",
    "WISCONSIN": "WI", "WYOMING": "WY", "DISTRICT OF COLUMBIA": "DC", "PUERTO RICO": "PR", "GUAM": "GU",
}
STATE_CODES = set(US_STATES.values())


def state_code(text: str | None) -> str | None:
    """Extract a US state/territory code from free text such as 'Oakland, CA' or '…, Florida'."""

    if not text:
        return None
    trailing = re.search(r",\s*([A-Za-z]{2})\.?\s*(?:\d{5}(?:-\d{4})?)?\s*$", text)
    if trailing and trailing.group(1).upper() in STATE_CODES:
        return trailing.group(1).upper()
    upper = text.upper()
    for name, code in sorted(US_STATES.items(), key=lambda pair: -len(pair[0])):
        if re.search(rf"\b{name}\b", upper):
            return code
    # Only uppercase two-letter tokens count, so English words like "in"/"or" never match.
    for token in reversed(re.findall(r"\b[A-Z]{2}\b", text)):
        if token in STATE_CODES:
            return token
    return None


def _point(geometry: dict[str, Any]) -> dict[str, float] | None:
    coordinates = geometry.get("coordinates")
    if geometry.get("type") == "Point" and isinstance(coordinates, list) and len(coordinates) >= 2:
        return {"lon": float(coordinates[0]), "lat": float(coordinates[1])}
    if geometry.get("type") == "Polygon" and coordinates:
        ring = coordinates[0]
        if ring:
            return {
                "lon": sum(float(p[0]) for p in ring) / len(ring),
                "lat": sum(float(p[1]) for p in ring) / len(ring),
            }
    return None


def normalize_event(row: dict[str, Any], result: AdapterResult) -> dict[str, Any]:
    geometries = row.get("geometry") or []
    latest = geometries[-1] if geometries else {}
    return {
        "id": row["id"],
        "title": row.get("title"),
        "description": row.get("description"),
        "categories": [{"id": c.get("id"), "title": c.get("title")} for c in row.get("categories", [])],
        "sources": [{"id": s.get("id"), "url": s.get("url")} for s in row.get("sources", [])],
        "link": row.get("link"),
        "closed": row.get("closed"),
        "first_observed": geometries[0].get("date") if geometries else None,
        "last_observed": latest.get("date"),
        "geometry_count": len(geometries),
        "latest_geometry": {
            "type": latest.get("type"),
            "date": latest.get("date"),
            "coordinates": latest.get("coordinates"),
            "magnitude_value": latest.get("magnitudeValue"),
            "magnitude_unit": latest.get("magnitudeUnit"),
        } if latest else None,
        "point": _point(latest) if latest else None,
        "state": state_code(row.get("title")) or state_code(row.get("description")),
        "provenance": result.provenance,
        "retrieved_at": result.retrieved_at,
        "source_url": row.get("link") or result.source_url,
    }


async def eonet_events(hub: IntegrationHub, limit: int = 60, category: str | None = None) -> AdapterResult:
    params: dict[str, Any] = {"status": "open", "limit": limit}
    if category:
        params["category"] = category
    result = await hub.fetch(
        "nasa_eonet", f"{EONET_BASE}/events", params=params,
        cache_key=f"events:{limit}:{category}", fresh_seconds=300, timeout=12,
        source_url=f"{EONET_BASE}/events?status=open",
    )
    if result.ok:
        result.data = [normalize_event(row, result) for row in (result.data or {}).get("events", [])]
    return result


async def eonet_event(hub: IntegrationHub, event_id: str) -> AdapterResult:
    if not re.fullmatch(r"[A-Za-z0-9_\-]{1,64}", event_id):
        return AdapterResult("nasa_eonet", "UNAVAILABLE", error="Invalid EONET event id")
    result = await hub.fetch(
        "nasa_eonet", f"{EONET_BASE}/events/{event_id}", cache_key=f"event:{event_id}",
        fresh_seconds=300, timeout=12, not_found_ok=True,
    )
    if result.ok:
        if not result.data:
            return AdapterResult("nasa_eonet", "UNAVAILABLE", error=f"EONET event {event_id} not found")
        result.data = normalize_event(result.data, result)
    return result


def normalize_alert(feature: dict[str, Any], result: AdapterResult) -> dict[str, Any]:
    props = feature.get("properties", {})
    return {
        "id": props.get("id") or feature.get("id"),
        "event": props.get("event"),
        "headline": props.get("headline"),
        "severity": props.get("severity"),
        "urgency": props.get("urgency"),
        "certainty": props.get("certainty"),
        "effective": props.get("effective"),
        "expires": props.get("expires"),
        "area": props.get("areaDesc"),
        "sender": props.get("senderName"),
        "source_url": props.get("@id") or feature.get("id"),
        "provenance": result.provenance,
        "retrieved_at": result.retrieved_at,
    }


async def nws_alerts(hub: IntegrationHub, *, lat: float | None = None, lon: float | None = None,
                     state: str | None = None) -> AdapterResult:
    if lat is not None and lon is not None:
        params = {"point": f"{lat:.4f},{lon:.4f}"}
        key = f"point:{lat:.2f},{lon:.2f}"
    elif state:
        params = {"area": state}
        key = f"area:{state}"
    else:
        return AdapterResult("nws", "UNAVAILABLE", error="NWS needs a US point or state")
    result = await hub.fetch(
        "nws", f"{NWS_BASE}/alerts/active", params=params, cache_key=key, fresh_seconds=180,
        headers={"Accept": "application/geo+json"}, timeout=12,
        source_url=f"{NWS_BASE}/alerts/active?{'&'.join(f'{k}={v}' for k, v in params.items())}",
    )
    if result.ok:
        result.data = [normalize_alert(feature, result) for feature in (result.data or {}).get("features", [])]
    return result


async def firms_detections(hub: IntegrationHub, map_key: str | None, *, lat: float, lon: float,
                           radius_deg: float = 0.5, days: int = 2,
                           sensor: str = "VIIRS_NOAA20_NRT") -> AdapterResult:
    bbox = f"{lon - radius_deg:.4f},{lat - radius_deg:.4f},{lon + radius_deg:.4f},{lat + radius_deg:.4f}"
    public_url = f"{FIRMS_BASE}/[MAP_KEY]/{sensor}/{bbox}/{days}"
    if not map_key:
        return hub.blocked("nasa_firms", "RELIEFMESH_NASA_FIRMS_MAP_KEY is not configured", public_url)
    result = await hub.fetch(
        "nasa_firms", f"{FIRMS_BASE}/{map_key}/{sensor}/{bbox}/{days}", cache_key=f"{sensor}:{bbox}:{days}",
        fresh_seconds=600, expect="text", timeout=20, source_url=public_url,
    )
    if result.ok:
        text = result.data or ""
        if text.lstrip().lower().startswith(("invalid", "error")):
            return AdapterResult("nasa_firms", "UNAVAILABLE", source_url=public_url, error=text.strip()[:200])
        rows = list(csv.DictReader(io.StringIO(text)))
        result.data = [
            {
                "latitude": float(row["latitude"]),
                "longitude": float(row["longitude"]),
                "acquired_at": f"{row.get('acq_date')}T{str(row.get('acq_time', '0000')).zfill(4)[:2]}:"
                               f"{str(row.get('acq_time', '0000')).zfill(4)[2:]}:00Z",
                "satellite": row.get("satellite"),
                "instrument": row.get("instrument"),
                "confidence": row.get("confidence"),
                "frp": float(row["frp"]) if row.get("frp") else None,
                "daynight": row.get("daynight"),
                "sensor": sensor,
            }
            for row in rows if row.get("latitude") and row.get("longitude")
        ]
        result.meta.update({"bbox": bbox, "days": days, "sensor": sensor})
    return result


async def fema_declarations(hub: IntegrationHub, state: str, top: int = 8) -> AdapterResult:
    if state not in STATE_CODES:
        return AdapterResult("openfema", "UNAVAILABLE", error=f"Unknown state code {state!r}")
    params = {"$filter": f"state eq '{state}'", "$orderby": "declarationDate desc", "$top": top}
    result = await hub.fetch(
        "openfema", FEMA_URL, params=params, cache_key=f"{state}:{top}", fresh_seconds=3600, timeout=15,
        source_url=f"{FEMA_URL}?$filter=state eq '{state}'",
    )
    if result.ok:
        result.data = [
            {
                "declaration_number": row.get("femaDeclarationString"),
                "disaster_number": row.get("disasterNumber"),
                "declaration_type": row.get("declarationType"),
                "declaration_date": row.get("declarationDate"),
                "incident_type": row.get("incidentType"),
                "title": row.get("declarationTitle"),
                "state": row.get("state"),
                "designated_area": row.get("designatedArea"),
                "incident_begin": row.get("incidentBeginDate"),
                "incident_end": row.get("incidentEndDate"),
                "source_url": f"https://www.fema.gov/disaster/{row.get('disasterNumber')}",
            }
            for row in (result.data or {}).get("DisasterDeclarationsSummaries", [])
        ]
    return result
