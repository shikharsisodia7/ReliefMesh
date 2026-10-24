"""Judge-controlled scenario: labeled TEST suppliers and real, persisted supply-chain disruptions.

Seeding creates four supplier accounts flagged ``is_demo`` (badged TEST everywhere) with
synthetic quotes. Their evidence is NOT synthetic: names are screened against the live
OFAC/SAM/openFDA/USAspending sources exactly like real suppliers. Disruptions mutate the
persisted quote through the same code path a supplier's own edit uses, so invalidation,
background replanning, and re-approval are the production mechanisms, not an animation.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from ..core import (
    Services, audit, current_user, get_services, new_id, notify, now_iso, require_admin, require_mission_access,
    token_hash,
)
from ..jobs import enqueue
from ..planning import evaluate_mission, invalidate_for_change
from ..schemas import DisruptionRequest
from ..workflows import apply_quote_change, latest_plan

router = APIRouter()

# Pioneer Logistics Supply shares a name with the real SDN-listed entity "PIONEER LOGISTICS"; the live
# OFAC screen flags it as a POTENTIAL_MATCH, which the policy engine routes to human review.
DEMO_SUPPLIERS = [
    {"key": "a", "legal_name": "Bayside Relief Supply Co", "price": "1.00", "share": "0.60", "ship": "0.020", "eta": 0.40},
    {"key": "b", "legal_name": "Pioneer Logistics Supply", "price": "0.85", "share": "1.00", "ship": "0.010", "eta": 0.30},
    {"key": "c", "legal_name": "Golden Gate Medical Logistics", "price": "1.08", "share": "0.70", "ship": "0.015", "eta": 0.50},
    {"key": "d", "legal_name": "Sierra Backup Provisions", "price": "1.22", "share": "1.00", "ship": "0.005", "eta": 0.75},
]


def cents(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def require_demo(services: Services) -> None:
    if not services.settings.demo_controls_enabled:
        raise HTTPException(status_code=403, detail="Demo controls are disabled in this environment")


@router.post("/v1/missions/{mission_id}/demo/seed", status_code=status.HTTP_201_CREATED)
async def seed_demo_suppliers(mission_id: str, user: dict = Depends(current_user),
                              services: Services = Depends(get_services)) -> dict:
    require_demo(services)
    mission, _ = await require_mission_access(mission_id, user, services)
    await require_admin(mission, user, services)
    existing = await services.store.find("suppliers", demo_mission_id=mission_id)
    if existing:
        return {"suppliers": existing, "seeded": False}
    now = datetime.now(UTC)
    deadline = datetime.fromisoformat(mission["delivery_deadline"].replace("Z", "+00:00"))
    total_units = sum(int(row["quantity"]) for row in mission["requirements"])
    budget = Decimal(mission["budget"])
    base = budget / total_units * Decimal("0.60")
    created = []
    for spec in DEMO_SUPPLIERS:
        supplier_id = new_id()
        email = f"test-supplier-{spec['key']}.{mission_id[:8]}@reliefmesh-demo.example.com"
        await services.store.insert("users", {
            "id": supplier_id, "email": email, "role": "supplier", "password_hash": None, "active": True,
            "is_demo": True, "created_at": now_iso(),
        })
        supplier = {
            "id": supplier_id, "user_id": supplier_id, "email": email, "legal_name": spec["legal_name"],
            "country": "US", "is_demo": True, "data_origin": "TEST", "demo_organization_id": mission["organization_id"],
            "demo_mission_id": mission_id, "created_at": now_iso(),
        }
        await services.store.insert("suppliers", supplier)
        invitation = {
            "id": new_id(), "mission_id": mission_id, "organization_id": mission["organization_id"],
            "supplier_email": email, "token_hash": token_hash(secrets.token_urlsafe(32)), "status": "accepted",
            "accepted_by_user_id": supplier_id, "accepted_at": now_iso(), "expires_at": mission["delivery_deadline"],
            "created_by": user["id"], "created_at": now_iso(), "delivery_status": "not_sent_test_supplier",
            "is_demo": True,
        }
        await services.store.insert("invitations", invitation)
        delivery = now + (deadline - now) * spec["eta"]
        lines = []
        for requirement in mission["requirements"]:
            quantity = max(1, int((Decimal(requirement["quantity"]) * Decimal(spec["share"])).to_integral_value()))
            lines.append({
                "item": requirement["item"], "unit_price": f"{cents(base * Decimal(spec['price'])):.2f}",
                "available_quantity": quantity, "delivery_date": delivery.isoformat(), "restrictions": None,
                "evidence_url": None,
            })
        quote = {
            "id": new_id(), "mission_id": mission_id, "organization_id": mission["organization_id"],
            "invitation_id": invitation["id"], "supplier_id": supplier_id, "supplier_email": email,
            "supplier_name": spec["legal_name"], "status": "submitted", "version": 1, "provenance": "SYNTHETIC",
            "is_demo": True, "expires_at": (deadline - timedelta(minutes=5)).isoformat(), "currency": mission["currency"],
            "shipping_cost": f"{cents(budget * Decimal(spec['ship'])):.2f}", "lines": lines,
            "created_at": now_iso(), "updated_at": now_iso(),
        }
        await services.store.insert("quotes", quote)
        created.append(supplier)
    await audit("demo.seeded", user["id"], mission["organization_id"], mission_id, "mission", mission_id, services,
                {"suppliers": [s["id"] for s in created]})
    await notify(services, mission, "demo_seeded",
                 "Four clearly labeled TEST suppliers submitted synthetic quotes; live evidence checks are running.",
                 "info")
    job = await enqueue(services, "evidence_refresh", mission, coalesce=False,
                        payload={"supplier_ids": [s["id"] for s in created], "actor_id": user["id"]},
                        trigger={"kind": "demo_seeded", "summary": "TEST suppliers seeded", "at": now_iso()})
    return {"suppliers": created, "seeded": True, "evidence_job_id": job["id"]}


def describe(kind: str, name: str, before: dict[str, Any], after: dict[str, Any]) -> str:
    if kind == "withdraw":
        return f"{name} withdrew its quote"
    if kind == "reduce_inventory":
        return f"{name} cut available inventory {before['quantity']} -> {after['quantity']} units"
    if kind == "raise_price":
        return f"{name} raised unit price ${before['unit_price']} -> ${after['unit_price']}"
    if kind == "delay_eta":
        return f"{name} delayed delivery to {after['delivery_date'][:16]}Z"
    return f"{name} was blocked by policy"


@router.post("/v1/missions/{mission_id}/disruptions", status_code=status.HTTP_202_ACCEPTED)
async def disrupt_supply_chain(mission_id: str, payload: DisruptionRequest, user: dict = Depends(current_user),
                               services: Services = Depends(get_services)) -> dict:
    require_demo(services)
    mission, _ = await require_mission_access(mission_id, user, services)
    await require_admin(mission, user, services)
    supplier = await services.store.get("suppliers", payload.supplier_id)
    quotes = [q for q in await services.store.find("quotes", mission_id=mission_id, supplier_id=payload.supplier_id)]
    if not supplier or not quotes:
        raise HTTPException(status_code=404, detail="Supplier is not participating in this mission")
    name = supplier.get("legal_name") or supplier["email"]
    quote = max(quotes, key=lambda row: row["created_at"])
    job = None
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}

    if payload.kind == "block_supplier":
        # A block is the buyer's own policy decision, so it is allowed for any supplier.
        reason = payload.reason or "Blocked during a supply-chain disruption drill"
        review = {
            "id": new_id(), "organization_id": mission["organization_id"], "mission_id": mission_id,
            "supplier_id": payload.supplier_id, "action": "block", "rule_id": None, "evidence_ids": [],
            "reason": reason, "reviewer_id": user["id"], "created_at": now_iso(),
        }
        report_before, _ = await evaluate_mission(services, mission)
        await services.store.insert("supplier_reviews", review)
        before = {"policy_status": report_before["suppliers"][payload.supplier_id]["status"]}
        after = {"policy_status": "BLOCK"}
        summary = f"{name} was blocked by policy: {reason}"
        await notify(services, mission, "supplier_blocked", summary, "warning", {"supplier_id": payload.supplier_id})
        current = await latest_plan(services, mission_id)
        if current and current["status"] in {"feasible", "approved"}:
            await invalidate_for_change(services, mission, user["id"], summary)
        job = await enqueue(services, "replan", mission, trigger={
            "kind": "policy_change", "supplier_id": payload.supplier_id, "summary": summary, "at": now_iso()})
    else:
        if not (supplier.get("is_demo") and supplier.get("demo_organization_id") == mission["organization_id"]):
            raise HTTPException(status_code=403, detail="Only a supplier can change its own quote; judge disruptions "
                                                        "may only mutate this mission's labeled TEST suppliers")
        if quote["status"] != "submitted":
            raise HTTPException(status_code=409, detail="That supplier's quote is no longer active")
        lines = [dict(line) for line in quote["lines"]]
        targets = [line for line in lines if payload.item in (None, line["item"])]
        if not targets:
            raise HTTPException(status_code=404, detail="That item is not on the supplier's quote")
        first = targets[0]
        before = {"quantity": first["available_quantity"], "unit_price": first["unit_price"],
                  "delivery_date": first["delivery_date"], "status": quote["status"]}
        if payload.kind == "withdraw":
            after = {"status": "withdrawn"}
        else:
            for line in targets:
                if payload.kind == "reduce_inventory":
                    line["available_quantity"] = payload.quantity or max(1, line["available_quantity"] // 3)
                elif payload.kind == "raise_price":
                    line["unit_price"] = f"{payload.unit_price or cents(Decimal(line['unit_price']) * Decimal('1.35')):.2f}"
                elif payload.kind == "delay_eta":
                    delivered = datetime.fromisoformat(line["delivery_date"].replace("Z", "+00:00"))
                    line["delivery_date"] = (delivered + timedelta(hours=payload.delay_hours or 72)).isoformat()
            after = {"quantity": first["available_quantity"], "unit_price": first["unit_price"],
                     "delivery_date": first["delivery_date"], "status": "submitted"}
        summary = describe(payload.kind, name, before, after)
        quote, job = await apply_quote_change(
            services, quote, mission, user["id"], kind="withdrawn" if payload.kind == "withdraw" else "updated",
            summary=summary, withdraw=payload.kind == "withdraw",
            updates=None if payload.kind == "withdraw" else {"lines": lines},
        )
    disruption = {
        "id": new_id(), "mission_id": mission_id, "organization_id": mission["organization_id"],
        "kind": payload.kind, "supplier_id": payload.supplier_id, "supplier_name": name, "quote_id": quote["id"],
        "before": before, "after": after, "summary": summary, "actor_id": user["id"],
        "job_id": job["id"] if job else None, "created_at": now_iso(),
    }
    await services.store.insert("disruptions", disruption)
    await audit("supply_chain.disrupted", user["id"], mission["organization_id"], mission_id, "supplier",
                payload.supplier_id, services, {"kind": payload.kind, "summary": summary, "job_id": disruption["job_id"]})
    return disruption


@router.get("/v1/missions/{mission_id}/disruptions")
async def list_disruptions(mission_id: str, user: dict = Depends(current_user),
                           services: Services = Depends(get_services)) -> list:
    await require_mission_access(mission_id, user, services)
    return sorted(await services.store.find("disruptions", mission_id=mission_id), key=lambda row: row["created_at"],
                  reverse=True)
