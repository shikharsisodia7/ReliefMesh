"""SAM.gov registration evidence under a personal key's tiny daily quota (10 requests/day without a SAM role).

The adapter must parse registrations, spend at most one request per name per day, never retry a 429 (the quota
is gone, retrying only burns more), and the public status page must not spend the quota on every visit.
"""

from __future__ import annotations

import httpx
import pytest

from app.integrations import entity
from app.integrations.http import IntegrationHub
from app.store import MemoryStore
from conftest import make_settings

ENTITY = {"totalRecords": 2, "entityData": [
    {"entityRegistration": {"ueiSAM": "AAA111", "legalBusinessName": "PACIFIC RELIEF SUPPLY CO",
                            "registrationStatus": "Active", "registrationExpirationDate": "2027-01-12",
                            "cageCode": "1ABC2"},
     "coreData": {"physicalAddress": {"city": "Oakland", "stateOrProvinceCode": "CA"}}},
    {"entityRegistration": {"ueiSAM": "BBB222", "legalBusinessName": "UNRELATED HOLDINGS LLC",
                            "registrationStatus": "Active"}, "coreData": {}},
]}


def hub_with(handler) -> tuple[IntegrationHub, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)
    return IntegrationHub(MemoryStore(), "ReliefMesh/test", transport=httpx.MockTransport(record)), seen


@pytest.mark.anyio
async def test_registration_is_parsed_and_cached_for_a_day_per_name() -> None:
    hub, seen = hub_with(lambda request: httpx.Response(200, json=ENTITY))
    first = await entity.sam_registration(hub, "SAM-test", "Pacific Relief Supply Co")
    assert first.ok and first.provenance == "LIVE"
    best = first.data["entities"][0]
    assert best["uei"] == "AAA111" and best["registration_status"] == "Active" and best["similarity"] == 1.0
    assert seen[0].url.params["legalBusinessName"] == "Pacific Relief Supply Co"
    again = await entity.sam_registration(hub, "SAM-test", "PACIFIC RELIEF SUPPLY CO.")  # same normalized name
    assert again.ok and again.provenance == "CACHED" and len(seen) == 1


@pytest.mark.anyio
async def test_quota_exhausted_is_not_retried_and_says_so() -> None:
    hub, seen = hub_with(lambda request: httpx.Response(429, json={"error": {"code": "OVER_RATE_LIMIT"}}))
    result = await entity.sam_registration(hub, "SAM-test", "Pacific Relief Supply Co")
    assert not result.ok and result.status == "UNAVAILABLE" and len(seen) == 1
    assert result.error == entity.SAM_QUOTA_MESSAGE


@pytest.mark.anyio
async def test_status_probe_spends_one_request_per_twelve_hours() -> None:
    from app.core import Services
    from app.emailing import EmailGateway
    from app.integrations.connections import TokenVault
    from app.routes.status import check_sam

    hub, seen = hub_with(lambda request: httpx.Response(200, json=ENTITY))
    settings = make_settings(sam_gov_api_key="SAM-test")
    services = Services(settings, hub.store, EmailGateway(settings, hub.store, TokenVault(settings), hub.client), hub)
    status, detail, _ = await check_sam(services)
    assert status == "ok" and "PACIFIC RELIEF SUPPLY CO" in detail and "UEI AAA111" in detail
    for _ in range(5):  # every status-page visit after the first reuses the probe
        status, detail, provenance = await check_sam(services)
        assert status == "ok" and provenance == "CACHED"
    assert len(seen) == 1

    quota_hub, _ = hub_with(lambda request: httpx.Response(429))
    quota_services = Services(settings, quota_hub.store, services.email, quota_hub)
    status, detail, _ = await check_sam(quota_services)
    assert status == "degraded" and detail == entity.SAM_QUOTA_MESSAGE

    unset = make_settings()
    assert (await check_sam(Services(unset, hub.store, services.email, hub)))[0] == "not_configured"
