"""Break-in attempts: every ID-addressed API operation, driven by actors who must not reach Org B's data.

Routes are enumerated from the OpenAPI schema, so a new endpoint is covered automatically. Each call carries a
valid body, so a rejection is an authorization decision, not a validation error. Org B's state must be unchanged.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from conftest import auth, register, settle_jobs

# Capability URLs: the secret token in the path is the authorization (only its mission's public fields are shown).
PUBLIC_BY_DESIGN = {("GET", "/v1/emergency-events/{event_id}"), ("GET", "/v1/supplier-invitations/{token}"),
                    ("GET", "/v1/org-invites/{token}")}


def body_for(method: str, path: str, ids: dict) -> dict | None:
    soon = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    if method == "PUT" and path == "/v1/quotes/{quote_id}":
        return {"expires_at": soon, "shipping_cost": "0", "lines": [
            {"requirement_id": ids["requirement_id"], "item": "blankets", "unit_price": "0.01",
             "available_quantity": 100, "delivery_date": soon}]}
    return {
        "/v1/missions/{mission_id}/invitations": {"supplier_email": "intruder@vendor.example.org"},
        "/v1/organizations/{organization_id}/members": {"email": "intruder@ops.example.org", "role": "admin"},
        "/v1/organizations/{organization_id}/agent-tokens": {"name": "intruder"},
        "/v1/missions/{mission_id}/discovery": {"query": "blankets", "max_results": 1},
        "/v1/missions/{mission_id}/evidence/refresh": {},
        "/v1/missions/{mission_id}/disruptions": {"kind": "withdraw", "supplier_id": ids["supplier_id"]},
        "/v1/missions/{mission_id}/suppliers/{supplier_id}/review": {
            "action": "clear", "reason": "intruder clearing a finding", "rule_id": "SANCTIONS_POTENTIAL_MATCH",
            "evidence_ids": [ids["evidence_id"]]},
        "/v1/purchase-orders/{order_id}/fulfillment": {"status": "cancelled", "note": "intruder cancellation"},
        "/v1/purchase-orders/{order_id}/supplier-response": {"accepted": False, "reason": "intruder"},
        "/v1/purchase-orders/{order_id}/send": {"confirm": True},
        "/v1/leads/{lead_id}/invite": {"supplier_email": "intruder@vendor.example.org"},
        "/v1/supplier-invitations/{token}/quote-draft": {"text": "120 blankets at $1.00 each, ship tomorrow."},
    }.get(path, {} if method in {"POST", "PUT"} else None)


async def snapshot(app, organization_id: str) -> str:
    store = app.state.services.store
    keep = ("status", "version", "lines", "allocations", "total_cost", "role", "is_demo", "name")
    state = {}
    for collection in ("missions", "quotes", "plans", "approvals", "purchase_orders", "memberships", "invitations",
                       "supplier_reviews", "agent_tokens", "org_invites", "supplier_leads"):
        rows = [r for r in await store.find(collection) if r.get("organization_id") == organization_id]
        state[collection] = sorted(json.dumps({k: r.get(k) for k in ("id", *keep)}, sort_keys=True, default=str)
                                   for r in rows)
    return json.dumps(state, sort_keys=True)


@pytest.mark.anyio
async def test_no_actor_outside_org_b_can_read_or_change_any_org_b_object(app_and_client) -> None:
    app, client = app_and_client
    admin_b = await register(client, "admin-b@county-b.example.org", "coordinator")
    org_b = (await client.post("/v1/organizations", json={"name": "County B", "demo": True},
                               headers=auth(admin_b))).json()
    soon = (datetime.now(UTC) + timedelta(days=5)).isoformat()
    mission = (await client.post("/v1/missions", headers=auth(admin_b), json={
        "organization_id": org_b["id"], "name": "B shelter", "delivery_location": "Oakland, CA",
        "delivery_deadline": soon, "budget": "5000.00", "requirements": [{"item": "blankets", "quantity": 100}]})).json()
    mid = mission["id"]
    await client.post(f"/v1/missions/{mid}/demo/seed", headers=auth(admin_b))
    await settle_jobs(client, admin_b, mid)
    plan_id = (await client.post(f"/v1/missions/{mid}/optimize", headers=auth(admin_b))).json()["plan_id"]
    assert (await client.post(f"/v1/plans/{plan_id}/approve", headers=auth(admin_b))).status_code == 201
    orders = (await client.post(f"/v1/plans/{plan_id}/purchase-orders",
                                headers={**auth(admin_b), "Idempotency-Key": "b-orders"})).json()
    await client.post(f"/v1/purchase-orders/{orders[0]['id']}/send", json={"confirm": True}, headers=auth(admin_b))
    rfq = (await client.post(f"/v1/missions/{mid}/invitations", headers=auth(admin_b),
                             json={"supplier_email": "real-vendor@vendor-b.example.org"})).json()
    org_invite = (await client.post(f"/v1/organizations/{org_b['id']}/members", headers=auth(admin_b),
                                    json={"email": "approver-b@county-b.example.org", "role": "approver"})).json()
    token_b = (await client.post(f"/v1/organizations/{org_b['id']}/agent-tokens", headers=auth(admin_b),
                                 json={"name": "B agent"})).json()
    suppliers = (await client.get(f"/v1/missions/{mid}/suppliers", headers=auth(admin_b))).json()
    quote = {**suppliers[0]["quotes"][0], "supplier_id": suppliers[0]["supplier"]["id"]}
    evidence_id = suppliers[0]["evidence_history"][0]["id"]
    lead = {"id": "lead-b-1", "organization_id": org_b["id"], "mission_id": mid, "name": "Real Lead Co",
            "status": "lead", "provenance": "LIVE", "created_at": datetime.now(UTC).isoformat()}
    await app.state.services.store.insert("supplier_leads", lead)
    job_id = (await client.get(f"/v1/missions/{mid}/jobs", headers=auth(admin_b))).json()[0]["id"]
    ids = {"mission_id": mid, "plan_id": plan_id, "order_id": orders[0]["id"], "quote_id": quote["id"],
           "supplier_id": quote["supplier_id"], "evidence_id": evidence_id, "job_id": job_id, "lead_id": lead["id"],
           "organization_id": org_b["id"], "token_id": token_b["id"], "event_id": "EONET_9999",
           "requirement_id": mission["requirements"][0]["id"]}
    tokens = {"/v1/supplier-invitations/": rfq["token"], "/v1/org-invites/": org_invite["invite_url"].rsplit("/", 1)[1]}
    before = await snapshot(app, org_b["id"])

    admin_a = await register(client, "admin-a@county-a.example.org", "coordinator")
    org_a = (await client.post("/v1/organizations", json={"name": "County A"}, headers=auth(admin_a))).json()
    token_a = (await client.post(f"/v1/organizations/{org_a['id']}/agent-tokens", headers=auth(admin_a),
                                 json={"name": "A agent"})).json()["token"]
    intruders = {
        "org A admin": auth(admin_a),
        "unrelated supplier": auth(await register(client, "other-vendor@vendor-x.example.org", "supplier")),
        "org A agent": {"Authorization": f"Bearer {token_a}", "X-Agent-Sender": "agent1qintruder"},
        "org B agent, other conversation": {"Authorization": f"Bearer {token_b['token']}",
                                            "X-Agent-Sender": "agent1qanotherconversation"},
        "anonymous": {},
    }

    operations = [(method.upper(), path) for path, ops in app.openapi()["paths"].items() for method in ops
                  if "{" in path and (method.upper(), path) not in PUBLIC_BY_DESIGN]
    assert len(operations) >= 45
    breaches, unexercised = [], []
    for method, path in operations:
        url = path
        for name, value in ids.items():
            url = url.replace("{" + name + "}", value)
        for prefix, token in tokens.items():
            if url.startswith(prefix):
                url = url.replace("{token}", token)
        decisions = []
        for actor, headers in intruders.items():
            headers = {**headers, "Idempotency-Key": f"intruder-{actor}"}
            params = {"supplier": "Pioneer"} if path.endswith("/explain") else None
            response = await client.request(method, url, headers=headers, params=params,
                                            json=body_for(method, path, ids))
            decisions.append(response.status_code)
            if response.status_code < 400:
                breaches.append(f"{actor}: {method} {path} -> {response.status_code} {response.text[:120]}")
        if all(code == 422 for code in decisions):
            unexercised.append(f"{method} {path}")
    assert not breaches, "\n".join(breaches)
    assert not unexercised, f"only validation errors, authorization never reached: {unexercised}"
    assert await snapshot(app, org_b["id"]) == before
