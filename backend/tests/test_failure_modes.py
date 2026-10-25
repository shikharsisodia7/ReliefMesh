"""Every external dependency failing: procurement-sensitive checks fail safe, notifications never block procurement,
and nothing fabricated is shown in place of a missing answer."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.main import create_app
from conftest import FakeUpstream, auth, make_settings, register, settle_jobs, wait_for
from test_po_disruption import quote


async def _app(upstream: FakeUpstream, **overrides):
    app = create_app(make_settings(**overrides), http_transport=httpx.MockTransport(upstream))
    return app


async def _mission(client: httpx.AsyncClient, coordinator: str, **extra) -> dict:
    org = (await client.post("/v1/organizations", json={"name": "County OES"}, headers=auth(coordinator))).json()
    return (await client.post("/v1/missions", headers=auth(coordinator), json={
        "organization_id": org["id"], "name": "Shelter", "delivery_location": "Oakland, CA",
        "delivery_deadline": (datetime.now(UTC) + timedelta(days=4)).isoformat(), "budget": "1000.00",
        "requirements": [{"item": "blankets", "quantity": 100}], **extra})).json()


@pytest.mark.anyio
async def test_emergency_sources_down_are_reported_unavailable_never_fabricated() -> None:
    upstream = FakeUpstream()
    app = await _app(upstream)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            coordinator = await register(client, "lead@county.example.org", "coordinator")
            mission = await _mission(client, coordinator, emergency_event_id="EONET_9999")
            upstream.down |= {"eonet.gsfc.nasa.gov", "api.weather.gov", "www.fema.gov", "firms.modaps.eosdis.nasa.gov"}
            app.state.services.hub._breakers.clear()
            context = (await client.get(f"/v1/missions/{mission['id']}/context", headers=auth(coordinator))).json()
            assert context["nws"]["status"] == "UNAVAILABLE" and not context["nws"].get("data")
            assert context["fema"]["status"] == "UNAVAILABLE" and not context["fema"].get("data")
            # The event falls back to real data captured earlier (cache or creation snapshot), labeled CACHED.
            assert context["event"]["provenance"] == "CACHED", context["event"]
            # The mission and procurement still work while every emergency feed is down.
            assert (await client.get(f"/v1/missions/{mission['id']}", headers=auth(coordinator))).status_code == 200


@pytest.mark.anyio
async def test_email_provider_down_records_failure_and_procurement_continues() -> None:
    upstream = FakeUpstream(down={"api.resend.com"})
    app = await _app(upstream, app_env="development", demo_mode=False, expose_invitation_links=False,
                     email_mode="live", resend_api_key="re_test_unreachable_provider")
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            coordinator = await register(client, "lead@county.example.org", "coordinator")
            mission = await _mission(client, coordinator)
            invite = (await client.post(f"/v1/missions/{mission['id']}/invitations", headers=auth(coordinator),
                                        json={"supplier_email": "sales@vendor.example.org"})).json()
            assert invite["delivery_status"] == "failed" and invite["delivery"]["sent_at"] is None
            assert invite["link_reason"] == "email_not_sent" and invite["token"]  # coordinator can relay the link
            supplier = await register(client, "sales@vendor.example.org", "supplier")
            assert (await client.post(f"/v1/supplier-invitations/{invite['token']}/accept",
                                      headers=auth(supplier))).status_code == 200


@pytest.mark.anyio
async def test_gemini_down_is_explicit_and_the_form_still_works() -> None:
    upstream = FakeUpstream(down={"generativelanguage.googleapis.com"})
    app = await _app(upstream, gemini_api_key="test-gemini-key")
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            coordinator = await register(client, "lead@county.example.org", "coordinator")
            mission = await _mission(client, coordinator)
            token = (await client.post(f"/v1/missions/{mission['id']}/invitations", headers=auth(coordinator),
                                       json={"supplier_email": "s@vendor.example.org"})).json()["token"]
            supplier = await register(client, "s@vendor.example.org", "supplier")
            await client.post(f"/v1/supplier-invitations/{token}/accept", headers=auth(supplier))
            draft = await client.post(f"/v1/supplier-invitations/{token}/quote-draft", headers=auth(supplier),
                                      json={"text": "100 blankets at $10 each, delivery tomorrow, freight $20"})
            assert draft.status_code == 502 and draft.json()["detail"]["code"] == "GEMINI_UNAVAILABLE"


@pytest.mark.anyio
async def test_compliance_sources_down_never_pass_a_supplier(client: httpx.AsyncClient, upstream) -> None:
    upstream.down |= {"sanctionslistservice.ofac.treas.gov", "api.fda.gov", "api.usaspending.gov"}
    coordinator = await register(client, "lead@county.example.org", "coordinator")
    mission = await _mission(client, coordinator)
    await quote(client, coordinator, mission["id"], "a@alpha.example.org", "Alpha Textiles", 100, "1.00")
    await settle_jobs(client, coordinator, mission["id"])
    rows = (await client.get(f"/v1/missions/{mission['id']}/suppliers", headers=auth(coordinator))).json()
    assert rows and all(row["policy"]["status"] in {"NEEDS_REVIEW", "BLOCK"} for row in rows)
    plan = (await client.get(f"/v1/plans/{(await client.post(f'/v1/missions/{mission['id']}/optimize', headers=auth(coordinator))).json()['plan_id']}",
                             headers=auth(coordinator))).json()
    assert plan["status"] == "infeasible" and plan["allocations"] == []  # no money moves on missing evidence


@pytest.mark.anyio
async def test_crs_down_holds_sandbox_suppliers_for_review() -> None:
    upstream = FakeUpstream(down={"api-sandbox.stitchcredit.com"})
    app = await _app(upstream, crs_username="sandbox-user", crs_password="sandbox-pass")
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            coordinator = await register(client, "lead@county.example.org", "coordinator")
            org = (await client.post("/v1/organizations", json={"name": "Demo", "demo": True},
                                     headers=auth(coordinator))).json()
            mission = (await client.post("/v1/missions", headers=auth(coordinator), json={
                "organization_id": org["id"], "name": "Shelter", "delivery_location": "Oakland, CA",
                "delivery_deadline": (datetime.now(UTC) + timedelta(days=4)).isoformat(), "budget": "5000.00",
                "requirements": [{"item": "blankets", "quantity": 100}]})).json()
            await client.post(f"/v1/missions/{mission['id']}/demo/seed", headers=auth(coordinator))
            await settle_jobs(client, coordinator, mission["id"])
            rows = (await client.get(f"/v1/missions/{mission['id']}/suppliers", headers=auth(coordinator))).json()
            crs = {row["supplier"]["legal_name"]: (row["latest_evidence"].get("CRS_VERIFICATION") or {}).get("status")
                   for row in rows}
            assert crs and all(status == "UNAVAILABLE" for status in crs.values()), crs
            assert all(row["policy"]["status"] in {"NEEDS_REVIEW", "BLOCK"} for row in rows)


@pytest.mark.anyio
async def test_apify_down_fails_the_discovery_job_without_inventing_leads() -> None:
    upstream = FakeUpstream(down={"api.apify.com"})
    app = await _app(upstream, apify_api_token="apify_api_test_token")
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            coordinator = await register(client, "lead@county.example.org", "coordinator")
            mission = await _mission(client, coordinator)
            await client.post(f"/v1/missions/{mission['id']}/discovery", headers=auth(coordinator),
                              json={"query": "blankets", "max_results": 3})
            async def finished():
                rows = (await client.get(f"/v1/missions/{mission['id']}/jobs", headers=auth(coordinator))).json()
                return rows if rows and all(job["status"] in {"succeeded", "failed"} for job in rows) else None
            jobs = await wait_for(finished, attempts=150, delay=0.2)  # 3 attempts with 2 s / 4 s backoff
            discovery = [job for job in jobs if job["type"] == "supplier_discovery"]
            assert discovery and discovery[0]["status"] == "failed"
            assert (await client.get(f"/v1/missions/{mission['id']}/leads", headers=auth(coordinator))).json() == []


@pytest.mark.anyio
async def test_solana_rpc_and_mongo_down_render_as_errors_on_the_status_page() -> None:
    from app.core import Services
    from app.emailing import EmailGateway
    from app.integrations.connections import TokenVault
    from app.integrations.http import IntegrationHub
    from app.routes.status import check_mongo, check_x402, run_check
    from app.store import MemoryStore

    upstream = FakeUpstream(down={"api.devnet.solana.com", "x402.org", "www.x402.org"})
    settings = make_settings(x402_pay_to="DxajVzXWtestTreasury1111111111111111111111111")
    store = MemoryStore()
    hub = IntegrationHub(store, "ReliefMesh/test", transport=httpx.MockTransport(upstream))
    services = Services(settings, store, EmailGateway(settings, store, TokenVault(settings), hub.client), hub)
    status, _detail, _ = await check_x402(services)
    assert status != "ok"

    def facilitator_up_rpc_down(request: httpx.Request) -> httpx.Response:
        if request.url.host == "x402.org":
            return httpx.Response(200, json={"kinds": [{"scheme": "exact",
                                                        "network": "solana:EtWTRABZaYq6iMfeYKouRu166VU2xqa1"}]})
        raise httpx.ConnectTimeout("simulated Solana RPC outage", request=request)
    rpc_hub = IntegrationHub(store, "ReliefMesh/test", transport=httpx.MockTransport(facilitator_up_rpc_down))
    rpc_down = Services(settings, store, services.email, rpc_hub)
    _status, detail, _ = await check_x402(rpc_down)
    assert "balance unavailable" in detail and "holds 0" not in detail, detail

    class DeadMongo(MemoryStore):
        async def ping(self):
            raise ConnectionError("simulated MongoDB outage")
    mongo_settings = make_settings(storage_mode="memory")
    object.__setattr__(mongo_settings, "storage_mode", "mongo")
    dead = Services(mongo_settings, DeadMongo(), services.email, hub)
    row = await run_check(dead, "mongodb", "MongoDB Atlas", "core", check_mongo)
    assert row["status"] == "error" and "outage" in row["detail"]
