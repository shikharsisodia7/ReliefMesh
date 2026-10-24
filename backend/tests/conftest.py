from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from app.main import create_app
from app.settings import Settings

# Excerpts in the exact format of the Treasury SDN.CSV / ALT.CSV exports.
SDN_CSV = (
    '306,"BANCO NACIONAL DE CUBA",-0- ,"CUBA",-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,"a.k.a. \'BNC\'."\n'
    '7269,"GLOBAL RELIEF FOUNDATION, INC.",-0- ,"SDGT",-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0- \n'
    '17229,"PIONEER LOGISTICS",-0- ,"SDGT] [IFSR",-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0- \n'
)
ALT_CSV = '306,220,"aka","NATIONAL BANK OF CUBA",-0- \n'

EONET_EVENT = {
    "id": "EONET_9999",
    "title": "Wildfire TEST CANYON, Alameda, California",
    "description": "Fixture event",
    "link": "https://eonet.gsfc.nasa.gov/api/v3/events/EONET_9999",
    "closed": None,
    "categories": [{"id": "wildfires", "title": "Wildfires"}],
    "sources": [{"id": "IRWIN", "url": "https://irwin.doi.gov/observer/incidents/fixture"}],
    "geometry": [{"magnitudeValue": 1200.0, "magnitudeUnit": "acres", "date": "2026-10-23T10:00:00Z",
                  "type": "Point", "coordinates": [-122.27, 37.80]}],
}


@dataclass
class FakeUpstream:
    """Deterministic stand-in for public APIs. Unknown hosts fail like a dead network."""

    ofac_down: bool = False
    fda_firms: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.calls.append(url)
        host, path = request.url.host, request.url.path
        if host == "sanctionslistservice.ofac.treas.gov":
            if self.ofac_down:
                raise httpx.ConnectTimeout("simulated OFAC timeout", request=request)
            return httpx.Response(200, text=SDN_CSV if path.endswith("SDN.CSV") else ALT_CSV)
        if host == "api.fda.gov":
            search = request.url.params.get("search", "")
            for firm, rows in self.fda_firms.items():
                if firm.lower() in search.lower():
                    return httpx.Response(200, json={"meta": {"results": {"total": len(rows)}}, "results": rows})
            return httpx.Response(404, json={"error": {"code": "NOT_FOUND", "message": "No matches found!"}})
        if host == "api.usaspending.gov":
            return httpx.Response(200, json={"results": [], "page_metadata": {"hasNext": False}})
        if host == "eonet.gsfc.nasa.gov":
            if path.endswith("/events"):
                return httpx.Response(200, json={"events": [EONET_EVENT]})
            if path.endswith("/EONET_9999"):
                return httpx.Response(200, json=EONET_EVENT)
            return httpx.Response(404, json={"error": "not found"})
        if host == "api.weather.gov":
            return httpx.Response(200, json={"type": "FeatureCollection", "features": []})
        if host == "www.fema.gov":
            return httpx.Response(200, json={"DisasterDeclarationsSummaries": []})
        raise httpx.ConnectError(f"no network in tests: {url}", request=request)


def make_settings(**overrides: Any) -> Settings:
    values = dict(app_env="test", storage_mode="memory", jwt_secret="test-secret-that-is-long-enough-to-be-safe",
                  expose_invitation_links=True, frontend_origin="http://localhost:3000")
    values.update(overrides)
    # Never read the developer's local .env (real keys) inside tests.
    return Settings(_env_file=None, **values)


@pytest.fixture
def upstream() -> FakeUpstream:
    return FakeUpstream()


@pytest.fixture
async def app_and_client(upstream: FakeUpstream):
    app = create_app(make_settings(), http_transport=httpx.MockTransport(upstream))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as test_client:
            yield app, test_client


@pytest.fixture
async def client(app_and_client) -> httpx.AsyncClient:
    return app_and_client[1]


async def register(client: httpx.AsyncClient, email: str, role: str) -> str:
    response = await client.post(
        "/v1/auth/register", json={"email": email, "password": "correct horse battery staple", "role": role}
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def wait_for(predicate, attempts: int = 200, delay: float = 0.02):
    for _ in range(attempts):
        value = await predicate()
        if value:
            return value
        await asyncio.sleep(delay)
    raise AssertionError("condition not reached")


async def settle_jobs(client: httpx.AsyncClient, token: str, mission_id: str) -> list[dict[str, Any]]:
    async def done():
        jobs = (await client.get(f"/v1/missions/{mission_id}/jobs", headers=auth(token))).json()
        return {"jobs": jobs} if all(job["status"] in {"succeeded", "failed"} for job in jobs) else None
    return (await wait_for(done))["jobs"]


def dumps(value: Any) -> str:
    return json.dumps(value, indent=1, default=str)
