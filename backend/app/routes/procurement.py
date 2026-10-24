"""Core procurement workflow: accounts, missions, RFQs, quotes, plans, approvals, POs, audit."""

from __future__ import annotations

import secrets
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from ..auth import create_access_token, hash_password, verify_password
from ..core import (
    Services, audit, secret, current_principal, current_user, get_services, invitation_from_token, new_id, notify, now_iso,
    public_user, record_email, require_admin, require_mission_access, require_org_member, token_hash, verify_chain,
)
from ..integrations import emergency, gemini
from ..jobs import enqueue
from ..planning import compute_plan, evaluate_mission, plan_hash
from ..requirements import assign_quote_lines, new_requirement_id
from ..schemas import (
    CreateOrganizationRequest, FulfillmentUpdateRequest, InvitationCreateRequest, LoginRequest, MemberInviteRequest,
    MissionCreateRequest,
    PurchaseOrderSendRequest, QuoteCreateRequest, QuoteDraftRequest, QuoteUpdateRequest, RegisterRequest, SupplierProfileInput,
    SupplierResponseRequest,
)
from ..workflows import apply_quote_change

router = APIRouter()
MISSION_PUBLIC_FIELDS = ("id", "name", "delivery_location", "delivery_deadline", "requirements", "currency")


@router.post("/v1/auth/register", status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, request: Request, services: Services = Depends(get_services)) -> dict:
    services.rate_limiter.check(f"register:{request.client.host if request.client else 'unknown'}")
    email_address = str(payload.email).lower()
    if await services.store.find("users", email=email_address):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = {
        "id": new_id(), "email": email_address, "role": payload.role,
        "password_hash": hash_password(payload.password), "active": True, "created_at": now_iso(),
    }
    await services.store.insert("users", user)
    await audit("user.registered", user["id"], None, None, "user", user["id"], services)
    return {"access_token": create_access_token(user, services.settings), "token_type": "bearer",
            "user": public_user(user)}


ORG_INVITE_DAYS = 7


async def org_invite_from_token(token: str, services: Services) -> dict:
    invites = await services.store.find("org_invites", token_hash=token_hash(token))
    if not invites:
        raise HTTPException(status_code=404, detail="Organization invitation not found")
    invite = invites[0]
    if invite["status"] != "pending":
        raise HTTPException(status_code=409, detail="This organization invitation was already used")
    if invite["expires_at"] <= now_iso():
        raise HTTPException(status_code=410, detail="This organization invitation has expired")
    return invite


