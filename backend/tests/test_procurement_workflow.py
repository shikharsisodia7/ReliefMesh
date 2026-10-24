from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.main import create_app
from app.settings import Settings
from conftest import auth, register, settle_jobs


async def screened(client: httpx.AsyncClient, coordinator: str, mission_id: str) -> None:
    """Suppliers without screening evidence are withheld by policy, so collect it first."""

    await settle_jobs(client, coordinator, mission_id)
    refreshed = await client.post(f"/v1/missions/{mission_id}/evidence/refresh", headers=auth(coordinator))
    assert refreshed.status_code == 202, refreshed.text


@pytest.mark.anyio
async def test_withdrawal_replans_and_invalidates_approval(client: httpx.AsyncClient) -> None:
    coordinator = await register(client, "ops@reliefmesh.example.com", "coordinator")
    supplier_one = await register(client, "one@supply.example.com", "supplier")
    supplier_two = await register(client, "two@supply.example.com", "supplier")

    organization = await client.post(
        "/v1/organizations", json={"name": "Harbor Response"}, headers=auth(coordinator)
    )
    assert organization.status_code == 201
    organization_id = organization.json()["id"]
    approver = await register(client, "approver@reliefmesh.example.com", "coordinator")
    added = await client.post(f"/v1/organizations/{organization_id}/members",
                              json={"email": "approver@reliefmesh.example.com", "role": "approver"},
                              headers=auth(coordinator))
    assert added.status_code == 201 and added.json()["status"] == "pending"
    join_token = added.json()["invite_url"].rsplit("/", 1)[1]
    joined = await client.post(f"/v1/org-invites/{join_token}/accept", headers=auth(approver))
    assert joined.status_code == 200 and joined.json()["role"] == "approver"
    replay = await client.post(f"/v1/org-invites/{join_token}/accept", headers=auth(approver))
    assert replay.status_code == 409
    deadline = (datetime.now(UTC) + timedelta(days=10)).isoformat()
    mission = await client.post(
        "/v1/missions",
        json={
            "organization_id": organization_id,
            "name": "Blanket recovery",
            "delivery_location": "Oakland, CA",
            "delivery_deadline": deadline,
            "budget": "100.00",
            "currency": "USD",
            "requirements": [{"item": "blankets", "quantity": 10}],
        },
        headers=auth(coordinator),
    )
    assert mission.status_code == 201, mission.text
    mission_id = mission.json()["id"]
    outsider = await register(client, "outside-coordinator@example.com", "coordinator")
    forbidden_mission = await client.get(f"/v1/missions/{mission_id}", headers=auth(outsider))
    assert forbidden_mission.status_code == 403

    invitations: list[str] = []
    for email in ("one@supply.example.com", "two@supply.example.com"):
        invitation = await client.post(
            f"/v1/missions/{mission_id}/invitations",
            json={"supplier_email": email},
            headers=auth(coordinator),
        )
        assert invitation.status_code == 201, invitation.text
        invitations.append(invitation.json()["token"])

    for token, supplier in zip(invitations, (supplier_one, supplier_two), strict=True):
        accepted = await client.post(
            f"/v1/supplier-invitations/{token}/accept",
            headers=auth(supplier),
        )
        assert accepted.status_code == 200, accepted.text

    quote_deadline = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    delivery = (datetime.now(UTC) + timedelta(days=3)).isoformat()
    first_quote = await client.post(
        "/v1/quotes",
        json={
            "invitation_token": invitations[0],
            "expires_at": quote_deadline,
            "shipping_cost": "10.00",
            "lines": [{"item": "blankets", "unit_price": "7.00", "available_quantity": 10, "delivery_date": delivery}],
            "supplier_profile": {"legal_name": "Northwind Blanket Co", "country": "US"},
        },
        headers=auth(supplier_one),
    )
    assert first_quote.status_code == 201, first_quote.text
    second_quote = await client.post(
        "/v1/quotes",
        json={
            "invitation_token": invitations[1],
            "expires_at": quote_deadline,
            "shipping_cost": "0.00",
            "lines": [{"item": "blankets", "unit_price": "9.00", "available_quantity": 10, "delivery_date": delivery}],
            "supplier_profile": {"legal_name": "Harbor Textile Supply", "country": "US"},
        },
        headers=auth(supplier_two),
    )
    assert second_quote.status_code == 201, second_quote.text

    private_quote = await client.get(f"/v1/quotes/{second_quote.json()['id']}", headers=auth(supplier_one))
    assert private_quote.status_code == 403

    await screened(client, coordinator, mission_id)
    optimized = await client.post(f"/v1/missions/{mission_id}/optimize", headers=auth(coordinator))
    assert optimized.status_code == 202, optimized.text
    plan_id = optimized.json()["plan_id"]
    initial_plan = (await client.get(f"/v1/plans/{plan_id}", headers=auth(coordinator))).json()
    assert initial_plan["status"] == "feasible"
    assert initial_plan["total_cost"] == "80.00"

    self_approval = await client.post(f"/v1/plans/{plan_id}/approve", headers=auth(coordinator))
    assert self_approval.status_code == 403
    assert self_approval.json()["detail"]["code"] == "SEGREGATION_OF_DUTIES"
    approved = await client.post(f"/v1/plans/{plan_id}/approve", headers=auth(approver))
    assert approved.status_code == 201, approved.text
    assert approved.json()["segregation_of_duties"] == "INDEPENDENT_APPROVER"

    withdrawn = await client.post(
        f"/v1/quotes/{first_quote.json()['id']}/withdraw", headers=auth(supplier_one)
    )
    assert withdrawn.status_code == 202, withdrawn.text

    revised_plan = None
    for _ in range(80):
        plans = await client.get(f"/v1/missions/{mission_id}/plans", headers=auth(coordinator))
        assert plans.status_code == 200
        if len(plans.json()) >= 2:
            revised_plan = plans.json()[0]
            break
        await asyncio.sleep(0.02)
    assert revised_plan is not None
    assert revised_plan["version"] == 2
    assert revised_plan["total_cost"] == "90.00"
    assert revised_plan["difference"]["cost_delta"] == "+10.00"
    assert any("withdrew" in reason for reason in revised_plan["difference"]["why"])

    approvals = await client.get(f"/v1/missions/{mission_id}/approvals", headers=auth(coordinator))
    assert approvals.status_code == 200
    assert approvals.json()[0]["status"] == "invalidated"
    assert "withdrew" in approvals.json()[0]["invalidation_reason"]

    revised_approval = await client.post(
        f"/v1/plans/{revised_plan['id']}/approve", headers=auth(approver)
    )
    assert revised_approval.status_code == 201
    key = "po-request-001"
    orders = await client.post(
        f"/v1/plans/{revised_plan['id']}/purchase-orders",
        headers={**auth(coordinator), "Idempotency-Key": key},
    )
    duplicate = await client.post(
        f"/v1/plans/{revised_plan['id']}/purchase-orders",
        headers={**auth(coordinator), "Idempotency-Key": key},
    )
    assert orders.status_code == duplicate.status_code == 201
    assert orders.json() == duplicate.json()
    purchase_order_id = orders.json()[0]["id"]

    sent_order = await client.post(
        f"/v1/purchase-orders/{purchase_order_id}/send",
        json={"confirm": True},
        headers=auth(coordinator),
    )
    assert sent_order.status_code == 200, sent_order.text
    assert sent_order.json()["status"] == "sent"

    accepted_order = await client.post(
        f"/v1/purchase-orders/{purchase_order_id}/supplier-response",
        json={"accepted": True},
        headers=auth(supplier_two),
    )
    assert accepted_order.status_code == 200
    assert accepted_order.json()["status"] == "supplier_accepted"


