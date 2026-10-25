"""Machine access for autonomous agents (the Fetch.ai ReliefMesh buyer agent).

An agent token is bound to one organization. It can create and inspect missions, run
evidence checks, discovery, and optimization, and ask for deterministic explanations.
It can never approve a plan, issue or send a purchase order, or move money: those
endpoints require a human session (`current_user` rejects agent principals).
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import Field

from ..core import (
    AGENT_TOKEN_PREFIX, Services, audit, current_principal, current_user, get_services, new_id, now_iso,
    require_mission_access, require_org_member, token_hash,
)
from ..planning import evaluate_mission
from ..schemas import AgentTokenRequest, APIModel, MissionCreateRequest, RequirementInput
from ..workflows import latest_plan
from .procurement import create_mission_record

router = APIRouter()
AGENT_SCOPES = ["missions:create", "missions:read", "evidence:run", "discovery:run", "plans:optimize",
                "plans:explain", "continuity:read"]


@router.post("/v1/organizations/{organization_id}/agent-tokens", status_code=status.HTTP_201_CREATED)
async def create_agent_token(organization_id: str, payload: AgentTokenRequest, user: dict = Depends(current_user),
                             services: Services = Depends(get_services)) -> dict:
    membership = await require_org_member(organization_id, user, services)
    if user["role"] != "coordinator" or membership["role"] != "admin":
        raise HTTPException(status_code=403, detail="An organization administrator must issue agent tokens")
    raw = AGENT_TOKEN_PREFIX + secrets.token_urlsafe(32)
    record = {"id": new_id(), "organization_id": organization_id, "name": payload.name, "scopes": AGENT_SCOPES,
              "token_hash": token_hash(raw), "created_by": user["id"], "created_at": now_iso(), "revoked_at": None}
    await services.store.insert("agent_tokens", record)
    await audit("agent_token.created", user["id"], organization_id, None, "agent_token", record["id"], services,
                {"name": payload.name, "scopes": AGENT_SCOPES})
    return {k: v for k, v in record.items() if k != "token_hash"} | {"token": raw}


@router.get("/v1/organizations/{organization_id}/agent-tokens")
async def list_agent_tokens(organization_id: str, user: dict = Depends(current_user),
                            services: Services = Depends(get_services)) -> list:
    await require_org_member(organization_id, user, services)
    return [{k: v for k, v in row.items() if k != "token_hash"}
            for row in await services.store.find("agent_tokens", organization_id=organization_id)]


@router.post("/v1/agent-tokens/{token_id}/revoke")
async def revoke_agent_token(token_id: str, user: dict = Depends(current_user),
                             services: Services = Depends(get_services)) -> dict:
    token = await services.store.get("agent_tokens", token_id)
    if not token:
        raise HTTPException(status_code=404, detail="Agent token not found")
    membership = await require_org_member(token["organization_id"], user, services)
    if membership["role"] != "admin":
        raise HTTPException(status_code=403, detail="An organization administrator must revoke agent tokens")
    token["revoked_at"] = now_iso()
    await services.store.replace("agent_tokens", token_id, token)
    await audit("agent_token.revoked", user["id"], token["organization_id"], None, "agent_token", token_id, services)
    return {k: v for k, v in token.items() if k != "token_hash"}


def require_agent(principal: dict) -> dict:
    if principal["role"] != "agent":
        raise HTTPException(status_code=403, detail="This endpoint is for organization agent tokens")
    return principal


class AgentMissionRequest(APIModel):
    name: str = Field(min_length=2, max_length=200)
    delivery_location: str = Field(min_length=2, max_length=400)
    delivery_deadline: datetime | None = None
    deadline_hours: int | None = Field(default=None, gt=0, le=24 * 60)
    budget: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    requirements: list[RequirementInput] = Field(min_length=1, max_length=20)
    emergency_event_id: str | None = Field(default=None, max_length=200)
    max_supplier_share: Decimal | None = Field(default=None, gt=0, le=1)


@router.get("/v1/agent/overview")
async def agent_overview(principal: dict = Depends(current_principal), services: Services = Depends(get_services)) -> dict:
    require_agent(principal)
    organization = await services.store.get("organizations", principal["organization_id"])
    missions = sorted(await services.store.find("missions", organization_id=principal["organization_id"],
                                                agent_sender=principal.get("sender")),
                      key=lambda row: row["created_at"], reverse=True)
    summaries = []
    for mission in missions[:10]:
        plan = await latest_plan(services, mission["id"])
        summaries.append({
            "id": mission["id"], "name": mission["name"], "delivery_location": mission["delivery_location"],
            "requirements": mission["requirements"], "budget": mission["budget"],
            "event": (mission.get("emergency_event") or {}).get("title"),
            "latest_plan": {"version": plan["version"], "status": plan["status"], "total_cost": plan["total_cost"]}
            if plan else None,
        })
    return {"organization": organization, "agent": principal["name"], "scopes": principal["scopes"],
            "missions": summaries,
            "cannot": ["approve plans", "issue or send purchase orders", "move money", "override policy"]}


@router.post("/v1/agent/missions", status_code=status.HTTP_201_CREATED)
async def agent_create_mission(payload: AgentMissionRequest, principal: dict = Depends(current_principal),
                               services: Services = Depends(get_services)) -> dict:
    require_agent(principal)
    deadline = payload.delivery_deadline or (datetime.now(UTC) + timedelta(hours=payload.deadline_hours or 72))
    request = MissionCreateRequest(
        organization_id=principal["organization_id"], name=payload.name,
        emergency_event_id=payload.emergency_event_id, delivery_location=payload.delivery_location,
        delivery_deadline=deadline, budget=payload.budget, currency="USD", requirements=payload.requirements,
        max_supplier_share=payload.max_supplier_share,
    )
    return await create_mission_record(services, request, principal)


def explain_supplier(plan: dict[str, Any], query: str) -> dict[str, Any]:
    """Deterministic explanation assembled from the plan's stored policy and allocation record."""

    needle = query.strip().lower()
    suppliers = plan["policy"]["suppliers"]
    matches = [
        (sid, row) for sid, row in suppliers.items()
        if needle in (row.get("legal_name") or "").lower() or needle in (row.get("email") or "").lower() or needle == sid
    ]
    if not matches:
        # Fall back to the supplier sharing the most meaningful words with the query.
        stop = {"the", "a", "an", "supplier", "vendor", "allocation", "allocated", "quote", "why", "was", "is", "co",
                "inc", "llc", "company", "supply", "supplies"}
        words = {w for w in needle.replace("'s", "").split() if w not in stop and len(w) > 2}
        scored = sorted(
            ((len(words & set((row.get("legal_name") or "").lower().split())), sid, row) for sid, row in suppliers.items()),
            key=lambda entry: -entry[0],
        )
        if scored and scored[0][0] > 0 and (len(scored) == 1 or scored[0][0] > scored[1][0]):
            matches = [(scored[0][1], scored[0][2])]
    if not matches:
        return {"found": False, "message": f"No supplier matching '{query}' participates in plan v{plan['version']}."}
    sid, row = matches[0]
    name = row.get("legal_name") or row.get("email")
    allocated = [a for a in plan["allocations"] if a["supplier_id"] == sid]
    units = sum(a["quantity"] for a in allocated)
    cost = sum(Decimal(a["line_cost"]) for a in allocated)
    blocking = [d for d in row["decisions"] if d["status"] in {"NEEDS_REVIEW", "BLOCK"}]
    warnings = [d for d in row["decisions"] if d["status"] == "WARN"]
    quote_issues = [
        d for qid, q in plan["policy"]["quotes"].items() if q["supplier_id"] == sid
        for d in q["decisions"] if d["status"] in {"NEEDS_REVIEW", "BLOCK"}
    ]
    lines = [f"{name}: policy status {row['status']} in plan v{plan['version']} ({plan['status']})."]
    if allocated:
        lines.append(f"Allocated {units} units for ${cost:.2f}.")
    else:
        lines.append("Received zero allocation.")
    for d in blocking + quote_issues:
        lines.append(f"[{d['status']}] {d['rule_id']}: {d['reason']}")
    if allocated and not blocking:
        lines.append("Eligible; the optimizer chose it on cost subject to inventory, deadline, budget, and "
                     "concentration constraints.")
    if not allocated and not blocking and not quote_issues:
        lines.append("Eligible, but a cheaper feasible combination of other suppliers covered the requirement.")
    for d in warnings:
        lines.append(f"[WARN] {d['rule_id']}: {d['reason']}")
    if blocking:
        lines.append("A coordinator must review this finding in ReliefMesh; agents cannot clear or override policy.")
    return {"found": True, "supplier_id": sid, "supplier": name, "status": row["status"], "units": units,
            "cost": f"{cost:.2f}", "evidence_ids": sorted({e for d in blocking + warnings for e in d["evidence_ids"]}),
            "explanation": "\n".join(lines), "plan_id": plan["id"], "plan_version": plan["version"]}


