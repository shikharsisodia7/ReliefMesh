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
