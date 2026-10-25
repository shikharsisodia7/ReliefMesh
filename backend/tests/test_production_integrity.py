"""Production shows real data only: no demo tooling, no synthetic suppliers, no pretended email delivery."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.main import create_app
from app.settings import Settings
from conftest import FakeUpstream, auth, make_settings, register


def test_production_refuses_to_start_with_demo_mode() -> None:
    base = dict(app_env="production", storage_mode="mongo", mongodb_uri="mongodb://db.example:27017",
                jwt_secret="production-secret-that-is-long-enough-123", _env_file=None)
    Settings(**base).validate_runtime()  # the default is safe
    assert Settings(**base).demo_enabled is False
    with pytest.raises(RuntimeError, match="DEMO_MODE"):
        Settings(**base, demo_mode=True).validate_runtime()
    with pytest.raises(RuntimeError, match="EXPOSE_INVITATION_LINKS"):
        Settings(**base, expose_invitation_links=True).validate_runtime()


@pytest.fixture
async def real_client():
    """A non-demo deployment with the real email gateway and no email credential."""
    settings = make_settings(app_env="development", demo_mode=False, expose_invitation_links=False)
    app = create_app(settings, http_transport=httpx.MockTransport(FakeUpstream()))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            yield client


@pytest.mark.anyio
async def test_without_demo_mode_there_is_no_demo_tooling_and_missions_start_empty(real_client) -> None:
    client = real_client
    config = (await client.get("/v1/config")).json()
    assert config["demo_mode"] is False and config["email"] == "not_configured"
    lead = await register(client, "lead@county.example.org", "coordinator")
    demo_org = await client.post("/v1/organizations", json={"name": "Fake Relief", "demo": True}, headers=auth(lead))
    assert demo_org.status_code == 422 and demo_org.json()["detail"]["code"] == "DEMO_MODE_DISABLED"
    org = (await client.post("/v1/organizations", json={"name": "County OES"}, headers=auth(lead))).json()
    mission = (await client.post("/v1/missions", headers=auth(lead), json={
        "organization_id": org["id"], "name": "Shelter blankets", "delivery_location": "Oakland, CA",
        "delivery_deadline": (datetime.now(UTC) + timedelta(days=5)).isoformat(), "budget": "5000.00",
        "requirements": [{"item": "blankets", "quantity": 100}]})).json()

    # Demo endpoints do not exist outside a demo deployment.
    assert (await client.post(f"/v1/missions/{mission['id']}/demo/seed", headers=auth(lead))).status_code == 404
    simulated = await client.post(f"/v1/missions/{mission['id']}/disruptions", headers=auth(lead),
                                  json={"kind": "withdraw", "supplier_id": "anything"})
    assert simulated.status_code == 404

    # A new mission has no suppliers, quotes, plans, or disruptions until real suppliers respond.
    for path in ("suppliers", "quotes", "plans", "disruptions"):
        rows = await client.get(f"/v1/missions/{mission['id']}/{path}", headers=auth(lead))
        assert rows.status_code == 200 and rows.json() == [], path

    # No email credential: the RFQ is recorded as NOT sent, and the coordinator gets the link to relay.
    invite = await client.post(f"/v1/missions/{mission['id']}/invitations", headers=auth(lead),
                               json={"supplier_email": "sales@real-vendor.example.org"})
    body = invite.json()
    assert body["delivery_status"] == "not_configured"
    assert body["delivery"]["sent_at"] is None and "not configured" in body["delivery"]["error"]
    assert body["link_reason"] == "email_not_sent" and body["invitation_url"].endswith(body["token"])


@pytest.mark.anyio
async def test_crs_sandbox_proof_uses_test_identities_and_is_cached() -> None:
    upstream = FakeUpstream()
    app = create_app(make_settings(crs_username="sandbox-user", crs_password="sandbox-pass"),
                     http_transport=httpx.MockTransport(upstream))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            proof = (await client.get("/v1/sandbox/crs-proof")).json()
            assert proof["provenance"] == "SANDBOX" and "not real-world" in proof["notice"]
            outcomes = {row["persona_id"]: row["outcome"] for row in proof["results"]}
            assert outcomes == {"P01": "verified", "P12": "flagged"}
            calls = len([url for url in upstream.calls if "identity-manager-verification" in url])
            await client.get("/v1/sandbox/crs-proof")
            assert len([url for url in upstream.calls if "identity-manager-verification" in url]) == calls  # cached


@pytest.mark.anyio
async def test_public_status_refresh_cannot_amplify_upstream_calls(client: httpx.AsyncClient, upstream) -> None:
    await client.get("/v1/integrations/status")
    before = len(upstream.calls)
    for _ in range(5):
        assert (await client.get("/v1/integrations/status?refresh=true")).status_code == 200
    assert len(upstream.calls) == before  # forced refreshes inside the floor are served from cache


@pytest.mark.anyio
@pytest.mark.parametrize(("status_code", "body", "expected"), [
    (401, {"name": "restricted_api_key", "message": "This API key is restricted to only send emails"}, "ok"),
    (200, {"data": []}, "ok"),
    (400, {"name": "validation_error", "message": "API key is invalid"}, "error"),
    (422, {"name": "missing_required_field"}, "error"),
])
async def test_resend_key_check_is_read_only_and_fails_closed(status_code, body, expected) -> None:
    from app.core import Services
    from app.emailing import EmailGateway
    from app.integrations.connections import TokenVault
    from app.integrations.http import IntegrationHub
    from app.routes.status import check_resend
    from app.store import MemoryStore

    seen = []

    def resend(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        return httpx.Response(status_code, json=body)

    settings = make_settings(app_env="development", demo_mode=False, expose_invitation_links=False,
                             resend_api_key="re_test_key_for_status_check")
    hub = IntegrationHub(MemoryStore(), "ReliefMesh/test", transport=httpx.MockTransport(resend))
    store = MemoryStore()
    gateway = EmailGateway(settings, store, TokenVault(settings), hub.client)
    status, _detail, _ = await check_resend(Services(settings, store, gateway, hub))
    assert status == expected and seen == [("GET", "/domains")]  # never POSTs (never sends) to validate