@router.get("/v1/missions/{mission_id}/explain")
async def explain(mission_id: str, supplier: str, principal: dict = Depends(current_principal),
                  services: Services = Depends(get_services)) -> dict:
    await require_mission_access(mission_id, principal, services)
    plan = await latest_plan(services, mission_id)
    if not plan:
        raise HTTPException(status_code=404, detail="No plan has been computed for this mission yet")
    return explain_supplier(plan, supplier)


@router.get("/v1/missions/{mission_id}/brief")
async def mission_brief(mission_id: str, principal: dict = Depends(current_principal),
                        services: Services = Depends(get_services)) -> dict:
    """Compact, agent-friendly mission state with real computed values only."""

    mission, _ = await require_mission_access(mission_id, principal, services)
    report, quotes = await evaluate_mission(services, mission)
    plans = sorted(await services.store.find("plans", mission_id=mission_id), key=lambda row: row["version"])
    plan = plans[-1] if plans else None
    disruptions = sorted(await services.store.find("disruptions", mission_id=mission_id),
                         key=lambda row: row["created_at"])
    approvals = sorted(await services.store.find("approvals", mission_id=mission_id), key=lambda row: row["approved_at"])
    notifications = sorted(await services.store.find("notifications", mission_id=mission_id),
                           key=lambda row: row["created_at"], reverse=True)
    leads = await services.store.find("supplier_leads", mission_id=mission_id)
    return {
        "mission": {k: mission.get(k) for k in ("id", "name", "delivery_location", "delivery_deadline", "budget",
                                                 "currency", "requirements", "status")},
        "event": {k: (mission.get("emergency_event") or {}).get(k) for k in ("id", "title", "categories", "source_url")}
        if mission.get("emergency_event") else None,
        "quotes": {"total": len(quotes), "active": sum(q["status"] == "submitted" for q in quotes)},
        "leads": {"total": len(leads), "onboarded": sum(lead["status"] == "onboarded" for lead in leads)},
        "suppliers": [
            {"supplier_id": sid, "name": row.get("legal_name") or row.get("email"), "status": row["status"],
             "is_test": row["is_demo"],
             "open_findings": [d["rule_id"] for d in row["decisions"] if d["status"] in {"NEEDS_REVIEW", "BLOCK"}]}
            for sid, row in report["suppliers"].items()
        ],
        "latest_plan": {
            "id": plan["id"], "version": plan["version"], "status": plan["status"], "total_cost": plan["total_cost"],
            "allocations": [{"supplier": a["supplier_email"], "item": a["item"], "quantity": a["quantity"],
                             "line_cost": a["line_cost"]} for a in plan["allocations"]],
            "difference": plan.get("difference"), "trigger": plan["trigger"],
        } if plan else None,
        "plan_versions": [{"version": p["version"], "status": p["status"], "total_cost": p["total_cost"]} for p in plans],
        "latest_disruption": disruptions[-1] if disruptions else None,
        "approval": ({k: approvals[-1].get(k) for k in ("status", "amount", "plan_version", "expires_at",
                                                        "invalidation_reason")} if approvals else None),
        "recent_notifications": [n["message"] for n in notifications[:6]],
    }
