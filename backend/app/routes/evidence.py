"""Supplier evidence, human review decisions, and the per-mission supplier view."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from ..core import (
    Services, audit, current_principal, current_user, get_services, new_id, notify, now_iso, require_admin,
    require_mission_access,
)
from ..jobs import enqueue
from ..planning import evaluate_mission, invalidate_for_change
from ..schemas import EvidenceRefreshRequest, SupplierReviewRequest
from ..workflows import latest_plan, refresh_supplier_evidence

router = APIRouter()

CLEARABLE_RULES = {"SANCTIONS_POTENTIAL_MATCH", "SANCTIONS_EXACT_MATCH", "PRODUCT_RECALL_MATCH", "CRS_VERIFICATION"}


@router.get("/v1/missions/{mission_id}/suppliers")
async def mission_suppliers(mission_id: str, principal: dict = Depends(current_principal),
                            services: Services = Depends(get_services)) -> list:
    mission, _ = await require_mission_access(mission_id, principal, services)
    report, quotes = await evaluate_mission(services, mission)
    rows = []
    for supplier_id, policy in report["suppliers"].items():
        supplier = await services.store.get("suppliers", supplier_id) or {"id": supplier_id}
        evidence = sorted(
            await services.store.find("evidence", organization_id=mission["organization_id"], subject_id=supplier_id),
            key=lambda row: row["created_at"], reverse=True,
        )
        reviews = sorted(
            await services.store.find("supplier_reviews", organization_id=mission["organization_id"],
                                      supplier_id=supplier_id),
            key=lambda row: row["created_at"], reverse=True,
        )
        latest: dict[str, Any] = {}
        for record in evidence:
            latest.setdefault(record["type"], record)
        rows.append({
            "supplier": {k: supplier.get(k) for k in ("id", "email", "legal_name", "website", "country", "is_demo",
                                                       "data_origin", "lead_id")},
            "policy": policy,
            "quotes": [
                {"id": q["id"], "status": q["status"], "version": q["version"],
                 "policy": report["quotes"][q["id"]]} for q in quotes if q["supplier_id"] == supplier_id
            ],
            "latest_evidence": latest,
            "evidence_history": evidence[:30],
            "reviews": reviews,
        })
    return sorted(rows, key=lambda row: (row["supplier"].get("legal_name") or row["supplier"].get("email") or ""))


@router.post("/v1/missions/{mission_id}/evidence/refresh", status_code=status.HTTP_202_ACCEPTED)
async def refresh_evidence(mission_id: str, payload: EvidenceRefreshRequest | None = None,
                           principal: dict = Depends(current_principal),
                           services: Services = Depends(get_services)) -> dict:
    mission, _ = await require_mission_access(mission_id, principal, services)
    if principal["role"] not in {"coordinator", "agent"}:
        raise HTTPException(status_code=403, detail="Only coordinators can run evidence checks")
    quotes = await services.store.find("quotes", mission_id=mission_id)
    supplier_ids = sorted({q["supplier_id"] for q in quotes})
    if payload and payload.supplier_ids:
        unknown = set(payload.supplier_ids) - set(supplier_ids)
        if unknown:
            raise HTTPException(status_code=404, detail="Supplier is not participating in this mission")
        supplier_ids = sorted(payload.supplier_ids)
    result = await refresh_supplier_evidence(services, mission, supplier_ids, principal["id"])
    return result


@router.post("/v1/missions/{mission_id}/suppliers/{supplier_id}/review", status_code=status.HTTP_201_CREATED)
async def review_supplier(mission_id: str, supplier_id: str, payload: SupplierReviewRequest,
                          user: dict = Depends(current_user), services: Services = Depends(get_services)) -> dict:
    """Record a human compliance decision. Clearances bind to the exact evidence currently triggering."""

    mission, _ = await require_mission_access(mission_id, user, services)
    await require_admin(mission, user, services)
    report, quotes = await evaluate_mission(services, mission)
    if supplier_id not in report["suppliers"]:
        raise HTTPException(status_code=404, detail="Supplier is not participating in this mission")
    evidence_ids: list[str] = []
    if payload.action == "clear":
        if payload.rule_id not in CLEARABLE_RULES:
            raise HTTPException(status_code=422, detail="Only evidence-backed review findings can be cleared")
        triggering = [d for d in report["suppliers"][supplier_id]["decisions"]
                      if d["rule_id"] == payload.rule_id and d["status"] in {"NEEDS_REVIEW", "BLOCK"}]
        if not triggering:
            raise HTTPException(status_code=409, detail="That finding is not currently open for this supplier")
        evidence_ids = triggering[0]["evidence_ids"]
    review = {
        "id": new_id(), "organization_id": mission["organization_id"], "mission_id": mission_id,
        "supplier_id": supplier_id, "action": payload.action, "rule_id": payload.rule_id,
        "evidence_ids": evidence_ids, "reason": payload.reason, "reviewer_id": user["id"], "created_at": now_iso(),
    }
    await services.store.insert("supplier_reviews", review)
    await audit(f"supplier.review.{payload.action}", user["id"], mission["organization_id"], mission_id, "supplier",
                supplier_id, services, {"rule_id": payload.rule_id, "evidence_ids": evidence_ids,
                                        "reason": payload.reason})
    after, _ = await evaluate_mission(services, mission)
    before_status = report["suppliers"][supplier_id]["status"]
    after_status = after["suppliers"][supplier_id]["status"]
    name = after["suppliers"][supplier_id].get("legal_name") or supplier_id
    job = None
    if before_status != after_status:
        summary = f"{name} policy {before_status} -> {after_status} after human review ({payload.action})"
        await notify(services, mission, "policy_review", summary, "warning", {"supplier_id": supplier_id})
        current = await latest_plan(services, mission_id)
        if current and current["status"] in {"feasible", "approved"}:
            await invalidate_for_change(services, mission, user["id"], summary)
            job = await enqueue(services, "replan", mission,
                                trigger={"kind": "policy_change", "supplier_id": supplier_id, "summary": summary,
                                         "at": now_iso()})
    return {"review": review, "status_before": before_status, "status_after": after_status,
            "replan_job_id": job["id"] if job else None}


@router.get("/v1/evidence/{evidence_id}")
async def get_evidence(evidence_id: str, principal: dict = Depends(current_principal),
                       services: Services = Depends(get_services)) -> dict:
    record = await services.store.get("evidence", evidence_id)
    if not record:
        raise HTTPException(status_code=404, detail="Evidence not found")
    if principal["role"] == "supplier" or (record.get("mission_id") is None):
        raise HTTPException(status_code=403, detail="Evidence access denied")
    await require_mission_access(record["mission_id"], principal, services)
    return record
