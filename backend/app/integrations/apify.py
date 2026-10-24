"""Apify supplier discovery.

Discovered businesses are LEADS: public listing data (name, website, phone, address).
They carry no inventory, price, delivery promise, or willingness to sell. Binding
terms only ever arrive through ReliefMesh's authenticated RFQ/quote workflow.
"""

from __future__ import annotations

from typing import Any

from .http import AdapterResult, IntegrationHub

APIFY_BASE = "https://api.apify.com/v2"


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def account(hub: IntegrationHub, token: str | None) -> AdapterResult:
    if not token:
        return hub.blocked("apify", "RELIEFMESH_APIFY_API_TOKEN is not configured", f"{APIFY_BASE}/users/me")
    result = await hub.fetch("apify", f"{APIFY_BASE}/users/me", headers=_headers(token), timeout=10, retries=1)
    if result.ok:
        data = (result.data or {}).get("data", {})
        result.data = {"username": data.get("username"), "plan": (data.get("plan") or {}).get("id")}
    return result


async def start_discovery(hub: IntegrationHub, token: str | None, actor: str, *, query: str,
                          location: str | None, max_places: int) -> AdapterResult:
    url = f"{APIFY_BASE}/acts/{actor}/runs"
    if not token:
        return hub.blocked("apify", "RELIEFMESH_APIFY_API_TOKEN is not configured", url)
    actor_input: dict[str, Any] = {
        "searchStringsArray": [query],
        "maxCrawledPlacesPerSearch": max_places,
        "language": "en",
        "skipClosedPlaces": True,
        "scrapePlaceDetailPage": False,
    }
    if location:
        actor_input["locationQuery"] = location
    result = await hub.fetch(
        "apify", url, method="POST", json_body=actor_input, headers=_headers(token), timeout=30, retries=1,
        params={"waitForFinish": 0}, source_url=f"https://console.apify.com/actors/{actor}",
    )
    if result.ok:
        run = (result.data or {}).get("data", {})
        result.data = {"run_id": run.get("id"), "dataset_id": run.get("defaultDatasetId"),
                       "status": run.get("status"), "actor": actor, "input": actor_input}
    return result


async def wait_for_run(hub: IntegrationHub, token: str, run_id: str, wait_seconds: int = 60) -> AdapterResult:
    result = await hub.fetch(
        "apify", f"{APIFY_BASE}/actor-runs/{run_id}", params={"waitForFinish": wait_seconds},
        headers=_headers(token), timeout=wait_seconds + 15, retries=1,
    )
    if result.ok:
        run = (result.data or {}).get("data", {})
        result.data = {"run_id": run.get("id"), "dataset_id": run.get("defaultDatasetId"),
                       "status": run.get("status"), "usage_usd": run.get("usageTotalUsd")}
    return result


async def dataset_leads(hub: IntegrationHub, token: str, dataset_id: str, limit: int = 25) -> AdapterResult:
    result = await hub.fetch(
        "apify", f"{APIFY_BASE}/datasets/{dataset_id}/items", params={"clean": "true", "limit": limit},
        headers=_headers(token), timeout=30, retries=1,
        source_url=f"https://console.apify.com/storage/datasets/{dataset_id}",
    )
    if result.ok:
        leads = []
        for row in result.data or []:
            if not row.get("title"):
                continue
            location = row.get("location") or {}
            leads.append({
                "name": row.get("title"),
                "website": row.get("website"),
                "phone": row.get("phone"),
                "address": row.get("address"),
                "city": row.get("city"),
                "state": row.get("state"),
                "country_code": row.get("countryCode"),
                "category": row.get("categoryName"),
                "rating": row.get("totalScore"),
                "reviews": row.get("reviewsCount"),
                "place_id": row.get("placeId"),
                "coordinates": {"lat": location.get("lat"), "lon": location.get("lng")} if location else None,
                "source_url": row.get("url"),
            })
        result.data = leads
    return result