@pytest.mark.anyio
async def test_budget_and_deadline_make_plan_honestly_infeasible(client: httpx.AsyncClient) -> None:
    coordinator = await register(client, "coord@budget.example.com", "coordinator")
    supplier = await register(client, "supplier@budget.example.com", "supplier")
    organization = await client.post(
        "/v1/organizations", json={"name": "Budget Test"}, headers=auth(coordinator)
    )
    deadline = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    mission = await client.post(
        "/v1/missions",
        json={
            "organization_id": organization.json()["id"],
            "name": "Constrained",
            "delivery_location": "Los Angeles, CA",
            "delivery_deadline": deadline,
            "budget": "20.00",
            "currency": "USD",
            "requirements": [{"item": "masks", "quantity": 5}],
        },
        headers=auth(coordinator),
    )
    invitation = await client.post(
        f"/v1/missions/{mission.json()['id']}/invitations",
        json={"supplier_email": "supplier@budget.example.com"},
        headers=auth(coordinator),
    )
    token = invitation.json()["token"]
    await client.post(f"/v1/supplier-invitations/{token}/accept", headers=auth(supplier))
    quote = await client.post(
        "/v1/quotes",
        json={
            "invitation_token": token,
            "expires_at": (datetime.now(UTC) + timedelta(hours=12)).isoformat(),
            "shipping_cost": "0.00",
            "lines": [{"item": "masks", "unit_price": "10.00", "available_quantity": 5, "delivery_date": deadline}],
            "supplier_profile": {"legal_name": "Coastal Mask Works"},
        },
        headers=auth(supplier),
    )
    assert quote.status_code == 201
    await screened(client, coordinator, mission.json()["id"])
    result = await client.post(f"/v1/missions/{mission.json()['id']}/optimize", headers=auth(coordinator))
    plan = await client.get(f"/v1/plans/{result.json()['plan_id']}", headers=auth(coordinator))
    assert plan.json()["status"] == "infeasible"
    requirement_id = mission.json()["requirements"][0]["id"]
    assert plan.json()["shortages"] == [{"item": "masks", "requirement_id": requirement_id, "required": 5, "available": 5,
                                         "shortage": 0, "reason": "budget"}]


@pytest.mark.anyio
async def test_unconfigured_email_is_recorded_as_a_failed_delivery() -> None:
    app = create_app(
        Settings(
            _env_file=None,
            app_env="development",
            storage_mode="memory",
            jwt_secret="development-secret-that-is-long-enough",
            expose_invitation_links=True,
        )
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        coordinator = await register(client, "email-admin@example.com", "coordinator")
        organization = await client.post("/v1/organizations", json={"name": "Email Test"}, headers=auth(coordinator))
        mission = await client.post(
            "/v1/missions",
            json={
                "organization_id": organization.json()["id"],
                "name": "Email delivery test",
                "delivery_location": "San Jose, CA",
                "delivery_deadline": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
                "budget": "100.00",
                "currency": "USD",
                "requirements": [{"item": "masks", "quantity": 10}],
            },
            headers=auth(coordinator),
        )
        invitation = await client.post(
            f"/v1/missions/{mission.json()['id']}/invitations",
            json={"supplier_email": "supplier-email@example.com"},
            headers=auth(coordinator),
        )
        assert invitation.status_code == 201
        assert invitation.json()["delivery_status"] == "failed"
        deliveries = await client.get(
            f"/v1/missions/{mission.json()['id']}/email-dispatches", headers=auth(coordinator)
        )
        assert deliveries.status_code == 200
        assert deliveries.json()[0]["status"] == "failed"
        assert deliveries.json()[0]["error"] == "RESEND_API_KEY is not configured"
