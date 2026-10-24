"""A supplier declining its purchase order is a real disruption; replans keep units already on active POs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from conftest import auth, register, settle_jobs, wait_for


async def quote(client: httpx.AsyncClient, coordinator: str, mission_id: str, email: str, name: str,
                quantity: int, price: str) -> str:
    supplier = await register(client, email, "supplier")
    token = (await client.post(f"/v1/missions/{mission_id}/invitations", headers=auth(coordinator),
                               json={"supplier_email": email})).json()["token"]
    await client.post(f"/v1/supplier-invitations/{token}/accept", headers=auth(supplier))
    submitted = await client.post("/v1/quotes", headers=auth(supplier), json={
        "invitation_token": token, "expires_at": (datetime.now(UTC) + timedelta(days=3)).isoformat(),
        "shipping_cost": "0", "supplier_profile": {"legal_name": name},
        "lines": [{"item": "blankets", "unit_price": price, "available_quantity": quantity,
                   "delivery_date": (datetime.now(UTC) + timedelta(days=1)).isoformat()}]})
    assert submitted.status_code == 201, submitted.text
    return supplier


@pytest.mark.anyio
async def test_declined_po_replans_only_the_uncommitted_remainder(client: httpx.AsyncClient) -> None:
    coordinator = await register(client, "buyer@county.example.org", "coordinator")
    org = (await client.post("/v1/organizations", json={"name": "County OES"}, headers=auth(coordinator))).json()
    invite = (await client.post(f"/v1/organizations/{org['id']}/members", headers=auth(coordinator),
                                json={"email": "approver@county.example.org", "role": "approver"})).json()
    approver = await register(client, "approver@county.example.org", "coordinator")
    await client.post(f"/v1/org-invites/{invite['invite_url'].rsplit('/', 1)[1]}/accept", headers=auth(approver))
    mission = (await client.post("/v1/missions", headers=auth(coordinator), json={
        "organization_id": org["id"], "name": "Shelter blankets", "delivery_location": "Oakland, CA",
        "delivery_deadline": (datetime.now(UTC) + timedelta(days=4)).isoformat(), "budget": "1000.00",
        "requirements": [{"item": "blankets", "quantity": 100}]})).json()
    mid = mission["id"]
    alpha = await quote(client, coordinator, mid, "a@alpha-textiles.example.org", "Alpha Textiles", 60, "1.00")
    beta = await quote(client, coordinator, mid, "b@beta-supply.example.org", "Beta Supply", 60, "2.00")
    await quote(client, coordinator, mid, "c@gamma-goods.example.org", "Gamma Goods", 100, "3.00")
    await settle_jobs(client, coordinator, mid)

    v1 = (await client.get(f"/v1/plans/{(await client.post(f'/v1/missions/{mid}/optimize', headers=auth(coordinator))).json()['plan_id']}",
                           headers=auth(coordinator))).json()
    assert v1["total_cost"] == "140.00"  # Alpha 60 x $1 + Beta 40 x $2
    assert (await client.post(f"/v1/plans/{v1['id']}/approve", headers=auth(approver))).status_code == 201
    orders = (await client.post(f"/v1/plans/{v1['id']}/purchase-orders",
                                headers={**auth(coordinator), "Idempotency-Key": "po-v1"})).json()
    for order in orders:
        sent = await client.post(f"/v1/purchase-orders/{order['id']}/send", json={"confirm": True},
                                 headers=auth(coordinator))
        assert sent.status_code == 200, sent.text
    alpha_order = next(o for o in orders if o["supplier_email"].startswith("a@"))
    beta_order = next(o for o in orders if o["supplier_email"].startswith("b@"))
    assert (await client.post(f"/v1/purchase-orders/{beta_order['id']}/supplier-response", headers=auth(beta),
                              json={"accepted": True})).status_code == 200

    declined = await client.post(f"/v1/purchase-orders/{alpha_order['id']}/supplier-response", headers=auth(alpha),
                                 json={"accepted": False, "reason": "warehouse fire"})
    assert declined.status_code == 200 and declined.json()["status"] == "supplier_declined"

    async def replanned():
        plans = (await client.get(f"/v1/missions/{mid}/plans", headers=auth(coordinator))).json()
        return plans[0] if plans[0]["version"] == 2 else None
    v2 = await wait_for(replanned)
    stale_v1 = (await client.get(f"/v1/plans/{v1['id']}", headers=auth(coordinator))).json()
    assert stale_v1["status"] == "stale" and "declined" in stale_v1["stale_reason"]
    assert v2["status"] == "feasible"
    committed = [row for row in v2["allocations"] if row.get("committed")]
    assert [(row["po_number"], row["quantity"]) for row in committed] == [(beta_order["po_number"], 40)]
    # Remainder (60) from what is left: Beta's other 20 at $2, then Gamma 40 at $3; Alpha is out.
    assert v2["committed_cost"] == "80.00" and v2["new_spend"] == "160.00" and v2["total_cost"] == "240.00"
    assert any("Alpha Textiles declined" in reason for reason in v2["difference"]["why"])

    assert (await client.post(f"/v1/plans/{v2['id']}/approve", headers=auth(approver))).status_code == 201
    new_orders = (await client.post(f"/v1/plans/{v2['id']}/purchase-orders",
                                    headers={**auth(coordinator), "Idempotency-Key": "po-v2"})).json()
    ordered = sorted((o["supplier_email"][0], sum(line["quantity"] for line in o["lines"])) for o in new_orders)
    assert ordered == [("b", 20), ("c", 40)]  # Beta's committed 40 is not ordered twice
