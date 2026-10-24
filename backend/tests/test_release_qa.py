"""Independent adversarial release checks.

Strict expected failures represent confirmed, unfixed production release blockers.
All other checks are regression tests for independently verified remediations.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from random import Random

import httpx
import pytest

from app.core import GENESIS_HASH, event_digest, verify_chain
from app.optimizer import solve
from conftest import auth, register, settle_jobs


def _future(hours: int = 24) -> str:
    return (datetime.now(UTC) + timedelta(hours=hours)).isoformat()


def _mapping_mission() -> dict:
    return {
        "id": "mission-water",
        "delivery_deadline": _future(72),
        "budget": "1000.00",
        "requirements": [{"id": "req-water", "item": "water", "quantity": 10}],
    }


def _mapping_quote(lines: list[dict]) -> dict:
    return {
        "id": "quote-water",
        "supplier_id": "supplier-water",
        "supplier_email": "water@example.com",
        "status": "submitted",
        "expires_at": _future(48),
        "shipping_cost": "0.00",
        "lines": lines,
    }


def test_requirement_id_maps_a_renamed_supplier_description() -> None:
    """A line must allocate by requirement_id even when its display text changes."""

    result = solve(_mapping_mission(), [_mapping_quote([{
        "requirement_id": "req-water", "item": "Bottled water — 24 case", "unit_price": "3.00",
        "available_quantity": 10, "delivery_date": _future(24),
    }])])

    assert result["status"] == "feasible"
    assert result["allocations"][0]["requirement_id"] == "req-water"


async def _quote_mapping_context(client: httpx.AsyncClient) -> dict:
    suffix = str(datetime.now().timestamp()).replace(".", "")
    coordinator = await register(client, f"mapping-{suffix}@ops.example.com", "coordinator")
    organization = await client.post("/v1/organizations", json={"name": "Mapping QA"}, headers=auth(coordinator))
    mission = await client.post(
        "/v1/missions",
        json={"organization_id": organization.json()["id"], "name": "Mapping RFQ", "delivery_location": "Oakland",
              "delivery_deadline": _future(72), "budget": "1000.00",
              "requirements": [{"item": "water", "quantity": 10}]},
        headers=auth(coordinator),
    )
    supplier_email = f"mapping-supplier-{suffix}@vendor.example.com"
    supplier = await register(client, supplier_email, "supplier")
    invitation = await client.post(
        f"/v1/missions/{mission.json()['id']}/invitations", json={"supplier_email": supplier_email},
        headers=auth(coordinator),
    )
    token = invitation.json()["token"]
    accepted = await client.post(f"/v1/supplier-invitations/{token}/accept", headers=auth(supplier))
    assert accepted.status_code == 200, accepted.text
    return {"supplier": supplier, "token": token, "requirement_id": mission.json()["requirements"][0]["id"]}


def _quote_payload(token: str, lines: list[dict]) -> dict:
    return {"invitation_token": token, "expires_at": _future(48), "shipping_cost": "0.00", "lines": lines}


def _quote_line(**values: str | int) -> dict:
    return {"item": "water", "unit_price": "3.00", "available_quantity": 10,
            "delivery_date": _future(24)} | values


@pytest.mark.anyio
async def test_unknown_requirement_id_is_rejected_explicitly(client: httpx.AsyncClient) -> None:
    ctx = await _quote_mapping_context(client)
    response = await client.post("/v1/quotes", headers=auth(ctx["supplier"]), json=_quote_payload(
        ctx["token"], [_quote_line(requirement_id="req_notinmission")]))
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "QUOTE_LINE_REQUIREMENT_MISMATCH"


@pytest.mark.anyio
async def test_missing_requirement_id_with_nonmatching_description_is_rejected(client: httpx.AsyncClient) -> None:
    ctx = await _quote_mapping_context(client)
    response = await client.post("/v1/quotes", headers=auth(ctx["supplier"]), json=_quote_payload(
        ctx["token"], [_quote_line(item="bottled water 24-pack")]))
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "QUOTE_LINE_REQUIREMENT_MISMATCH"


@pytest.mark.anyio
async def test_duplicate_requirement_mapping_is_rejected(client: httpx.AsyncClient) -> None:
    ctx = await _quote_mapping_context(client)
    lines = [_quote_line(requirement_id=ctx["requirement_id"]), _quote_line(requirement_id=ctx["requirement_id"])]
    response = await client.post("/v1/quotes", headers=auth(ctx["supplier"]),
                                 json=_quote_payload(ctx["token"], lines))
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "QUOTE_LINE_DUPLICATE_REQUIREMENT"


@pytest.mark.anyio
async def test_legacy_name_match_is_pinned_to_a_requirement_id(client: httpx.AsyncClient) -> None:
    ctx = await _quote_mapping_context(client)
    response = await client.post("/v1/quotes", headers=auth(ctx["supplier"]),
                                 json=_quote_payload(ctx["token"], [_quote_line()]))
    assert response.status_code == 201, response.text
    assert response.json()["lines"][0]["requirement_id"] == ctx["requirement_id"]


async def _demo_plan(client: httpx.AsyncClient) -> dict:
    coordinator = await register(client, f"qa-{datetime.now().timestamp()}@ops.example.com", "coordinator")
    organization = await client.post("/v1/organizations", json={"name": "QA Response"}, headers=auth(coordinator))
    deadline = _future(120)
    mission = await client.post(
        "/v1/missions",
        json={
            "organization_id": organization.json()["id"], "name": "QA blankets", "delivery_location": "Oakland, CA",
            "delivery_deadline": deadline, "budget": "5000.00", "currency": "USD",
            "requirements": [{"item": "blankets", "quantity": 100}],
        },
        headers=auth(coordinator),
    )
    assert mission.status_code == 201, mission.text
    mission_id = mission.json()["id"]
    seeded = await client.post(f"/v1/missions/{mission_id}/demo/seed", headers=auth(coordinator))
    assert seeded.status_code == 201, seeded.text
    await settle_jobs(client, coordinator, mission_id)
    optimized = await client.post(f"/v1/missions/{mission_id}/optimize", headers=auth(coordinator))
    assert optimized.status_code == 202, optimized.text
    return {
        "coordinator": coordinator,
        "organization_id": organization.json()["id"],
        "mission_id": mission_id,
        "plan_id": optimized.json()["plan_id"],
    }


@pytest.mark.anyio
async def test_mission_creator_cannot_approve_own_real_plan(client: httpx.AsyncClient) -> None:
    ctx = await _demo_plan(client)
    approval = await client.post(f"/v1/plans/{ctx['plan_id']}/approve", headers=auth(ctx["coordinator"]))

    assert approval.status_code == 403
    assert approval.json()["detail"]["code"] == "SEGREGATION_OF_DUTIES"


@pytest.mark.anyio
async def test_independent_organization_approver_can_approve(client: httpx.AsyncClient) -> None:
    ctx = await _demo_plan(client)
    suffix = str(datetime.now().timestamp()).replace(".", "")
    email = f"independent-{suffix}@ops.example.com"
    invite = await client.post(f"/v1/organizations/{ctx['organization_id']}/members", headers=auth(ctx["coordinator"]),
                               json={"email": email, "role": "approver"})
    assert invite.status_code == 201, invite.text
    approver = await register(client, email, "coordinator")
    token = invite.json()["invite_url"].rsplit("/", 1)[1]
    accepted = await client.post(f"/v1/org-invites/{token}/accept", headers=auth(approver))
    assert accepted.status_code == 200, accepted.text
    approval = await client.post(f"/v1/plans/{ctx['plan_id']}/approve", headers=auth(approver))
    assert approval.status_code == 201, approval.text
    assert approval.json()["requested_by"] != approval.json()["approver_id"]


@pytest.mark.anyio
async def test_organization_invitation_acceptance_is_one_time(client: httpx.AsyncClient) -> None:
    suffix = str(datetime.now().timestamp()).replace(".", "")
    coordinator = await register(client, f"org-inviter-{suffix}@ops.example.com", "coordinator")
    organization = await client.post("/v1/organizations", json={"name": "Invite replay QA"}, headers=auth(coordinator))
    email = f"org-invitee-{suffix}@ops.example.com"
    invite = await client.post(f"/v1/organizations/{organization.json()['id']}/members", headers=auth(coordinator),
                               json={"email": email, "role": "approver"})
    invitee = await register(client, email, "coordinator")
    token = invite.json()["invite_url"].rsplit("/", 1)[1]
    assert (await client.post(f"/v1/org-invites/{token}/accept", headers=auth(invitee))).status_code == 200
    assert (await client.post(f"/v1/org-invites/{token}/accept", headers=auth(invitee))).status_code == 409


@pytest.mark.anyio
@pytest.mark.xfail(strict=True, reason="REL-003: direct plan reads skip agent_sender mission isolation")
async def test_agent_cannot_read_a_plan_from_another_agent_conversation(client: httpx.AsyncClient) -> None:
    coordinator = await register(client, "agent-qa@ops.example.com", "coordinator")
    organization = await client.post("/v1/organizations", json={"name": "Agent QA"}, headers=auth(coordinator))
    issued = await client.post(
        f"/v1/organizations/{organization.json()['id']}/agent-tokens",
        json={"name": "QA agent"}, headers=auth(coordinator),
    )
    assert issued.status_code == 201, issued.text
    sender_a = {"Authorization": f"Bearer {issued.json()['token']}", "X-Agent-Sender": "conversation-a"}
    created = await client.post(
        "/v1/agent/missions",
        headers=sender_a,
        json={
            "name": "Private agent mission", "delivery_location": "Oakland, CA", "deadline_hours": 48,
            "budget": "200.00", "requirements": [{"item": "water", "quantity": 10}],
        },
    )
    assert created.status_code == 201, created.text
    optimized = await client.post(f"/v1/missions/{created.json()['id']}/optimize", headers=sender_a)
    assert optimized.status_code == 202, optimized.text
    sender_b = {"Authorization": f"Bearer {issued.json()['token']}", "X-Agent-Sender": "conversation-b"}

    leaked = await client.get(f"/v1/plans/{optimized.json()['plan_id']}", headers=sender_b)
    assert leaked.status_code == 403


@pytest.mark.anyio
async def test_plan_is_not_visible_to_another_organization_or_supplier(client: httpx.AsyncClient) -> None:
    ctx = await _demo_plan(client)
    outsider = await register(client, "separate-org@ops.example.com", "coordinator")
    supplier = await register(client, "supplier-outsider@vendor.example.com", "supplier")

    assert (await client.get(f"/v1/plans/{ctx['plan_id']}", headers=auth(outsider))).status_code == 403
    assert (await client.get(f"/v1/plans/{ctx['plan_id']}", headers=auth(supplier))).status_code == 403
    assert (await client.post(f"/v1/plans/{ctx['plan_id']}/approve", headers=auth(supplier))).status_code == 403


@pytest.mark.anyio
@pytest.mark.xfail(strict=True, reason="REL-004: supplier RFQ invitation tokens can be accepted repeatedly after use")
async def test_invitation_acceptance_is_one_time(client: httpx.AsyncClient) -> None:
    coordinator = await register(client, "invite-admin@ops.example.com", "coordinator")
    supplier = await register(client, "invite-vendor@vendor.example.com", "supplier")
    organization = await client.post("/v1/organizations", json={"name": "Invitation QA"}, headers=auth(coordinator))
    mission = await client.post(
        "/v1/missions",
        json={
            "organization_id": organization.json()["id"], "name": "Invitation safety", "delivery_location": "Oakland",
            "delivery_deadline": _future(48), "budget": "100.00", "requirements": [{"item": "water", "quantity": 1}],
        },
        headers=auth(coordinator),
    )
    invite = await client.post(
        f"/v1/missions/{mission.json()['id']}/invitations",
        json={"supplier_email": "invite-vendor@vendor.example.com"}, headers=auth(coordinator),
    )
    assert invite.status_code == 201
    first = await client.post(f"/v1/supplier-invitations/{invite.json()['token']}/accept", headers=auth(supplier))
    second = await client.post(f"/v1/supplier-invitations/{invite.json()['token']}/accept", headers=auth(supplier))

    assert first.status_code == 200
    assert second.status_code == 409


def test_optimizer_randomized_feasible_cases_preserve_all_hard_constraints() -> None:
    """Deterministic fuzz smoke test over feasible inventory, price, and shipping combinations."""

    random = Random(20261024)
    deadline = _future(96)
    for case in range(20):
        mission = {
            "id": f"m-{case}", "delivery_deadline": deadline, "budget": "10000.00",
            "requirements": [{"item": "water", "quantity": 10}, {"item": "blankets", "quantity": 10}],
            "max_supplier_share": Decimal("0.70"),
        }
        quotes = []
        for supplier in range(3):
            quotes.append({
                "id": f"q-{case}-{supplier}", "supplier_id": f"s-{supplier}",
                "supplier_email": f"s-{supplier}@example.com", "status": "submitted", "expires_at": _future(48),
                "shipping_cost": f"{random.randint(0, 20)}.00",
                "lines": [
                    {"item": "water", "unit_price": f"{random.randint(1, 9)}.00", "available_quantity": 10,
                     "delivery_date": _future(24)},
                    {"item": "blankets", "unit_price": f"{random.randint(1, 9)}.00", "available_quantity": 10,
                     "delivery_date": _future(24)},
                ],
            })
        # Invalid lifecycle rows must never appear in allocations.
        quotes.append({
            "id": f"withdrawn-{case}", "supplier_id": "withdrawn", "supplier_email": "withdrawn@example.com",
            "status": "withdrawn", "expires_at": _future(48), "shipping_cost": "0.00",
            "lines": [{"item": "water", "unit_price": "0.01", "available_quantity": 999,
                       "delivery_date": _future(24)}],
        })
        quotes.append({
            "id": f"expired-{case}", "supplier_id": "expired", "supplier_email": "expired@example.com",
            "status": "submitted", "expires_at": _future(-1), "shipping_cost": "0.00",
            "lines": [{"item": "water", "unit_price": "0.01", "available_quantity": 999,
                       "delivery_date": _future(24)}],
        })

        result = solve(mission, quotes)
        assert result["status"] == "feasible"
        assert {row["item"]: row["allocated"] for row in result["coverage"]} == {"water": 10, "blankets": 10}
        assert Decimal(result["total_cost"]) <= Decimal(mission["budget"])
        assert Decimal(result["total_cost"]) == Decimal(result["shipping_cost"]) + sum(
            (Decimal(row["line_cost"]) for row in result["allocations"]), Decimal("0")
        )
        by_quote: dict[str, int] = {}
        by_supplier: dict[str, int] = {}
        for allocation in result["allocations"]:
            assert allocation["delivery_date"] <= deadline
            assert allocation["supplier_id"] not in {"withdrawn", "expired"}
            by_quote[allocation["quote_id"]] = by_quote.get(allocation["quote_id"], 0) + allocation["quantity"]
            by_supplier[allocation["supplier_id"]] = by_supplier.get(allocation["supplier_id"], 0) + allocation["quantity"]
        assert all(quantity <= 20 for quantity in by_quote.values())
        assert all(quantity <= 14 for quantity in by_supplier.values())


def test_audit_chain_rejects_payload_deletion_reordering_link_and_hash_tampering() -> None:
    events = []
    previous = GENESIS_HASH
    for sequence in range(1, 4):
        event = {
            "sequence": sequence, "previous_hash": previous, "chain_key": "mission:qa", "action": "qa.event",
            "actor_id": "qa", "organization_id": "org", "mission_id": "mission", "entity_type": "qa",
            "entity_id": str(sequence), "metadata": {"sequence": sequence}, "created_at": f"2026-01-01T00:0{sequence}:00+00:00",
        }
        event["event_hash"] = event_digest(event)
        events.append(event)
        previous = event["event_hash"]
    assert verify_chain(events)["valid"] is True

    payload_changed = deepcopy(events)
    payload_changed[1]["metadata"] = {"forged": True}
    assert verify_chain(payload_changed)["valid"] is False
    assert verify_chain(events[:1] + events[2:])["valid"] is False
    reordered = deepcopy(events)
    reordered[1]["sequence"] = 1  # a persisted reordering changes the canonical sequence slot
    assert verify_chain(reordered)["valid"] is False
    wrong_previous = deepcopy(events)
    wrong_previous[1]["previous_hash"] = "f" * 64
    assert verify_chain(wrong_previous)["valid"] is False
    wrong_hash = deepcopy(events)
    wrong_hash[1]["event_hash"] = "e" * 64
    assert verify_chain(wrong_hash)["valid"] is False


@pytest.mark.anyio
async def test_auth_registration_is_rate_limited(client: httpx.AsyncClient) -> None:
    for number in range(12):
        response = await client.post(
            "/v1/auth/register",
            json={"email": f"rate-{number}@qa.example.com", "password": "correct horse battery staple", "role": "supplier"},
        )
        assert response.status_code == 201
    blocked = await client.post(
        "/v1/auth/register",
        json={"email": "rate-blocked@qa.example.com", "password": "correct horse battery staple", "role": "supplier"},
    )
    assert blocked.status_code == 429
