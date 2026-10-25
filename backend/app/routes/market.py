"""Supplier market: Apify-discovered leads and lead -> RFQ invitation."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ..core import Services, current_principal, current_user, get_services, now_iso, require_mission_access
from ..jobs import enqueue
from ..integrations import brightdata
from ..core import secret, audit
from ..schemas import DiscoveryRequest, LeadInviteRequest
from .procurement import create_invitation_record

router = APIRouter()


@router.post("/v1/leads/{lead_id}/public-web")
async def review_public_web(lead_id: str, principal: dict = Depends(current_principal),
                            services: Services = Depends(get_services)) -> dict:
    lead = await services.store.get("supplier_leads", lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    mission, _ = await require_mission_access(lead["mission_id"], principal, services)
    if principal["role"] not in {"coordinator", "agent"}:
        raise HTTPException(status_code=403, detail="Only coordinators can review supplier websites")
    result = await brightdata.fetch_public_page(
        services.hub, secret(services.settings.bright_data_api_key), services.settings.bright_data_zone,
        lead.get("website") or "",
    )
    snapshot = {"provider": "bright_data", "status": result.status, "provenance": result.provenance,
               "source_url": result.source_url, "retrieved_at": result.retrieved_at,
               "error": result.error, "data": result.data}
    lead["public_web_review"] = snapshot
    await services.store.replace("supplier_leads", lead_id, lead)
    await audit("supplier_lead.public_web_reviewed", principal["id"], mission["organization_id"], mission["id"],
                "supplier_lead", lead_id, services, {"status": result.status, "source_url": result.source_url})
    return snapshot


@router.post("/v1/missions/{mission_id}/discovery", status_code=status.HTTP_202_ACCEPTED)
async def start_discovery(mission_id: str, payload: DiscoveryRequest, principal: dict = Depends(current_principal),
                          services: Services = Depends(get_services)) -> dict:
    mission, _ = await require_mission_access(mission_id, principal, services)
    if principal["role"] not in {"coordinator", "agent"}:
        raise HTTPException(status_code=403, detail="Only coordinators can run supplier discovery")
    if principal["role"] == "agent" and principal.get("sender") not in services.settings.agent_privileged_senders:
        raise HTTPException(status_code=403, detail="Supplier discovery spends paid credits; this agent conversation "
                                                    "is not authorized to run it")
    if not services.settings.apify_api_token:
        raise HTTPException(status_code=503, detail="BLOCKED_EXTERNAL: RELIEFMESH_APIFY_API_TOKEN is not configured")
    job = await enqueue(services, "supplier_discovery", mission, coalesce=False, payload={
        "query": payload.query, "location": payload.location or mission["delivery_location"],
        "max_results": payload.max_results, "actor_id": principal["id"],
    }, trigger={"kind": "discovery", "summary": f"Discovery: {payload.query}", "at": now_iso()})
    return job


@router.get("/v1/missions/{mission_id}/leads")
async def list_leads(mission_id: str, principal: dict = Depends(current_principal),
                     services: Services = Depends(get_services)) -> list:
    await require_mission_access(mission_id, principal, services)
    return sorted(await services.store.find("supplier_leads", mission_id=mission_id),
                  key=lambda row: row["created_at"], reverse=True)


@router.post("/v1/leads/{lead_id}/invite", status_code=status.HTTP_201_CREATED)
async def invite_lead(lead_id: str, payload: LeadInviteRequest, user: dict = Depends(current_user),
                      services: Services = Depends(get_services)) -> dict:
    lead = await services.store.get("supplier_leads", lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    mission, _ = await require_mission_access(lead["mission_id"], user, services)
    if user["role"] != "coordinator":
        raise HTTPException(status_code=403, detail="Only coordinators can send RFQs")
    if lead["status"] == "onboarded":
        raise HTTPException(status_code=409, detail="This lead is already an onboarded supplier")
    invitation = await create_invitation_record(services, mission, str(payload.supplier_email), user, lead_id=lead_id)
    lead.update(status="invited", invitation_id=invitation["id"], invited_email=str(payload.supplier_email).lower(),
                invited_at=now_iso())
    await services.store.replace("supplier_leads", lead_id, lead)
    return {"lead": lead, "invitation": invitation}


@router.post("/v1/leads/{lead_id}/dismiss")
async def dismiss_lead(lead_id: str, user: dict = Depends(current_user), services: Services = Depends(get_services)) -> dict:
    lead = await services.store.get("supplier_leads", lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    await require_mission_access(lead["mission_id"], user, services)
    if lead["status"] != "lead":
        raise HTTPException(status_code=409, detail="Only an uncontacted lead can be dismissed")
    lead.update(status="dismissed", dismissed_at=now_iso())
    await services.store.replace("supplier_leads", lead_id, lead)
    return lead