@router.post("/v1/auth/login")
async def login(payload: LoginRequest, request: Request, services: Services = Depends(get_services)) -> dict:
    services.rate_limiter.check(f"login:{request.client.host if request.client else 'unknown'}")
    users = await services.store.find("users", email=str(payload.email).lower())
    if not users or not users[0].get("password_hash") or not verify_password(payload.password, users[0]["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    user = users[0]
    return {"access_token": create_access_token(user, services.settings), "token_type": "bearer",
            "user": public_user(user)}


@router.get("/v1/me")
async def me(user: dict = Depends(current_user)) -> dict:
    return public_user(user)


@router.post("/v1/organizations", status_code=status.HTTP_201_CREATED)
async def create_organization(payload: CreateOrganizationRequest, user: dict = Depends(current_user),
                              services: Services = Depends(get_services)) -> dict:
    if user["role"] != "coordinator":
        raise HTTPException(status_code=403, detail="Only coordinators can create organizations")
    if payload.demo and not services.settings.demo_enabled:
        raise HTTPException(status_code=422, detail={"code": "DEMO_MODE_DISABLED",
                                                     "message": "Demo organizations exist only in demo deployments"})
    organization = {"id": new_id(), "name": payload.name.strip(), "is_demo": payload.demo, "created_at": now_iso()}
    await services.store.insert("organizations", organization)
    await services.store.insert("memberships", {
        "id": new_id(), "organization_id": organization["id"], "user_id": user["id"], "role": "admin",
        "created_at": now_iso(),
    })
    await audit("organization.created", user["id"], organization["id"], None, "organization", organization["id"],
                services)
    return organization


@router.post("/v1/organizations/{organization_id}/members", status_code=status.HTTP_201_CREATED)
async def invite_member(organization_id: str, payload: MemberInviteRequest, user: dict = Depends(current_user),
                        services: Services = Depends(get_services)) -> dict:
    membership = await require_org_member(organization_id, user, services)
    if membership["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only an organization administrator can add members")
    email_address = str(payload.email).lower()
    existing = await services.store.find("users", email=email_address)
    if existing and existing[0]["role"] != "coordinator":
        raise HTTPException(status_code=409, detail="Supplier accounts cannot join a buyer organization")
    raw_token = secrets.token_urlsafe(32)
    invite = {"id": new_id(), "organization_id": organization_id, "email": email_address, "role": payload.role,
              "status": "pending", "invited_by": user["id"], "token_hash": token_hash(raw_token),
              "expires_at": (datetime.now(UTC) + timedelta(days=ORG_INVITE_DAYS)).isoformat(), "created_at": now_iso()}
    await services.store.insert("org_invites", invite)
    organization = await services.store.get("organizations", organization_id)
    url = f"{services.settings.frontend_origin}/join/{raw_token}"
    attempt = await record_email(
        to=email_address, subject=f"Join {(organization or {}).get('name')} on ReliefMesh",
        html=f"<p>You were invited as <strong>{payload.role}</strong>.</p><p><a href=\"{url}\">Accept invitation</a></p>",
        kind="org_invite", entity_id=invite["id"], services=services)
    await audit("organization.member_invited", user["id"], organization_id, None, "org_invite", invite["id"], services,
                {"email": email_address, "role": payload.role, "delivery_status": attempt["status"]})
    # The secret link goes only to the inviting admin (and the invitee's inbox when email is configured).
    return {k: v for k, v in invite.items() if k != "token_hash"} | {"invite_url": url,
                                                                     "delivery_status": attempt["status"]}


@router.get("/v1/org-invites/{token}")
async def get_org_invite(token: str, services: Services = Depends(get_services)) -> dict:
    invite = await org_invite_from_token(token, services)
    organization = await services.store.get("organizations", invite["organization_id"])
    return {"organization": (organization or {}).get("name"), "email": invite["email"], "role": invite["role"],
            "expires_at": invite["expires_at"]}


@router.post("/v1/org-invites/{token}/accept")
async def accept_org_invite(token: str, user: dict = Depends(current_user),
                            services: Services = Depends(get_services)) -> dict:
    invite = await org_invite_from_token(token, services)
    if user["role"] != "coordinator" or user["email"] != invite["email"]:
        raise HTTPException(status_code=403, detail="Sign in as the invited coordinator email to accept")
    if not await services.store.find("memberships", organization_id=invite["organization_id"], user_id=user["id"]):
        await services.store.insert("memberships", {
            "id": new_id(), "organization_id": invite["organization_id"], "user_id": user["id"], "role": invite["role"],
            "created_at": now_iso(), "invited_by": invite["invited_by"]})
    invite.update(status="accepted", accepted_at=now_iso(), user_id=user["id"])
    await services.store.replace("org_invites", invite["id"], invite)
    await audit("organization.member_joined", user["id"], invite["organization_id"], None, "membership", user["id"],
                services, {"role": invite["role"], "invited_by": invite["invited_by"]})
    return {"organization_id": invite["organization_id"], "role": invite["role"]}


@router.get("/v1/organizations/{organization_id}/members")
async def list_members(organization_id: str, user: dict = Depends(current_user),
                       services: Services = Depends(get_services)) -> dict:
    membership = await require_org_member(organization_id, user, services)
    members = []
    for membership in await services.store.find("memberships", organization_id=organization_id):
        member = await services.store.get("users", membership["user_id"])
        members.append({"user_id": membership["user_id"], "email": (member or {}).get("email"),
                        "role": membership["role"], "joined_at": membership["created_at"]})
    pending = [{k: v for k, v in i.items() if k != "token_hash"}
               for i in await services.store.find("org_invites", organization_id=organization_id)
               if i["status"] == "pending"] if membership["role"] == "admin" else []
    return {"members": members, "pending": pending}


@router.get("/v1/organizations")
async def list_organizations(user: dict = Depends(current_user), services: Services = Depends(get_services)) -> list:
    organizations = []
    for membership in await services.store.find("memberships", user_id=user["id"]):
        organization = await services.store.get("organizations", membership["organization_id"])
        if organization:
            organizations.append({**organization, "membership_role": membership["role"]})
    return organizations


async def resolve_event_snapshot(services: Services, event_id: str | None) -> tuple[dict | None, str | None]:
    if not event_id:
        return None, None
    result = await emergency.eonet_event(services.hub, event_id)
    if result.ok:
        return result.data, None
    return None, result.error or "EONET event could not be retrieved"


async def create_mission_record(services: Services, payload: MissionCreateRequest, actor: dict) -> dict:
    await require_org_member(payload.organization_id, actor, services)
    if payload.delivery_deadline <= datetime.now(UTC):
        raise HTTPException(status_code=422, detail="Delivery deadline must be in the future")
    snapshot, event_error = await resolve_event_snapshot(services, payload.emergency_event_id)
    body = payload.model_dump(mode="json")
    body["requirements"] = [{**row, "id": row.get("id") or new_requirement_id()} for row in body["requirements"]]
    if len({row["id"] for row in body["requirements"]}) != len(body["requirements"]):
        raise HTTPException(status_code=422, detail="Requirement IDs must be unique")
    mission = {
        "id": new_id(),
        **body,
        "emergency_event": snapshot,
        "emergency_event_error": event_error,
        "delivery_state": emergency.state_code(payload.delivery_location),
        "created_by": actor["id"],
        "created_via": "agent" if actor["role"] == "agent" else "web",
        "agent_sender": actor.get("sender") if actor["role"] == "agent" else None,
        "status": "open",
        "created_at": now_iso(),
    }
    await services.store.insert("missions", mission)
    await audit("mission.created", actor["id"], mission["organization_id"], mission["id"], "mission", mission["id"],
                services, {"emergency_event_id": payload.emergency_event_id, "via": mission["created_via"]})
    return mission


@router.post("/v1/missions", status_code=status.HTTP_201_CREATED)
async def create_mission(payload: MissionCreateRequest, user: dict = Depends(current_user),
                         services: Services = Depends(get_services)) -> dict:
    if user["role"] != "coordinator":
        raise HTTPException(status_code=403, detail="Only coordinators can create missions")
    return await create_mission_record(services, payload, user)


@router.get("/v1/missions")
async def list_missions(organization_id: str, user: dict = Depends(current_user),
                        services: Services = Depends(get_services)) -> list:
    await require_org_member(organization_id, user, services)
    return sorted(await services.store.find("missions", organization_id=organization_id),
                  key=lambda row: row["created_at"], reverse=True)


@router.get("/v1/missions/{mission_id}")
async def get_mission(mission_id: str, user: dict = Depends(current_user),
                      services: Services = Depends(get_services)) -> dict:
    mission, _ = await require_mission_access(mission_id, user, services)
    return mission


async def create_invitation_record(services: Services, mission: dict, supplier_email: str, actor: dict,
                                   lead_id: str | None = None) -> dict:
    raw_token = secrets.token_urlsafe(32)
    invitation = {
        "id": new_id(), "mission_id": mission["id"], "organization_id": mission["organization_id"],
        "supplier_email": supplier_email.lower(), "token_hash": token_hash(raw_token), "status": "sent",
        "expires_at": mission["delivery_deadline"], "created_by": actor["id"], "created_at": now_iso(),
        "lead_id": lead_id,
    }
    await services.store.insert("invitations", invitation)
    url = f"{services.settings.frontend_origin}/invitations/{raw_token}"
    attempt = await record_email(
        to=invitation["supplier_email"], subject=f"RFQ invitation: {mission['name']}",
        html=(f"<p>You have been invited to quote for <strong>{mission['name']}</strong>.</p>"
              f"<p><a href=\"{url}\">Open secure RFQ</a></p>"),
        kind="rfq_invitation", entity_id=invitation["id"], services=services,
    )
    invitation["delivery_status"] = attempt["status"]
    invitation["delivery"] = {key: attempt[key] for key in ("provider", "status", "message_id", "sent_at", "error")}
    await services.store.replace("invitations", invitation["id"], invitation)
    await audit("rfq.invited", actor["id"], mission["organization_id"], mission["id"], "invitation", invitation["id"],
                services, {"delivery_status": attempt["status"], "lead_id": lead_id})
    response = {key: value for key, value in invitation.items() if key != "token_hash"}
    # Only the invited address can accept the link (sign-in email must match), so the coordinator may relay it.
    if services.settings.expose_invitation_links or attempt["status"] != "sent":
        response["token"] = raw_token
        response["invitation_url"] = url
        response["link_reason"] = "development" if services.settings.expose_invitation_links else "email_not_sent"
    return response


@router.post("/v1/missions/{mission_id}/invitations", status_code=status.HTTP_201_CREATED)
async def create_invitation(mission_id: str, payload: InvitationCreateRequest, user: dict = Depends(current_user),
                            services: Services = Depends(get_services)) -> dict:
    mission, _ = await require_mission_access(mission_id, user, services)
    if user["role"] != "coordinator":
        raise HTTPException(status_code=403, detail="Only coordinators can send RFQs")
    return await create_invitation_record(services, mission, str(payload.supplier_email), user)


@router.get("/v1/missions/{mission_id}/invitations")
async def list_invitations(mission_id: str, user: dict = Depends(current_user),
                           services: Services = Depends(get_services)) -> list:
    await require_mission_access(mission_id, user, services)
    rows = await services.store.find("invitations", mission_id=mission_id)
    return sorted(({k: v for k, v in row.items() if k != "token_hash"} for row in rows),
                  key=lambda row: row["created_at"], reverse=True)


@router.get("/v1/supplier-invitations/{token}")
async def get_invitation(token: str, services: Services = Depends(get_services)) -> dict:
    invitation = await invitation_from_token(token, services)
    mission = await services.store.get("missions", invitation["mission_id"])
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    return {"mission": {key: mission[key] for key in MISSION_PUBLIC_FIELDS},
            "supplier_email": invitation["supplier_email"], "status": invitation["status"]}


async def ensure_supplier(services: Services, user: dict) -> dict:
    supplier = await services.store.get("suppliers", user["id"])
    if not supplier:
        supplier = {"id": user["id"], "user_id": user["id"], "email": user["email"], "legal_name": None,
                    "is_demo": bool(user.get("is_demo")), "data_origin": "USER_SUBMITTED", "created_at": now_iso()}
        await services.store.insert("suppliers", supplier)
    return supplier


@router.post("/v1/supplier-invitations/{token}/accept")
async def accept_invitation(token: str, user: dict = Depends(current_user),
                            services: Services = Depends(get_services)) -> dict:
    invitation = await invitation_from_token(token, services)
    if user["role"] != "supplier" or user["email"] != invitation["supplier_email"]:
        raise HTTPException(status_code=403, detail="This invitation belongs to a different supplier account")
    invitation.update(status="accepted", accepted_by_user_id=user["id"], accepted_at=now_iso())
    await services.store.replace("invitations", invitation["id"], invitation)
    supplier = await ensure_supplier(services, user)
    if invitation.get("lead_id"):
        lead = await services.store.get("supplier_leads", invitation["lead_id"])
        if lead:
            lead.update(status="onboarded", supplier_id=user["id"], onboarded_at=now_iso())
            await services.store.replace("supplier_leads", lead["id"], lead)
        supplier["lead_id"] = invitation["lead_id"]
        await services.store.replace("suppliers", supplier["id"], supplier)
    await audit("rfq.accepted", user["id"], invitation["organization_id"], invitation["mission_id"], "invitation",
                invitation["id"], services)
    return {"invitation_id": invitation["id"], "mission_id": invitation["mission_id"], "status": invitation["status"]}


@router.post("/v1/supplier-invitations/{token}/quote-draft")
async def draft_quote_from_text(token: str, payload: QuoteDraftRequest, user: dict = Depends(current_user),
                                services: Services = Depends(get_services)) -> dict:
    """Gemini pre-fills the quote form from pasted text. Nothing is stored; the supplier still submits."""
    invitation = await invitation_from_token(token, services)
    if user["role"] != "supplier" or invitation.get("accepted_by_user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Supplier invitation access denied")
    mission = await services.store.get("missions", invitation["mission_id"])
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    services.assist_limiter.check(f"quote-draft:{user['id']}")
    result = await gemini.draft_quote(services.hub, secret(services.settings.gemini_api_key),
                                      services.settings.gemini_model, payload.text, mission)
    if result.status == "BLOCKED_EXTERNAL":
        raise HTTPException(status_code=503, detail={"code": "GEMINI_NOT_CONFIGURED", "message": result.error})
    if not result.ok:
        raise HTTPException(status_code=502, detail={"code": "GEMINI_UNAVAILABLE",
                                                     "message": "The quote assistant is unavailable; fill the form "
                                                                "manually."})
    await audit("quote.draft_extracted", user["id"], invitation["organization_id"], invitation["mission_id"],
                "invitation", invitation["id"], services,
                {"model": result.meta.get("model"), "text_chars": len(payload.text), "lines": len(result.data["lines"])})
    return {**result.data, "model": result.meta.get("model"), "provenance": "AI_DRAFT",
            "notice": "Draft extracted by Gemini from your text. Review every field before submitting."}


async def apply_profile(services: Services, supplier: dict, profile: SupplierProfileInput) -> tuple[dict, bool]:
    changed = supplier.get("legal_name") != profile.legal_name
    supplier.update(profile.model_dump(mode="json"))
    supplier["updated_at"] = now_iso()
    await services.store.replace("suppliers", supplier["id"], supplier)
    return supplier, changed


@router.get("/v1/supplier/profile")
async def get_supplier_profile(user: dict = Depends(current_user), services: Services = Depends(get_services)) -> dict:
    if user["role"] != "supplier":
        raise HTTPException(status_code=403, detail="Supplier access required")
    return await ensure_supplier(services, user)


@router.put("/v1/supplier/profile")
async def update_supplier_profile(payload: SupplierProfileInput, user: dict = Depends(current_user),
                                  services: Services = Depends(get_services)) -> dict:
    if user["role"] != "supplier":
        raise HTTPException(status_code=403, detail="Supplier access required")
    supplier, changed = await apply_profile(services, await ensure_supplier(services, user), payload)
    if changed:
        # A new legal identity needs fresh screening in every mission this supplier has quoted.
        for quote in await services.store.find("quotes", supplier_id=user["id"], status="submitted"):
            mission = await services.store.get("missions", quote["mission_id"])
            if mission:
                await enqueue(services, "evidence_refresh", mission,
                              trigger={"kind": "profile_changed", "supplier_id": user["id"], "at": now_iso()})
    return supplier


@router.post("/v1/quotes", status_code=status.HTTP_201_CREATED)
async def submit_quote(payload: QuoteCreateRequest, user: dict = Depends(current_user),
                       services: Services = Depends(get_services)) -> dict:
    invitation = await invitation_from_token(payload.invitation_token, services)
    if user["role"] != "supplier" or invitation.get("accepted_by_user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Supplier invitation access denied")
    if payload.expires_at <= datetime.now(UTC):
        raise HTTPException(status_code=422, detail="Quote expiration must be in the future")
    if await services.store.find("quotes", invitation_id=invitation["id"]):
        raise HTTPException(status_code=409, detail="Use the quote update endpoint to revise this submission")
    mission = await services.store.get("missions", invitation["mission_id"])
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    lines = assign_quote_lines([line.model_dump(mode="json") for line in payload.lines], mission)
    supplier = await ensure_supplier(services, user)
    if payload.supplier_profile:
        supplier, _ = await apply_profile(services, supplier, payload.supplier_profile)
    quote = {
        "id": new_id(),
        "mission_id": invitation["mission_id"],
        "organization_id": invitation["organization_id"],
        "invitation_id": invitation["id"],
        "supplier_id": user["id"],
        "supplier_email": user["email"],
        "supplier_name": supplier.get("legal_name"),
        "status": "submitted",
        "version": 1,
        "provenance": "SYNTHETIC" if supplier.get("is_demo") else "USER_SUBMITTED",
        **payload.model_dump(mode="json", exclude={"invitation_token", "supplier_profile", "lines"}),
        "lines": lines,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await services.store.insert("quotes", quote)
    await audit("quote.submitted", user["id"], quote["organization_id"], quote["mission_id"], "quote", quote["id"],
                services)
    if supplier.get("legal_name"):
        await enqueue(services, "evidence_refresh", mission,
                      trigger={"kind": "quote_submitted", "supplier_id": user["id"], "at": now_iso()})
    return quote


@router.get("/v1/supplier/invitations")
async def list_supplier_invitations(user: dict = Depends(current_user),
                                    services: Services = Depends(get_services)) -> list:
    if user["role"] != "supplier":
        raise HTTPException(status_code=403, detail="Supplier access required")
    results = []
    for invitation in await services.store.find("invitations", supplier_email=user["email"]):
        mission = await services.store.get("missions", invitation["mission_id"])
        if mission:
            results.append({k: v for k, v in invitation.items() if k != "token_hash"}
                           | {"mission": {key: mission[key] for key in MISSION_PUBLIC_FIELDS}})
    return sorted(results, key=lambda row: row["created_at"], reverse=True)


@router.get("/v1/supplier/quotes")
async def list_supplier_quotes(user: dict = Depends(current_user), services: Services = Depends(get_services)) -> list:
    if user["role"] != "supplier":
        raise HTTPException(status_code=403, detail="Supplier access required")
    return sorted(await services.store.find("quotes", supplier_id=user["id"]), key=lambda row: row["updated_at"],
                  reverse=True)


async def quote_access(quote_id: str, user: dict, services: Services) -> dict:
    quote = await services.store.get("quotes", quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    if user["role"] == "supplier":
        if quote["supplier_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="Supplier quotes are private")
    else:
        await require_org_member(quote["organization_id"], user, services)
    return quote


@router.get("/v1/quotes/{quote_id}")
async def get_quote(quote_id: str, user: dict = Depends(current_user), services: Services = Depends(get_services)) -> dict:
    return await quote_access(quote_id, user, services)


@router.put("/v1/quotes/{quote_id}")
async def update_quote(quote_id: str, payload: QuoteUpdateRequest, user: dict = Depends(current_user),
                       services: Services = Depends(get_services)) -> dict:
    quote = await quote_access(quote_id, user, services)
    if user["role"] != "supplier" or quote["status"] != "submitted":
        raise HTTPException(status_code=409, detail="Only active supplier quotes can be updated")
    mission = await services.store.get("missions", quote["mission_id"])
    assert mission
    supplier = await services.store.get("suppliers", user["id"])
    label = (supplier or {}).get("legal_name") or user["email"]
    updates = payload.model_dump(mode="json")
    updates["lines"] = assign_quote_lines(updates["lines"], mission)
    quote, job = await apply_quote_change(services, quote, mission, user["id"], kind="updated",
                                          summary=f"{label} revised its quote", updates=updates)
    await audit("quote.updated", user["id"], quote["organization_id"], quote["mission_id"], "quote", quote_id, services,
                {"job_id": job["id"]})
    return {**quote, "replan_job_id": job["id"]}


@router.post("/v1/quotes/{quote_id}/withdraw", status_code=status.HTTP_202_ACCEPTED)
async def withdraw_quote(quote_id: str, user: dict = Depends(current_user),
                         services: Services = Depends(get_services)) -> dict:
    quote = await quote_access(quote_id, user, services)
    if user["role"] != "supplier":
        raise HTTPException(status_code=403, detail="Only a supplier can withdraw its quote")
    if quote["status"] == "withdrawn":
        return {"quote_id": quote_id, "status": "withdrawn"}
    mission = await services.store.get("missions", quote["mission_id"])
    assert mission
    supplier = await services.store.get("suppliers", user["id"])
    label = (supplier or {}).get("legal_name") or user["email"]
    quote, job = await apply_quote_change(services, quote, mission, user["id"], kind="withdrawn",
                                          summary=f"{label} withdrew its quote", withdraw=True)
    await audit("quote.withdrawn", user["id"], quote["organization_id"], quote["mission_id"], "quote", quote_id,
                services, {"job_id": job["id"]})
    return {"quote_id": quote_id, "status": "withdrawn", "replan_job_id": job["id"]}


@router.get("/v1/missions/{mission_id}/quotes")
async def list_quotes(mission_id: str, user: dict = Depends(current_user),
                      services: Services = Depends(get_services)) -> list:
    _, membership = await require_mission_access(mission_id, user, services)
    if user["role"] != "coordinator" or membership["role"] not in {"admin", "coordinator"}:
        raise HTTPException(status_code=403, detail="Only procurement coordinators can review quotes")
    return sorted(await services.store.find("quotes", mission_id=mission_id), key=lambda row: row["created_at"],
                  reverse=True)


@router.post("/v1/missions/{mission_id}/optimize", status_code=status.HTTP_202_ACCEPTED)
async def optimize_mission(mission_id: str, principal: dict = Depends(current_principal),
                           services: Services = Depends(get_services)) -> dict:
    mission, _ = await require_mission_access(mission_id, principal, services)
    if principal["role"] not in {"coordinator", "agent"}:
        raise HTTPException(status_code=403, detail="Only coordinators can run the optimizer")
    plan = await compute_plan(services, mission["id"], "manual" if principal["role"] == "coordinator" else "agent")
    return {"plan_id": plan["id"], "status": plan["status"], "version": plan["version"]}


@router.get("/v1/plans/{plan_id}")
async def get_plan(plan_id: str, principal: dict = Depends(current_principal),
                   services: Services = Depends(get_services)) -> dict:
    plan = await services.store.get("plans", plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    await require_org_member(plan["organization_id"], principal, services)
    return plan


@router.get("/v1/missions/{mission_id}/plans")
async def list_plans(mission_id: str, principal: dict = Depends(current_principal),
                     services: Services = Depends(get_services)) -> list:
    await require_mission_access(mission_id, principal, services)
    return sorted(await services.store.find("plans", mission_id=mission_id), key=lambda row: row["version"],
                  reverse=True)


@router.post("/v1/plans/{plan_id}/approve", status_code=status.HTTP_201_CREATED)
async def approve_plan(plan_id: str, user: dict = Depends(current_user), services: Services = Depends(get_services)) -> dict:
    plan = await services.store.get("plans", plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    membership = await require_org_member(plan["organization_id"], user, services)
    if user["role"] != "coordinator" or membership["role"] not in {"admin", "approver"}:
        raise HTTPException(status_code=403, detail="An organization administrator or approver must approve this plan")
    mission = await services.store.get("missions", plan["mission_id"])
    organization = await services.store.get("organizations", plan["organization_id"])
    assert mission and organization
    self_approval = mission.get("created_by") == user["id"]
    allocated = {row["supplier_id"] for row in plan["allocations"]}
    allocated_suppliers = [await services.store.get("suppliers", sid) for sid in allocated]
    all_test = bool(allocated) and all((row or {}).get("is_demo") for row in allocated_suppliers)
    demo_override = bool(organization.get("is_demo") and services.settings.demo_enabled and all_test)
    if self_approval and not demo_override:
        raise HTTPException(status_code=403, detail={
            "code": "SEGREGATION_OF_DUTIES",
            "message": "The coordinator who requested this procurement cannot approve it. Another approver in the "
                       "organization must review and approve the plan.",
            "requested_by": mission.get("created_by")})
    if plan["status"] != "feasible":
        raise HTTPException(status_code=409, detail="Only a current feasible plan can be approved")
    newer = [p for p in await services.store.find("plans", mission_id=plan["mission_id"]) if p["version"] > plan["version"]]
    if newer:
        raise HTTPException(status_code=409, detail="A newer plan version exists; approve the latest plan")
    if plan_hash(plan) != plan.get("plan_hash"):
        raise HTTPException(status_code=409, detail="Plan contents do not match their recorded hash")
    report, _ = await evaluate_mission(services, mission)
    if report["fingerprint"] != plan["policy"]["fingerprint"]:
        raise HTTPException(status_code=409,
                            detail="Supplier evidence or quotes changed since this plan was computed; re-optimize")
    if Decimal(plan["total_cost"]) > Decimal(mission["budget"]):
        raise HTTPException(status_code=409, detail="Plan total exceeds the mission spending ceiling")
    if [a for a in await services.store.find("approvals", plan_id=plan_id) if a["status"] in {"active", "consumed"}]:
        raise HTTPException(status_code=409, detail="This plan already has an approval")
    approved_at = datetime.now(UTC)
    approval = {
        "id": new_id(), "plan_id": plan_id, "plan_version": plan["version"], "plan_hash": plan["plan_hash"],
        "mission_id": plan["mission_id"], "organization_id": plan["organization_id"], "amount": plan["total_cost"],
        "currency": plan.get("currency", "USD"), "spending_ceiling": mission["budget"],
        "scope": "issue_purchase_orders", "approver_id": user["id"], "approver_email": user["email"],
        "requested_by": mission.get("created_by"),
        "segregation_of_duties": "DEMO_ORG_SELF_APPROVAL_OVERRIDE" if self_approval else "INDEPENDENT_APPROVER",
        "status": "active",
        "approved_at": approved_at.isoformat(),
        "expires_at": (approved_at + timedelta(minutes=services.settings.approval_ttl_minutes)).isoformat(),
        "nonce": secrets.token_hex(16),
    }
    await services.store.insert("approvals", approval)
    plan["status"] = "approved"
    await services.store.replace("plans", plan_id, plan)
    await audit("plan.approved", user["id"], plan["organization_id"], plan["mission_id"], "approval", approval["id"],
                services, {"plan_id": plan_id, "amount": plan["total_cost"], "plan_hash": plan["plan_hash"],
                           "expires_at": approval["expires_at"]})
    await notify(services, mission, "plan_approved",
                 f"Plan v{plan['version']} approved for ${plan['total_cost']} (expires {approval['expires_at'][:16]}Z).",
                 "success", {"approval_id": approval["id"]})
    return approval


@router.get("/v1/missions/{mission_id}/approvals")
async def list_approvals(mission_id: str, principal: dict = Depends(current_principal),
                         services: Services = Depends(get_services)) -> list:
    await require_mission_access(mission_id, principal, services)
    return sorted(await services.store.find("approvals", mission_id=mission_id), key=lambda row: row["approved_at"],
                  reverse=True)


@router.post("/v1/plans/{plan_id}/purchase-orders", status_code=status.HTTP_201_CREATED)
async def create_purchase_orders(plan_id: str, request: Request, user: dict = Depends(current_user),
                                 services: Services = Depends(get_services)) -> list:
    key = request.headers.get("Idempotency-Key")
    if not key or len(key) > 128:
        raise HTTPException(status_code=400, detail="An Idempotency-Key header is required")
    plan = await services.store.get("plans", plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    await require_org_member(plan["organization_id"], user, services)
    existing = await services.store.find("purchase_orders", plan_id=plan_id, idempotency_key=key)
    if existing:
        return existing
    if user["role"] != "coordinator" or plan["status"] != "approved":
        raise HTTPException(status_code=409, detail="An approved current plan is required")
    approvals = await services.store.find("approvals", plan_id=plan_id)
    active = [a for a in approvals if a["status"] == "active"]
    if not active:
        if any(a["status"] == "consumed" for a in approvals):
            raise HTTPException(status_code=409, detail="This approval was already used to issue purchase orders")
        raise HTTPException(status_code=409, detail="No active approval exists for this exact plan")
    approval = active[0]
    if approval["expires_at"] <= now_iso():
        approval.update(status="expired", invalidation_reason="approval window elapsed")
        await services.store.replace("approvals", approval["id"], approval)
        raise HTTPException(status_code=409, detail="The approval has expired; approve the plan again")
    if approval["plan_hash"] != plan["plan_hash"] or plan_hash(plan) != plan["plan_hash"] \
            or approval["plan_version"] != plan["version"]:
        raise HTTPException(status_code=409, detail="The approval does not match this exact plan version")
    if Decimal(plan["total_cost"]) > Decimal(approval["spending_ceiling"]):
        raise HTTPException(status_code=409, detail="Plan total exceeds the approved spending ceiling")
    mission = await services.store.get("missions", plan["mission_id"])
    organization = await services.store.get("organizations", plan["organization_id"])
    assert mission and organization
    by_supplier: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for allocation in plan["allocations"]:
        by_supplier[allocation["supplier_id"]].append(allocation)
    orders = []
    for supplier_id, allocations in by_supplier.items():
        order = {
            "id": new_id(),
            "po_number": f"RM-{datetime.now(UTC):%Y%m%d}-{new_id()[:8].upper()}",
            "plan_id": plan_id, "plan_version": plan["version"], "plan_hash": plan["plan_hash"],
            "mission_id": plan["mission_id"], "organization_id": plan["organization_id"],
            "supplier_id": supplier_id, "supplier_email": allocations[0]["supplier_email"],
            "buyer_organization": organization["name"], "delivery_location": mission["delivery_location"],
            "approval_id": approval["id"], "lines": allocations,
            "subtotal": f"{sum(Decimal(row['line_cost']) for row in allocations):.2f}",
            "currency": plan.get("currency", "USD"), "status": "draft", "idempotency_key": key,
            "created_at": now_iso(), "events": [{"status": "draft", "at": now_iso(), "actor_id": user["id"]}],
        }
        await services.store.insert("purchase_orders", order)
        orders.append(order)
        await audit("purchase_order.created", user["id"], plan["organization_id"], plan["mission_id"],
                    "purchase_order", order["id"], services, {"approval_id": approval["id"]})
    approval.update(status="consumed", consumed_at=now_iso(), consumed_idempotency_key=key)
    await services.store.replace("approvals", approval["id"], approval)
    return orders


async def purchase_order_access(order_id: str, user: dict, services: Services) -> dict:
    order = await services.store.get("purchase_orders", order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    if user["role"] == "supplier":
        if order["supplier_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="Supplier purchase orders are private")
    else:
        await require_org_member(order["organization_id"], user, services)
    return order


@router.get("/v1/purchase-orders")
async def list_purchase_orders(organization_id: str | None = None, mission_id: str | None = None,
                               user: dict = Depends(current_user), services: Services = Depends(get_services)) -> list:
    if user["role"] == "supplier":
        rows = await services.store.find("purchase_orders", supplier_id=user["id"])
    else:
        if not organization_id:
            raise HTTPException(status_code=422, detail="organization_id is required for coordinators")
        await require_org_member(organization_id, user, services)
        rows = await services.store.find("purchase_orders", organization_id=organization_id)
    if mission_id:
        rows = [row for row in rows if row["mission_id"] == mission_id]
    return sorted(rows, key=lambda row: row["created_at"], reverse=True)


@router.post("/v1/purchase-orders/{order_id}/send")
async def send_purchase_order(order_id: str, payload: PurchaseOrderSendRequest, user: dict = Depends(current_user),
                              services: Services = Depends(get_services)) -> dict:
    order = await purchase_order_access(order_id, user, services)
    if user["role"] != "coordinator":
        raise HTTPException(status_code=403, detail="Only a coordinator can send a purchase order")
    if order["status"] != "draft":
        raise HTTPException(status_code=409, detail="Only draft purchase orders can be sent")
    plan = await services.store.get("plans", order["plan_id"])
    if not plan or plan["status"] != "approved":
        raise HTTPException(status_code=409, detail="The plan behind this draft is no longer approved")
    supplier = await services.store.get("suppliers", order["supplier_id"])
    if supplier and supplier.get("is_demo"):
        # TEST suppliers have reserved example.com addresses; record the skip instead of emailing.
        attempt = {"id": new_id(), "to": order["supplier_email"], "subject": f"Purchase order {order['po_number']}",
                   "kind": "purchase_order", "entity_id": order_id, "status": "skipped_test_supplier",
                   "provider_id": None, "error": None, "created_at": now_iso()}
        await services.store.insert("email_dispatches", attempt)
    else:
        attempt = await record_email(
            to=order["supplier_email"], subject=f"Purchase order {order['po_number']}",
            html=f"<p>Purchase order {order['po_number']} is ready for your acceptance.</p>",
            kind="purchase_order", entity_id=order_id, services=services,
        )
    if attempt["status"] not in {"sent", "skipped_test_supplier"}:
        order["send_error"] = attempt["error"]
        await services.store.replace("purchase_orders", order_id, order)
        raise HTTPException(status_code=502, detail="Purchase order email was not delivered; the failure was recorded")
    order.update(status="sent", sent_at=now_iso())
    order["events"].append({"status": "sent", "at": now_iso(), "actor_id": user["id"]})
    await services.store.replace("purchase_orders", order_id, order)
    await audit("purchase_order.sent", user["id"], order["organization_id"], order["mission_id"], "purchase_order",
                order_id, services)
    return order


@router.post("/v1/purchase-orders/{order_id}/supplier-response")
async def supplier_response(order_id: str, payload: SupplierResponseRequest, user: dict = Depends(current_user),
                            services: Services = Depends(get_services)) -> dict:
    order = await purchase_order_access(order_id, user, services)
    if user["role"] != "supplier" or order["status"] != "sent":
        raise HTTPException(status_code=409, detail="Only a sent supplier order can be answered")
    order.update(status="supplier_accepted" if payload.accepted else "supplier_declined",
                 supplier_response_at=now_iso(), supplier_response_reason=payload.reason)
    order["events"].append({"status": order["status"], "at": now_iso(), "actor_id": user["id"]})
    await services.store.replace("purchase_orders", order_id, order)
    await audit("purchase_order.supplier_response", user["id"], order["organization_id"], order["mission_id"],
                "purchase_order", order_id, services, {"accepted": payload.accepted})
    mission = await services.store.get("missions", order["mission_id"])
    if mission:
        await notify(services, mission, "po_response",
                     f"{order['po_number']} was {'accepted' if payload.accepted else 'declined'} by the supplier.",
                     "success" if payload.accepted else "warning", {"order_id": order_id})
    return order


@router.post("/v1/purchase-orders/{order_id}/fulfillment")
async def update_fulfillment(order_id: str, payload: FulfillmentUpdateRequest, user: dict = Depends(current_user),
                             services: Services = Depends(get_services)) -> dict:
    order = await purchase_order_access(order_id, user, services)
    if user["role"] != "supplier" or order["status"] not in {"supplier_accepted", "in_fulfillment"}:
        raise HTTPException(status_code=409, detail="Only an accepted supplier order can receive fulfillment updates")
    order["status"] = payload.status
    order["events"].append({"status": payload.status, "note": payload.note, "at": now_iso(), "actor_id": user["id"]})
    await services.store.replace("purchase_orders", order_id, order)
    await services.store.insert("fulfillment_events", {
        "id": new_id(), "purchase_order_id": order_id, "status": payload.status, "note": payload.note,
        "actor_id": user["id"], "created_at": now_iso(),
    })
    await audit("fulfillment.updated", user["id"], order["organization_id"], order["mission_id"], "purchase_order",
                order_id, services, {"status": payload.status})
    mission = await services.store.get("missions", order["mission_id"])
    if mission:
        await notify(services, mission, "fulfillment", f"{order['po_number']}: {payload.status} - {payload.note}",
                     "info", {"order_id": order_id})
    return order


@router.get("/v1/purchase-orders/{order_id}/pdf")
async def purchase_order_pdf(order_id: str, user: dict = Depends(current_user),
                             services: Services = Depends(get_services)) -> Response:
    order = await purchase_order_access(order_id, user, services)
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle(order["po_number"])
    pdf.drawString(72, 740, f"ReliefMesh Purchase Order {order['po_number']}")
    pdf.drawString(72, 720, f"Buyer: {order['buyer_organization']}")
    pdf.drawString(72, 700, f"Supplier: {order['supplier_email']}")
    pdf.drawString(72, 680, f"Delivery: {order['delivery_location']}")
    y = 650
    for line in order["lines"]:
        pdf.drawString(72, y, f"{line['item']}: {line['quantity']} x {line['unit_price']} = {line['line_cost']}")
        y -= 20
    pdf.drawString(72, y - 10, f"Approval reference: {order['approval_id']}")
    pdf.drawString(72, y - 30, f"Plan v{order.get('plan_version', '?')} hash: {order.get('plan_hash', '')[:32]}")
    pdf.save()
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{order["po_number"]}.pdf"'})


@router.get("/v1/missions/{mission_id}/audit")
async def mission_audit(mission_id: str, principal: dict = Depends(current_principal),
                        services: Services = Depends(get_services)) -> list:
    await require_mission_access(mission_id, principal, services)
    return sorted(await services.store.find("audit_events", mission_id=mission_id),
                  key=lambda row: (row.get("sequence", 0), row["created_at"]))


@router.get("/v1/missions/{mission_id}/audit/verify")
async def verify_mission_audit(mission_id: str, principal: dict = Depends(current_principal),
                               services: Services = Depends(get_services)) -> dict:
    await require_mission_access(mission_id, principal, services)
    events = await services.store.find("audit_events", chain_key=f"mission:{mission_id}")
    return verify_chain(events)


@router.get("/v1/missions/{mission_id}/notifications")
async def mission_notifications(mission_id: str, principal: dict = Depends(current_principal),
                                services: Services = Depends(get_services)) -> list:
    await require_mission_access(mission_id, principal, services)
    return sorted(await services.store.find("notifications", mission_id=mission_id),
                  key=lambda row: row["created_at"], reverse=True)


@router.get("/v1/missions/{mission_id}/email-dispatches")
async def mission_email_dispatches(mission_id: str, user: dict = Depends(current_user),
                                   services: Services = Depends(get_services)) -> list:
    _, membership = await require_mission_access(mission_id, user, services)
    if user["role"] != "coordinator" or membership["role"] not in {"admin", "coordinator"}:
        raise HTTPException(status_code=403, detail="Only coordinators can review email delivery")
    attempts = []
    for invitation in await services.store.find("invitations", mission_id=mission_id):
        attempts.extend(await services.store.find("email_dispatches", entity_id=invitation["id"]))
    return sorted(attempts, key=lambda row: row["created_at"], reverse=True)


@router.get("/v1/jobs/{job_id}")
async def get_job(job_id: str, principal: dict = Depends(current_principal),
                  services: Services = Depends(get_services)) -> dict:
    job = await services.store.get("jobs", job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await require_mission_access(job["mission_id"], principal, services)
    return job


@router.get("/v1/missions/{mission_id}/jobs")
async def list_jobs(mission_id: str, principal: dict = Depends(current_principal),
                    services: Services = Depends(get_services)) -> list:
    await require_mission_access(mission_id, principal, services)
    return sorted(await services.store.find("jobs", mission_id=mission_id), key=lambda row: row["created_at"],
                  reverse=True)


@router.get("/v1/missions/{mission_id}/policy")
async def mission_policy(mission_id: str, principal: dict = Depends(current_principal),
                         services: Services = Depends(get_services)) -> dict:
    mission, _ = await require_mission_access(mission_id, principal, services)
    report, _ = await evaluate_mission(services, mission)
    return report


__all__ = ["router", "create_mission_record", "create_invitation_record", "require_admin", "notify"]
