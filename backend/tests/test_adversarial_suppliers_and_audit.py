"""Suppliers on the same mission attacking each other, and every way to tamper with the audit chain."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from conftest import auth, register, settle_jobs
from test_po_disruption import quote


@pytest.mark.anyio
async def test_a_supplier_cannot_touch_a_competitors_quote_order_or_invitation(client: httpx.AsyncClient) -> None:
    buyer = await register(client, "buyer@county.example.org", "coordinator")
    org = (await client.post("/v1/organizations", json={"name": "County OES"}, headers=auth(buyer))).json()
    invite = (await client.post(f"/v1/organizations/{org['id']}/members", headers=auth(buyer),
                                json={"email": "approver@county.example.org", "role": "approver"})).json()
    approver = await register(client, "approver@county.example.org", "coordinator")
    await client.post(f"/v1/org-invites/{invite['invite_url'].rsplit('/', 1)[1]}/accept", headers=auth(approver))
    mission = (await client.post("/v1/missions", headers=auth(buyer), json={
        "organization_id": org["id"], "name": "Shelter", "delivery_location": "Oakland, CA",
        "delivery_deadline": (datetime.now(UTC) + timedelta(days=4)).isoformat(), "budget": "1000.00",
        "requirements": [{"item": "blankets", "quantity": 100}]})).json()
    mid = mission["id"]
    alpha = await quote(client, buyer, mid, "a@alpha-textiles.example.org", "Alpha Textiles", 60, "1.00")
    beta = await quote(client, buyer, mid, "b@beta-supply.example.org", "Beta Supply", 60, "2.00")
    await settle_jobs(client, buyer, mid)
    plan_id = (await client.post(f"/v1/missions/{mid}/optimize", headers=auth(buyer))).json()["plan_id"]
    assert (await client.post(f"/v1/plans/{plan_id}/approve", headers=auth(approver))).status_code == 201
    orders = (await client.post(f"/v1/plans/{plan_id}/purchase-orders",
                                headers={**auth(buyer), "Idempotency-Key": "po"})).json()
    for order in orders:
        await client.post(f"/v1/purchase-orders/{order['id']}/send", json={"confirm": True}, headers=auth(buyer))
    beta_quote = (await client.get("/v1/supplier/quotes", headers=auth(beta))).json()[0]
    beta_order = next(o for o in orders if o["supplier_email"].startswith("b@"))
    beta_rfq = (await client.post(f"/v1/missions/{mid}/invitations", headers=auth(buyer),
                                  json={"supplier_email": "b@beta-supply.example.org"})).json()["token"]
    soon = (datetime.now(UTC) + timedelta(days=1)).isoformat()

    attacks = [
        ("GET", f"/v1/quotes/{beta_quote['id']}", None),
        ("PUT", f"/v1/quotes/{beta_quote['id']}", {"expires_at": soon, "shipping_cost": "0", "lines": [
            {"requirement_id": mission["requirements"][0]["id"], "item": "blankets", "unit_price": "99.00",
             "available_quantity": 1, "delivery_date": soon}]}),
        ("POST", f"/v1/quotes/{beta_quote['id']}/withdraw", None),
        ("POST", f"/v1/purchase-orders/{beta_order['id']}/supplier-response", {"accepted": False, "reason": "x"}),
        ("POST", f"/v1/purchase-orders/{beta_order['id']}/fulfillment", {"status": "cancelled", "note": "x"}),
        ("GET", f"/v1/purchase-orders/{beta_order['id']}/pdf", None),
        ("POST", f"/v1/supplier-invitations/{beta_rfq}/accept", None),
        ("POST", f"/v1/supplier-invitations/{beta_rfq}/quote-draft", {"text": "60 blankets at $2.00 each, tomorrow"}),
        ("GET", f"/v1/missions/{mid}/quotes", None),
        ("GET", f"/v1/missions/{mid}/plans", None),
        ("POST", f"/v1/plans/{plan_id}/approve", None),
    ]
    for method, url, body in attacks:
        response = await client.request(method, url, json=body, headers=auth(alpha))
        assert response.status_code in {403, 404, 409}, (method, url, response.status_code, response.text[:120])
    # The independent approver reviews the quotes it authorizes spend against (read-only).
    approver_view = await client.get(f"/v1/missions/{mid}/quotes", headers=auth(approver))
    assert approver_view.status_code == 200 and len(approver_view.json()) == 2
    alpha_orders = (await client.get("/v1/purchase-orders", headers=auth(alpha))).json()
    assert {o["supplier_email"] for o in alpha_orders} == {"a@alpha-textiles.example.org"}
    after = (await client.get(f"/v1/quotes/{beta_quote['id']}", headers=auth(beta))).json()
    assert after["status"] == "submitted" and after["version"] == beta_quote["version"]
    assert (await client.get(f"/v1/plans/{plan_id}", headers=auth(buyer))).json()["status"] == "approved"


async def _chain(app_and_client):
    app, client = app_and_client
    token = await register(client, "auditor@county.example.org", "coordinator")
    org = (await client.post("/v1/organizations", json={"name": "Audit Org"}, headers=auth(token))).json()
    mission = (await client.post("/v1/missions", headers=auth(token), json={
        "organization_id": org["id"], "name": "Audit", "delivery_location": "Oakland, CA",
        "delivery_deadline": (datetime.now(UTC) + timedelta(days=4)).isoformat(), "budget": "100.00",
        "requirements": [{"item": "water", "quantity": 1}]})).json()
    for email in ("one@vendor.example.org", "two@vendor.example.org", "three@vendor.example.org"):
        await client.post(f"/v1/missions/{mission['id']}/invitations", headers=auth(token), json={"supplier_email": email})
    store = app.state.services.store
    events = sorted(await store.find("audit_events", chain_key=f"mission:{mission['id']}"), key=lambda e: e["sequence"])
    assert len(events) >= 4

    async def verify():
        return (await client.get(f"/v1/missions/{mission['id']}/audit/verify", headers=auth(token))).json()
    assert (await verify())["valid"] is True
    return store, events, verify


@pytest.mark.anyio
@pytest.mark.parametrize("tamper", ["payload", "removed_middle", "removed_last", "reordered", "previous_hash",
                                    "event_hash", "removed_last_and_head", "removed_last_head_rewritten"])
async def test_audit_chain_detects_every_tampering(app_and_client, tamper: str) -> None:
    store, events, verify = await _chain(app_and_client)
    target = dict(events[1])
    if tamper == "payload":
        target["metadata"] = {"delivery_status": "forged"}
        await store.replace("audit_events", target["id"], target)
    elif tamper == "removed_middle":  # attacker with database access deletes a record
        store._documents["audit_events"].pop(events[1]["id"])
    elif tamper == "removed_last":
        store._documents["audit_events"].pop(events[-1]["id"])
    elif tamper == "reordered":
        first, second = dict(events[1]), dict(events[2])
        first["sequence"], second["sequence"] = second["sequence"], first["sequence"]
        await store.replace("audit_events", first["id"], first)
        await store.replace("audit_events", second["id"], second)
    elif tamper == "previous_hash":
        target["previous_hash"] = "0" * 64
        await store.replace("audit_events", target["id"], target)
    elif tamper == "event_hash":
        target["event_hash"] = "f" * 64
        await store.replace("audit_events", target["id"], target)
    elif tamper == "removed_last_and_head":
        store._documents["audit_events"].pop(events[-1]["id"])
        store._documents["audit_chain_heads"].pop(events[-1]["chain_key"])
    elif tamper == "removed_last_head_rewritten":  # attacker hides the deletion but lacks the server key
        store._documents["audit_events"].pop(events[-1]["id"])
        head = store._documents["audit_chain_heads"][events[-1]["chain_key"]]
        head.update(sequence=events[-2]["sequence"], event_hash=events[-2]["event_hash"])
    result = await verify()
    assert result["valid"] is False and result["reason"], (tamper, result)
