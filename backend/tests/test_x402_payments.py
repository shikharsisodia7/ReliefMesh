"""x402 purchase guards: duplicate settlement, cooldown reuse, daily budget, receipt persistence.

The live HTTP 402 -> Solana devnet settlement is exercised against the real facilitator
(see docs/SPONSOR_ACCESS_STATUS.md); here the buyer is injected so the guards are deterministic.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import count

import pytest
from fastapi import HTTPException

from app.payments.x402_exchange import compile_dossier, dossier_hash_matches, purchase_supplier_dossier
from conftest import auth, register

_tx = count(1)


async def fake_buyer(services, name):
    dossier = await compile_dossier(services, name)
    return dossier, {"success": True, "transaction": f"devnet-tx-{next(_tx)}", "payer": "BuyerWallet111"}, 200


async def replay_buyer(services, name):
    dossier = await compile_dossier(services, name)
    return dossier, {"success": True, "transaction": "devnet-tx-replayed", "payer": "BuyerWallet111"}, 200


async def setup(app, client):
    services = app.state.services
    services.settings.x402_pay_to = "TreasuryWallet111"
    services.settings.x402_buyer_private_key = "configured"
    token = await register(client, f"buyer-{datetime.now().timestamp()}@example.com", "coordinator")
    org = (await client.post("/v1/organizations", json={"name": "Paid evidence"}, headers=auth(token))).json()
    mission = (await client.post("/v1/missions", headers=auth(token), json={
        "organization_id": org["id"], "name": "x402", "delivery_location": "Oakland, CA",
        "delivery_deadline": (datetime.now(UTC) + timedelta(days=3)).isoformat(), "budget": "5000.00",
        "requirements": [{"item": "blankets", "quantity": 100}]})).json()
    seeded = (await client.post(f"/v1/missions/{mission['id']}/demo/seed", headers=auth(token))).json()
    user = (await client.get("/v1/me", headers=auth(token))).json()
    return services, mission, seeded["suppliers"], user, token


@pytest.mark.anyio
async def test_receipt_persisted_and_cooldown_reuses_without_paying_again(app_and_client) -> None:
    app, client = app_and_client
    services, mission, suppliers, user, token = await setup(app, client)
    first = await purchase_supplier_dossier(services, mission, suppliers[1], user, buyer=fake_buyer)
    assert first["reused"] is False
    payment = first["payment"]
    assert payment["network_label"] == "solana-devnet" and payment["asset_symbol"] == "USDC"
    assert payment["amount_atomic"] == "10000" and payment["transaction"].startswith("devnet-tx-")
    assert dossier_hash_matches(first["evidence"]["raw_reference"]["dossier"])
    again = await purchase_supplier_dossier(services, mission, suppliers[1], user, buyer=fake_buyer)
    assert again["reused"] is True and again["payment"]["id"] == payment["id"]
    listed = (await client.get(f"/v1/missions/{mission['id']}/payments", headers=auth(token))).json()
    assert len(listed) == 1
    audit = (await client.get(f"/v1/missions/{mission['id']}/audit", headers=auth(token))).json()
    assert any(event["action"] == "payment.x402.settled" and event["metadata"]["transaction"] == payment["transaction"]
               for event in audit)


@pytest.mark.anyio
async def test_replayed_settlement_transaction_is_rejected(app_and_client) -> None:
    app, client = app_and_client
    services, mission, suppliers, user, _ = await setup(app, client)
    await purchase_supplier_dossier(services, mission, suppliers[0], user, buyer=replay_buyer)
    with pytest.raises(HTTPException) as error:
        await purchase_supplier_dossier(services, mission, suppliers[2], user, buyer=replay_buyer)
    assert error.value.status_code == 409 and "Duplicate" in error.value.detail


@pytest.mark.anyio
async def test_daily_data_budget_caps_machine_spend(app_and_client) -> None:
    app, client = app_and_client
    services, mission, suppliers, user, _ = await setup(app, client)
    services.settings.x402_daily_cap_usd = "0.02"
    await purchase_supplier_dossier(services, mission, suppliers[0], user, buyer=fake_buyer)
    await purchase_supplier_dossier(services, mission, suppliers[1], user, buyer=fake_buyer)
    with pytest.raises(HTTPException) as error:
        await purchase_supplier_dossier(services, mission, suppliers[2], user, buyer=fake_buyer)
    assert error.value.status_code == 409 and "budget" in error.value.detail


@pytest.mark.anyio
async def test_unconfigured_payments_are_blocked_external(app_and_client) -> None:
    app, client = app_and_client
    services, mission, suppliers, user, token = await setup(app, client)
    services.settings.x402_pay_to = None
    response = await client.post(f"/v1/missions/{mission['id']}/suppliers/{suppliers[0]['id']}/premium-dossier",
                                 headers=auth(token))
    assert response.status_code == 503 and "BLOCKED_EXTERNAL" in response.json()["detail"]


@pytest.mark.anyio
async def test_public_devnet_proof_is_throttled_and_rejects_replays(app_and_client) -> None:
    from app.payments import x402_exchange
    from app.payments.x402_exchange import run_proof

    app, client = app_and_client
    services = app.state.services
    services.settings.x402_pay_to, services.settings.x402_buyer_private_key = "TreasuryWallet111", "configured"
    assert (await client.get("/v1/sandbox/x402-proof")).json()["proof"] is None  # nothing faked before a real run
    anonymous = await client.post("/v1/sandbox/x402-proof")
    assert anonymous.status_code == 401  # spending, even devnet test funds, needs a signed-in user
    actor = {"id": "user-1"}
    first = await run_proof(services, actor, buyer=fake_buyer)
    assert first["reused"] is False and first["provenance"] == "SANDBOX" and "DEVNET TEST PAYMENT" in first["notice"]
    assert first["proof"]["explorer_url"].endswith("?cluster=devnet")
    again = await run_proof(services, actor, buyer=fake_buyer)  # inside the cooldown: no second payment
    assert again["reused"] is True and again["proof"]["transaction"] == first["proof"]["transaction"]
    shown = (await client.get("/v1/sandbox/x402-proof")).json()
    assert shown["proof"]["transaction"] == first["proof"]["transaction"]

    rows = await services.store.find("sandbox_proofs", kind="x402")
    for row in rows:  # age the proof past the cooldown, then a replayed settlement must be rejected
        row["created_at"] = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
        await services.store.replace("sandbox_proofs", row["id"], row)

    async def same_tx(services_, name):
        return {"dossier_sha256": "x"}, {"success": True, "transaction": first["proof"]["transaction"]}, 200
    with pytest.raises(HTTPException) as replay:
        await run_proof(services, actor, buyer=same_tx)
    assert replay.value.status_code == 409

    services.settings.x402_buyer_private_key = None
    with pytest.raises(HTTPException) as blocked:
        await run_proof(services, actor, buyer=fake_buyer)
    assert blocked.value.status_code == 503
    assert x402_exchange.PROOF_DAILY_LIMIT >= 1
    events = [e for e in await services.store.find("audit_events") if e["action"] == "sandbox.x402_proof.settled"]
    assert len(events) == 1 and events[0]["metadata"]["transaction"] == first["proof"]["transaction"]
