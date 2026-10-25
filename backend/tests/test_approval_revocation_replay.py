"""The production E2E sequence, pinned: an approval revoked by a real supplier change can never be replayed.

Approved V1 -> the supplier revises its quote -> V1 stale and its approval invalidated -> no purchase order can be
issued from V1, before or after V2 is approved; V2 needs its own approval, and its POs are idempotent.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from conftest import auth, register, settle_jobs
from test_continuity_guarantees import _line, _optimize, _org, _three_supplier_mission


@pytest.mark.anyio
async def test_revoked_v1_approval_cannot_issue_orders_and_v2_needs_its_own(app_and_client) -> None:
    app, client = app_and_client
    store = app.state.services.store
    coordinator, org = await _org(client)
    invite = (await client.post(f"/v1/organizations/{org['id']}/members", headers=auth(coordinator),
                                json={"email": "approver@county.example.org", "role": "approver"})).json()
    approver = await register(client, "approver@county.example.org", "coordinator")
    await client.post(f"/v1/org-invites/{invite['invite_url'].rsplit('/', 1)[1]}/accept", headers=auth(approver))
    ctx = await _three_supplier_mission(client, coordinator, org["id"])
    mid = ctx["mission"]["id"]

    plan_v1 = await _optimize(client, coordinator, mid)
    approved_v1 = await client.post(f"/v1/plans/{plan_v1['id']}/approve", headers=auth(approver))
    assert approved_v1.status_code == 201, approved_v1.text

    beta_token, beta_quote = ctx["beta"]
    revised = await client.put(f"/v1/quotes/{beta_quote['id']}", headers=auth(beta_token), json={
        "expires_at": (datetime.now(UTC) + timedelta(days=3)).isoformat(), "shipping_cost": "0",
        "lines": [_line("1.45", 60)]})
    assert revised.status_code == 200, revised.text
    await settle_jobs(client, coordinator, mid)

    assert (await store.get("plans", plan_v1["id"]))["status"] == "stale"
    assert (await store.get("approvals", approved_v1.json()["id"]))["status"] == "invalidated"
    replay_v1 = await client.post(f"/v1/plans/{plan_v1['id']}/purchase-orders",
                                  headers={**auth(coordinator), "Idempotency-Key": "replay-v1"})
    assert replay_v1.status_code == 409, replay_v1.text
    assert await store.find("purchase_orders", plan_id=plan_v1["id"]) == []

    plans = sorted((await client.get(f"/v1/missions/{mid}/plans", headers=auth(coordinator))).json(),
                   key=lambda row: row["version"])
    plan_v2 = plans[-1]
    assert plan_v2["version"] > plan_v1["version"] and plan_v2["status"] == "feasible"
    unapproved = await client.post(f"/v1/plans/{plan_v2['id']}/purchase-orders",
                                   headers={**auth(coordinator), "Idempotency-Key": "v2-early"})
    assert unapproved.status_code == 409, "a fresh plan must not inherit the revoked approval"

    approved_v2 = await client.post(f"/v1/plans/{plan_v2['id']}/approve", headers=auth(approver))
    assert approved_v2.status_code == 201, approved_v2.text
    assert approved_v2.json()["plan_hash"] == plan_v2["plan_hash"] != plan_v1["plan_hash"]

    replay_v1_again = await client.post(f"/v1/plans/{plan_v1['id']}/purchase-orders",
                                        headers={**auth(coordinator), "Idempotency-Key": "replay-v1-after-v2"})
    assert replay_v1_again.status_code == 409, "approving V2 must not revive the stale V1"
    assert (await store.get("approvals", approved_v1.json()["id"]))["status"] == "invalidated"

    issued = await client.post(f"/v1/plans/{plan_v2['id']}/purchase-orders",
                               headers={**auth(coordinator), "Idempotency-Key": "v2-once"})
    assert issued.status_code == 201, issued.text
    again = await client.post(f"/v1/plans/{plan_v2['id']}/purchase-orders",
                              headers={**auth(coordinator), "Idempotency-Key": "v2-once"})
    assert {row["id"] for row in again.json()} == {row["id"] for row in issued.json()}
    assert len(await store.find("purchase_orders", plan_id=plan_v2["id"])) == len(issued.json())
    assert await store.find("purchase_orders", plan_id=plan_v1["id"]) == []
