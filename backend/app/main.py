from __future__ import annotations

import asyncio
import hashlib
import secrets
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from io import BytesIO
from typing import Any, AsyncIterator
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from .auth import create_access_token, decode_access_token, hash_password, verify_password
from .emailing import EmailGateway, ResendEmailGateway, TestEmailGateway
from .optimizer import solve
from .schemas import (
    CreateOrganizationRequest,
    FulfillmentUpdateRequest,
    InvitationCreateRequest,
    LoginRequest,
    MissionCreateRequest,
    PurchaseOrderSendRequest,
    QuoteCreateRequest,
    QuoteUpdateRequest,
    RegisterRequest,
    SupplierResponseRequest,
)
from .settings import Settings, get_settings
from .store import MemoryStore, MongoStore, Store


bearer = HTTPBearer(auto_error=False)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def new_id() -> str:
    return str(uuid4())


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in user.items() if key not in {"password_hash"}}


class RateLimiter:
    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self.events: dict[str, list[float]] = defaultdict(list)

    def check(self, client_key: str) -> None:
        loop_time = asyncio.get_running_loop().time()
        events = [time for time in self.events[client_key] if loop_time - time < 60]
        if len(events) >= self.per_minute:
            raise HTTPException(status_code=429, detail="Too many authentication attempts")
        events.append(loop_time)
        self.events[client_key] = events


class Services:
    def __init__(self, settings: Settings, store: Store, email: EmailGateway) -> None:
        self.settings = settings
        self.store = store
        self.email = email
        self.rate_limiter = RateLimiter(settings.auth_rate_limit_per_minute)
        self.jobs: set[asyncio.Task] = set()

    def schedule(self, coroutine: Any) -> None:
        task = asyncio.create_task(coroutine)
        self.jobs.add(task)
        task.add_done_callback(self.jobs.discard)


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or get_settings()
    if runtime_settings.storage_mode == "memory":
        store: Store = MemoryStore()
    else:
        if not runtime_settings.mongodb_uri:
            raise RuntimeError("RELIEFMESH_MONGODB_URI is required when storage mode is mongo")
        store = MongoStore(runtime_settings.mongodb_uri, runtime_settings.mongodb_database)
    email: EmailGateway = TestEmailGateway() if runtime_settings.app_env == "test" else ResendEmailGateway(runtime_settings)
    services = Services(runtime_settings, store, email)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await services.store.initialize()
        queued_jobs = await services.store.find("jobs", status="queued")
        for job in queued_jobs:
            if job["type"] == "replan":
                services.schedule(run_replan_job(job["id"]))
        yield
        if services.jobs:
            await asyncio.gather(*services.jobs, return_exceptions=True)
        await services.store.close()

    app = FastAPI(
        title="ReliefMesh Procurement API",
        version="0.1.0",
        description="Authenticated procurement, deterministic optimization, approvals, and purchase orders.",
        lifespan=lifespan,
    )
    app.state.services = services
    app.add_middleware(
        CORSMiddleware,
        allow_origins=runtime_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
    )

    def get_services() -> Services:
        return services

    async def current_user(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
        active_services: Services = Depends(get_services),
    ) -> dict[str, Any]:
        if credentials is None:
            raise HTTPException(status_code=401, detail="Authentication is required")
        claims = decode_access_token(credentials.credentials, active_services.settings)
        user = await active_services.store.get("users", claims["sub"])
        if not user or not user.get("active", False):
            raise HTTPException(status_code=401, detail="Session user is unavailable")
        return user

    async def require_org_member(
        organization_id: str, user: dict[str, Any], active_services: Services
    ) -> dict[str, Any]:
        memberships = await active_services.store.find(
            "memberships", organization_id=organization_id, user_id=user["id"]
        )
        if not memberships:
            raise HTTPException(status_code=403, detail="Organization access denied")
        return memberships[0]

    async def require_mission_access(
        mission_id: str, user: dict[str, Any], active_services: Services
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        mission = await active_services.store.get("missions", mission_id)
        if not mission:
            raise HTTPException(status_code=404, detail="Mission not found")
        membership = await require_org_member(mission["organization_id"], user, active_services)
        return mission, membership

    async def audit(
        action: str,
        actor_id: str | None,
        organization_id: str | None,
        mission_id: str | None,
        entity_type: str,
        entity_id: str,
        active_services: Services,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await active_services.store.insert(
            "audit_events",
            {
                "id": new_id(),
                "action": action,
                "actor_id": actor_id,
                "organization_id": organization_id,
                "mission_id": mission_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "metadata": metadata or {},
                "created_at": now_iso(),
            },
        )

    async def record_email(
        *,
        to: str,
        subject: str,
        html: str,
        kind: str,
        entity_id: str,
        active_services: Services,
    ) -> dict[str, Any]:
        result = await active_services.email.send(to, subject, html)
        attempt = {
            "id": new_id(),
            "to": to,
            "subject": subject,
            "kind": kind,
            "entity_id": entity_id,
            "status": "sent" if result.delivered else "failed",
            "provider_id": result.provider_id,
            "error": result.error,
            "created_at": now_iso(),
        }
        await active_services.store.insert("email_dispatches", attempt)
        return attempt

    async def invitation_from_token(token: str, active_services: Services) -> dict[str, Any]:
        invitations = await active_services.store.find("invitations", token_hash=token_hash(token))
        if not invitations:
            raise HTTPException(status_code=404, detail="Invitation not found")
        invitation = invitations[0]
        if invitation["expires_at"] <= now_iso():
            raise HTTPException(status_code=410, detail="Invitation has expired")
        return invitation

    async def invalidate_for_disruption(
        mission: dict[str, Any], actor_id: str, active_services: Services
    ) -> None:
        plans = await active_services.store.find("plans", mission_id=mission["id"])
        for plan in plans:
            if plan["status"] in {"feasible", "approved"}:
                plan["status"] = "stale"
                plan["stale_at"] = now_iso()
                await active_services.store.replace("plans", plan["id"], plan)
                approvals = await active_services.store.find("approvals", plan_id=plan["id"])
                for approval in approvals:
                    if approval["status"] == "active":
                        approval["status"] = "invalidated"
                        approval["invalidated_at"] = now_iso()
                        await active_services.store.replace("approvals", approval["id"], approval)
                        await audit(
                            "approval.invalidated",
                            actor_id,
                            mission["organization_id"],
                            mission["id"],
                            "approval",
                            approval["id"],
                            active_services,
                            {"plan_id": plan["id"]},
                        )

    async def compute_plan(mission_id: str, trigger: str, active_services: Services) -> dict[str, Any]:
        mission = await active_services.store.get("missions", mission_id)
        if not mission:
            raise RuntimeError(f"mission {mission_id} disappeared while optimizing")
        quotes = await active_services.store.find("quotes", mission_id=mission_id)
        existing = await active_services.store.find("plans", mission_id=mission_id)
        prior = max(existing, key=lambda plan: plan["version"]) if existing else None
        outcome = solve(mission, quotes)
        plan = {
            "id": new_id(),
            "mission_id": mission_id,
            "organization_id": mission["organization_id"],
            "version": max((plan["version"] for plan in existing), default=0) + 1,
            "trigger": trigger,
            "computed_at": now_iso(),
            **outcome,
        }
        previous_allocations = {
            (row["supplier_id"], row["item"]): row["quantity"] for row in prior["allocations"]
        } if prior else {}
        current_allocations = {
            (row["supplier_id"], row["item"]): row["quantity"] for row in plan["allocations"]
        }
        plan["difference"] = {
            "previous_plan_id": prior["id"] if prior else None,
            "total_cost_before": prior["total_cost"] if prior else None,
            "total_cost_after": plan["total_cost"],
            "allocation_changed": previous_allocations != current_allocations,
        }
        await active_services.store.insert("plans", plan)
        await audit(
            "plan.computed",
            None,
            mission["organization_id"],
            mission_id,
            "plan",
            plan["id"],
            active_services,
            {"version": plan["version"], "status": plan["status"], "trigger": trigger},
        )
        return plan

    async def run_replan_job(job_id: str) -> None:
        job = await services.store.get("jobs", job_id)
        if not job or job["status"] != "queued":
            return
        job["status"] = "running"
        job["started_at"] = now_iso()
        await services.store.replace("jobs", job_id, job)
        try:
            plan = await compute_plan(job["mission_id"], "supplier_disruption", services)
            job.update({"status": "succeeded", "plan_id": plan["id"], "finished_at": now_iso()})
            await services.store.replace("jobs", job_id, job)
            await services.store.insert(
                "notifications",
                {
                    "id": new_id(),
                    "organization_id": plan["organization_id"],
                    "mission_id": job["mission_id"],
                    "kind": "plan_replanned",
                    "message": f"Plan v{plan['version']} was computed after a supplier disruption.",
                    "created_at": now_iso(),
                },
            )
        except Exception as exc:  # keep a durable, visible failure record
            job.update({"status": "failed", "error": str(exc), "finished_at": now_iso()})
            await services.store.replace("jobs", job_id, job)

    async def queue_replan(mission: dict[str, Any], quote_id: str, active_services: Services) -> dict[str, Any]:
        job = {
            "id": new_id(),
            "type": "replan",
            "mission_id": mission["id"],
            "quote_id": quote_id,
            "status": "queued",
            "attempts": 0,
            "created_at": now_iso(),
        }
        await active_services.store.insert("jobs", job)
        active_services.schedule(run_replan_job(job["id"]))
        return job

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "storage": runtime_settings.storage_mode}

    @app.post("/v1/auth/register", status_code=status.HTTP_201_CREATED)
    async def register(
        payload: RegisterRequest,
        request: Request,
        active_services: Services = Depends(get_services),
    ) -> dict[str, Any]:
        active_services.rate_limiter.check(f"register:{request.client.host if request.client else 'unknown'}")
        email_address = str(payload.email).lower()
        if await active_services.store.find("users", email=email_address):
            raise HTTPException(status_code=409, detail="An account with this email already exists")
        user = {
            "id": new_id(),
            "email": email_address,
            "role": payload.role,
            "password_hash": hash_password(payload.password),
            "active": True,
            "created_at": now_iso(),
        }
        await active_services.store.insert("users", user)
        await audit("user.registered", user["id"], None, None, "user", user["id"], active_services)
        return {"access_token": create_access_token(user, active_services.settings), "token_type": "bearer", "user": public_user(user)}

    @app.post("/v1/auth/login")
    async def login(
        payload: LoginRequest,
        request: Request,
        active_services: Services = Depends(get_services),
    ) -> dict[str, Any]:
        active_services.rate_limiter.check(f"login:{request.client.host if request.client else 'unknown'}")
        users = await active_services.store.find("users", email=str(payload.email).lower())
        if not users or not verify_password(payload.password, users[0]["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        user = users[0]
        return {"access_token": create_access_token(user, active_services.settings), "token_type": "bearer", "user": public_user(user)}

    @app.get("/v1/me")
    async def me(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        return public_user(user)

    @app.post("/v1/organizations", status_code=status.HTTP_201_CREATED)
    async def create_organization(
        payload: CreateOrganizationRequest,
        user: dict[str, Any] = Depends(current_user),
        active_services: Services = Depends(get_services),
    ) -> dict[str, Any]:
        if user["role"] != "coordinator":
            raise HTTPException(status_code=403, detail="Only coordinators can create organizations")
        organization = {"id": new_id(), "name": payload.name.strip(), "created_at": now_iso()}
        await active_services.store.insert("organizations", organization)
        await active_services.store.insert(
            "memberships",
            {"id": new_id(), "organization_id": organization["id"], "user_id": user["id"], "role": "admin", "created_at": now_iso()},
        )
        await audit("organization.created", user["id"], organization["id"], None, "organization", organization["id"], active_services)
        return organization

    @app.get("/v1/organizations")
    async def list_organizations(
        user: dict[str, Any] = Depends(current_user), active_services: Services = Depends(get_services)
    ) -> list[dict[str, Any]]:
        memberships = await active_services.store.find("memberships", user_id=user["id"])
        organizations = []
        for membership in memberships:
            organization = await active_services.store.get("organizations", membership["organization_id"])
            if organization:
                organizations.append({**organization, "membership_role": membership["role"]})
        return organizations

    @app.post("/v1/missions", status_code=status.HTTP_201_CREATED)
    async def create_mission(
        payload: MissionCreateRequest,
        user: dict[str, Any] = Depends(current_user),
        active_services: Services = Depends(get_services),
    ) -> dict[str, Any]:
        if user["role"] != "coordinator":
            raise HTTPException(status_code=403, detail="Only coordinators can create missions")
        await require_org_member(payload.organization_id, user, active_services)
        if payload.delivery_deadline <= datetime.now(UTC):
            raise HTTPException(status_code=422, detail="Delivery deadline must be in the future")
        mission = {
            "id": new_id(),
            **payload.model_dump(mode="json"),
            "created_by": user["id"],
            "status": "open",
            "created_at": now_iso(),
        }
        await active_services.store.insert("missions", mission)
        await audit("mission.created", user["id"], mission["organization_id"], mission["id"], "mission", mission["id"], active_services)
        return mission

    @app.get("/v1/missions")
    async def list_missions(
        organization_id: str,
        user: dict[str, Any] = Depends(current_user),
        active_services: Services = Depends(get_services),
    ) -> list[dict[str, Any]]:
        await require_org_member(organization_id, user, active_services)
        return sorted(await active_services.store.find("missions", organization_id=organization_id), key=lambda row: row["created_at"], reverse=True)

    @app.get("/v1/missions/{mission_id}")
    async def get_mission(
        mission_id: str,
        user: dict[str, Any] = Depends(current_user),
        active_services: Services = Depends(get_services),
    ) -> dict[str, Any]:
        mission, _ = await require_mission_access(mission_id, user, active_services)
        return mission

    @app.post("/v1/missions/{mission_id}/invitations", status_code=status.HTTP_201_CREATED)
    async def create_invitation(
        mission_id: str,
        payload: InvitationCreateRequest,
        user: dict[str, Any] = Depends(current_user),
        active_services: Services = Depends(get_services),
    ) -> dict[str, Any]:
        mission, _ = await require_mission_access(mission_id, user, active_services)
        if user["role"] != "coordinator":
            raise HTTPException(status_code=403, detail="Only coordinators can send RFQs")
        raw_token = secrets.token_urlsafe(32)
        invitation = {
            "id": new_id(),
            "mission_id": mission_id,
            "organization_id": mission["organization_id"],
            "supplier_email": str(payload.supplier_email).lower(),
            "token_hash": token_hash(raw_token),
            "status": "sent",
            "expires_at": mission["delivery_deadline"],
            "created_by": user["id"],
            "created_at": now_iso(),
        }
        await active_services.store.insert("invitations", invitation)
        url = f"{active_services.settings.frontend_origin}/invitations/{raw_token}"
        attempt = await record_email(
            to=invitation["supplier_email"],
            subject=f"RFQ invitation: {mission['name']}",
            html=f"<p>You have been invited to quote for <strong>{mission['name']}</strong>.</p><p><a href=\"{url}\">Open secure RFQ</a></p>",
            kind="rfq_invitation",
            entity_id=invitation["id"],
            active_services=active_services,
        )
        invitation["delivery_status"] = attempt["status"]
        await active_services.store.replace("invitations", invitation["id"], invitation)
        await audit("rfq.invited", user["id"], mission["organization_id"], mission_id, "invitation", invitation["id"], active_services, {"delivery_status": attempt["status"]})
        response = {key: value for key, value in invitation.items() if key != "token_hash"}
        if active_services.settings.expose_invitation_links:
            response["token"] = raw_token
            response["invitation_url"] = url
        return response

    @app.get("/v1/supplier-invitations/{token}")
    async def get_invitation(token: str, active_services: Services = Depends(get_services)) -> dict[str, Any]:
        invitation = await invitation_from_token(token, active_services)
        mission = await active_services.store.get("missions", invitation["mission_id"])
        if not mission:
            raise HTTPException(status_code=404, detail="Mission not found")
        return {"mission": {key: mission[key] for key in ("id", "name", "delivery_location", "delivery_deadline", "requirements", "currency")}, "supplier_email": invitation["supplier_email"], "status": invitation["status"]}

    @app.post("/v1/supplier-invitations/{token}/accept")
    async def accept_invitation(
        token: str,
        user: dict[str, Any] = Depends(current_user),
        active_services: Services = Depends(get_services),
    ) -> dict[str, Any]:
        invitation = await invitation_from_token(token, active_services)
        if user["role"] != "supplier" or user["email"] != invitation["supplier_email"]:
            raise HTTPException(status_code=403, detail="This invitation belongs to a different supplier account")
        invitation["status"] = "accepted"
        invitation["accepted_by_user_id"] = user["id"]
        invitation["accepted_at"] = now_iso()
        await active_services.store.replace("invitations", invitation["id"], invitation)
        supplier = await active_services.store.get("suppliers", user["id"])
        if not supplier:
            supplier = {"id": user["id"], "user_id": user["id"], "email": user["email"], "created_at": now_iso()}
            await active_services.store.insert("suppliers", supplier)
        await audit("rfq.accepted", user["id"], invitation["organization_id"], invitation["mission_id"], "invitation", invitation["id"], active_services)
        return {"invitation_id": invitation["id"], "mission_id": invitation["mission_id"], "status": invitation["status"]}

    @app.post("/v1/quotes", status_code=status.HTTP_201_CREATED)
    async def submit_quote(
        payload: QuoteCreateRequest,
        user: dict[str, Any] = Depends(current_user),
        active_services: Services = Depends(get_services),
    ) -> dict[str, Any]:
        invitation = await invitation_from_token(payload.invitation_token, active_services)
        if user["role"] != "supplier" or invitation.get("accepted_by_user_id") != user["id"]:
            raise HTTPException(status_code=403, detail="Supplier invitation access denied")
        if payload.expires_at <= datetime.now(UTC):
            raise HTTPException(status_code=422, detail="Quote expiration must be in the future")
        existing = await active_services.store.find("quotes", invitation_id=invitation["id"])
        if existing:
            raise HTTPException(status_code=409, detail="Use the quote update endpoint to revise this submission")
        quote = {
            "id": new_id(),
            "mission_id": invitation["mission_id"],
            "organization_id": invitation["organization_id"],
            "invitation_id": invitation["id"],
            "supplier_id": user["id"],
            "supplier_email": user["email"],
            "status": "submitted",
            "version": 1,
            **payload.model_dump(mode="json", exclude={"invitation_token"}),
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        await active_services.store.insert("quotes", quote)
        await audit("quote.submitted", user["id"], quote["organization_id"], quote["mission_id"], "quote", quote["id"], active_services)
        return quote

    @app.get("/v1/supplier/invitations")
    async def list_supplier_invitations(
        user: dict[str, Any] = Depends(current_user), active_services: Services = Depends(get_services)
    ) -> list[dict[str, Any]]:
        if user["role"] != "supplier":
            raise HTTPException(status_code=403, detail="Supplier access required")
        invitations = await active_services.store.find("invitations", supplier_email=user["email"])
        results = []
        for invitation in invitations:
            mission = await active_services.store.get("missions", invitation["mission_id"])
            if mission:
                results.append({key: value for key, value in invitation.items() if key != "token_hash"} | {"mission": {key: mission[key] for key in ("id", "name", "delivery_location", "delivery_deadline", "requirements", "currency")}})
        return sorted(results, key=lambda row: row["created_at"], reverse=True)

    @app.get("/v1/supplier/quotes")
    async def list_supplier_quotes(
        user: dict[str, Any] = Depends(current_user), active_services: Services = Depends(get_services)
    ) -> list[dict[str, Any]]:
        if user["role"] != "supplier":
            raise HTTPException(status_code=403, detail="Supplier access required")
        return sorted(await active_services.store.find("quotes", supplier_id=user["id"]), key=lambda row: row["updated_at"], reverse=True)

    async def quote_access(quote_id: str, user: dict[str, Any], active_services: Services) -> dict[str, Any]:
        quote = await active_services.store.get("quotes", quote_id)
        if not quote:
            raise HTTPException(status_code=404, detail="Quote not found")
        if user["role"] == "supplier":
            if quote["supplier_id"] != user["id"]:
                raise HTTPException(status_code=403, detail="Supplier quotes are private")
        else:
            await require_org_member(quote["organization_id"], user, active_services)
        return quote

    @app.get("/v1/quotes/{quote_id}")
    async def get_quote(
        quote_id: str, user: dict[str, Any] = Depends(current_user), active_services: Services = Depends(get_services)
    ) -> dict[str, Any]:
        return await quote_access(quote_id, user, active_services)

    @app.put("/v1/quotes/{quote_id}")
    async def update_quote(
        quote_id: str,
        payload: QuoteUpdateRequest,
        user: dict[str, Any] = Depends(current_user),
        active_services: Services = Depends(get_services),
    ) -> dict[str, Any]:
        quote = await quote_access(quote_id, user, active_services)
        if user["role"] != "supplier" or quote["status"] != "submitted":
            raise HTTPException(status_code=409, detail="Only active supplier quotes can be updated")
        await active_services.store.insert("quote_versions", {"id": new_id(), "quote_id": quote_id, "version": quote["version"], "snapshot": quote, "created_at": now_iso()})
        quote.update(payload.model_dump(mode="json"))
        quote["version"] += 1
        quote["updated_at"] = now_iso()
        await active_services.store.replace("quotes", quote_id, quote)
        mission = await active_services.store.get("missions", quote["mission_id"])
        assert mission
        await invalidate_for_disruption(mission, user["id"], active_services)
        job = await queue_replan(mission, quote_id, active_services)
        await audit("quote.updated", user["id"], quote["organization_id"], quote["mission_id"], "quote", quote_id, active_services, {"job_id": job["id"]})
        return {**quote, "replan_job_id": job["id"]}

    @app.post("/v1/quotes/{quote_id}/withdraw", status_code=status.HTTP_202_ACCEPTED)
    async def withdraw_quote(
        quote_id: str,
        user: dict[str, Any] = Depends(current_user),
        active_services: Services = Depends(get_services),
    ) -> dict[str, Any]:
        quote = await quote_access(quote_id, user, active_services)
        if user["role"] != "supplier":
            raise HTTPException(status_code=403, detail="Only a supplier can withdraw its quote")
        if quote["status"] == "withdrawn":
            return {"quote_id": quote_id, "status": "withdrawn"}
        quote["status"] = "withdrawn"
        quote["withdrawn_at"] = now_iso()
        await active_services.store.replace("quotes", quote_id, quote)
        mission = await active_services.store.get("missions", quote["mission_id"])
        assert mission
        await invalidate_for_disruption(mission, user["id"], active_services)
        job = await queue_replan(mission, quote_id, active_services)
        await audit("quote.withdrawn", user["id"], quote["organization_id"], quote["mission_id"], "quote", quote_id, active_services, {"job_id": job["id"]})
        return {"quote_id": quote_id, "status": "withdrawn", "replan_job_id": job["id"]}

    @app.get("/v1/missions/{mission_id}/quotes")
    async def list_quotes(
        mission_id: str,
        user: dict[str, Any] = Depends(current_user),
        active_services: Services = Depends(get_services),
    ) -> list[dict[str, Any]]:
        _, membership = await require_mission_access(mission_id, user, active_services)
        if user["role"] != "coordinator" or membership["role"] not in {"admin", "coordinator"}:
            raise HTTPException(status_code=403, detail="Only procurement coordinators can review quotes")
        return sorted(await active_services.store.find("quotes", mission_id=mission_id), key=lambda row: row["created_at"], reverse=True)

    @app.post("/v1/missions/{mission_id}/optimize", status_code=status.HTTP_202_ACCEPTED)
    async def optimize_mission(
        mission_id: str,
        user: dict[str, Any] = Depends(current_user),
        active_services: Services = Depends(get_services),
    ) -> dict[str, Any]:
        mission, _ = await require_mission_access(mission_id, user, active_services)
        if user["role"] != "coordinator":
            raise HTTPException(status_code=403, detail="Only coordinators can run the optimizer")
        plan = await compute_plan(mission["id"], "manual", active_services)
        return {"plan_id": plan["id"], "status": plan["status"]}

    @app.get("/v1/plans/{plan_id}")
    async def get_plan(
        plan_id: str, user: dict[str, Any] = Depends(current_user), active_services: Services = Depends(get_services)
    ) -> dict[str, Any]:
        plan = await active_services.store.get("plans", plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        await require_org_member(plan["organization_id"], user, active_services)
        return plan

    @app.get("/v1/missions/{mission_id}/plans")
    async def list_plans(
        mission_id: str,
        user: dict[str, Any] = Depends(current_user),
        active_services: Services = Depends(get_services),
    ) -> list[dict[str, Any]]:
        await require_mission_access(mission_id, user, active_services)
        return sorted(await active_services.store.find("plans", mission_id=mission_id), key=lambda row: row["version"], reverse=True)

    @app.post("/v1/plans/{plan_id}/approve", status_code=status.HTTP_201_CREATED)
    async def approve_plan(
        plan_id: str,
        user: dict[str, Any] = Depends(current_user),
        active_services: Services = Depends(get_services),
    ) -> dict[str, Any]:
        plan = await active_services.store.get("plans", plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        membership = await require_org_member(plan["organization_id"], user, active_services)
        if user["role"] != "coordinator" or membership["role"] != "admin":
            raise HTTPException(status_code=403, detail="An organization administrator must approve this plan")
        if plan["status"] != "feasible":
            raise HTTPException(status_code=409, detail="Only a current feasible plan can be approved")
        approval = {"id": new_id(), "plan_id": plan_id, "mission_id": plan["mission_id"], "organization_id": plan["organization_id"], "amount": plan["total_cost"], "approver_id": user["id"], "status": "active", "approved_at": now_iso(), "expires_at": None}
        await active_services.store.insert("approvals", approval)
        plan["status"] = "approved"
        await active_services.store.replace("plans", plan_id, plan)
        await audit("plan.approved", user["id"], plan["organization_id"], plan["mission_id"], "approval", approval["id"], active_services, {"plan_id": plan_id, "amount": plan["total_cost"]})
        return approval

    @app.get("/v1/missions/{mission_id}/approvals")
    async def list_approvals(
        mission_id: str,
        user: dict[str, Any] = Depends(current_user),
        active_services: Services = Depends(get_services),
    ) -> list[dict[str, Any]]:
        await require_mission_access(mission_id, user, active_services)
        return sorted(await active_services.store.find("approvals", mission_id=mission_id), key=lambda row: row["approved_at"], reverse=True)

    @app.post("/v1/plans/{plan_id}/purchase-orders", status_code=status.HTTP_201_CREATED)
    async def create_purchase_orders(
        plan_id: str,
        request: Request,
        user: dict[str, Any] = Depends(current_user),
        active_services: Services = Depends(get_services),
    ) -> list[dict[str, Any]]:
        key = request.headers.get("Idempotency-Key")
        if not key or len(key) > 128:
            raise HTTPException(status_code=400, detail="An Idempotency-Key header is required")
        plan = await active_services.store.get("plans", plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        await require_org_member(plan["organization_id"], user, active_services)
        if user["role"] != "coordinator" or plan["status"] != "approved":
            raise HTTPException(status_code=409, detail="An approved current plan is required")
        existing = await active_services.store.find("purchase_orders", plan_id=plan_id, idempotency_key=key)
        if existing:
            return existing
        approvals = await active_services.store.find("approvals", plan_id=plan_id, status="active")
        if not approvals:
            raise HTTPException(status_code=409, detail="No active approval exists for this exact plan")
        mission = await active_services.store.get("missions", plan["mission_id"])
        assert mission
        organization = await active_services.store.get("organizations", plan["organization_id"])
        assert organization
        by_supplier: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for allocation in plan["allocations"]:
            by_supplier[allocation["supplier_id"]].append(allocation)
        orders = []
        for supplier_id, allocations in by_supplier.items():
            order = {
                "id": new_id(),
                "po_number": f"RM-{datetime.now(UTC):%Y%m%d}-{new_id()[:8].upper()}",
                "plan_id": plan_id,
                "mission_id": plan["mission_id"],
                "organization_id": plan["organization_id"],
                "supplier_id": supplier_id,
                "supplier_email": allocations[0]["supplier_email"],
                "buyer_organization": organization["name"],
                "delivery_location": mission["delivery_location"],
                "approval_id": approvals[0]["id"],
                "lines": allocations,
                "status": "draft",
                "idempotency_key": key,
                "created_at": now_iso(),
                "events": [{"status": "draft", "at": now_iso(), "actor_id": user["id"]}],
            }
            await active_services.store.insert("purchase_orders", order)
            orders.append(order)
            await audit("purchase_order.created", user["id"], plan["organization_id"], plan["mission_id"], "purchase_order", order["id"], active_services)
        return orders

    async def purchase_order_access(order_id: str, user: dict[str, Any], active_services: Services) -> dict[str, Any]:
        order = await active_services.store.get("purchase_orders", order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Purchase order not found")
        if user["role"] == "supplier":
            if order["supplier_id"] != user["id"]:
                raise HTTPException(status_code=403, detail="Supplier purchase orders are private")
        else:
            await require_org_member(order["organization_id"], user, active_services)
        return order

    @app.get("/v1/purchase-orders")
    async def list_purchase_orders(
        organization_id: str | None = None,
        user: dict[str, Any] = Depends(current_user),
        active_services: Services = Depends(get_services),
    ) -> list[dict[str, Any]]:
        if user["role"] == "supplier":
            return await active_services.store.find("purchase_orders", supplier_id=user["id"])
        if not organization_id:
            raise HTTPException(status_code=422, detail="organization_id is required for coordinators")
        await require_org_member(organization_id, user, active_services)
        return await active_services.store.find("purchase_orders", organization_id=organization_id)

    @app.post("/v1/purchase-orders/{order_id}/send")
    async def send_purchase_order(
        order_id: str,
        payload: PurchaseOrderSendRequest,
        user: dict[str, Any] = Depends(current_user),
        active_services: Services = Depends(get_services),
    ) -> dict[str, Any]:
        order = await purchase_order_access(order_id, user, active_services)
        if user["role"] != "coordinator":
            raise HTTPException(status_code=403, detail="Only a coordinator can send a purchase order")
        if order["status"] != "draft":
            raise HTTPException(status_code=409, detail="Only draft purchase orders can be sent")
        attempt = await record_email(
            to=order["supplier_email"],
            subject=f"Purchase order {order['po_number']}",
            html=f"<p>Purchase order {order['po_number']} is ready for your acceptance.</p>",
            kind="purchase_order",
            entity_id=order_id,
            active_services=active_services,
        )
        if not attempt["status"] == "sent":
            order["send_error"] = attempt["error"]
            await active_services.store.replace("purchase_orders", order_id, order)
            raise HTTPException(status_code=502, detail="Purchase order email was not delivered; the failure was recorded")
        order["status"] = "sent"
        order["sent_at"] = now_iso()
        order["events"].append({"status": "sent", "at": now_iso(), "actor_id": user["id"]})
        await active_services.store.replace("purchase_orders", order_id, order)
        await audit("purchase_order.sent", user["id"], order["organization_id"], order["mission_id"], "purchase_order", order_id, active_services)
        return order

    @app.post("/v1/purchase-orders/{order_id}/supplier-response")
    async def supplier_response(
        order_id: str,
        payload: SupplierResponseRequest,
        user: dict[str, Any] = Depends(current_user),
        active_services: Services = Depends(get_services),
    ) -> dict[str, Any]:
        order = await purchase_order_access(order_id, user, active_services)
        if user["role"] != "supplier" or order["status"] != "sent":
            raise HTTPException(status_code=409, detail="Only a sent supplier order can be answered")
        order["status"] = "supplier_accepted" if payload.accepted else "supplier_declined"
        order["supplier_response_at"] = now_iso()
        order["supplier_response_reason"] = payload.reason
        order["events"].append({"status": order["status"], "at": now_iso(), "actor_id": user["id"]})
        await active_services.store.replace("purchase_orders", order_id, order)
        await audit("purchase_order.supplier_response", user["id"], order["organization_id"], order["mission_id"], "purchase_order", order_id, active_services, {"accepted": payload.accepted})
        return order

    @app.post("/v1/purchase-orders/{order_id}/fulfillment")
    async def update_fulfillment(
        order_id: str,
        payload: FulfillmentUpdateRequest,
        user: dict[str, Any] = Depends(current_user),
        active_services: Services = Depends(get_services),
    ) -> dict[str, Any]:
        order = await purchase_order_access(order_id, user, active_services)
        if user["role"] != "supplier" or order["status"] not in {"supplier_accepted", "in_fulfillment"}:
            raise HTTPException(status_code=409, detail="Only an accepted supplier order can receive fulfillment updates")
        order["status"] = payload.status
        order["events"].append({"status": payload.status, "note": payload.note, "at": now_iso(), "actor_id": user["id"]})
        await active_services.store.replace("purchase_orders", order_id, order)
        await active_services.store.insert("fulfillment_events", {"id": new_id(), "purchase_order_id": order_id, "status": payload.status, "note": payload.note, "actor_id": user["id"], "created_at": now_iso()})
        await audit("fulfillment.updated", user["id"], order["organization_id"], order["mission_id"], "purchase_order", order_id, active_services, {"status": payload.status})
        return order

    @app.get("/v1/purchase-orders/{order_id}/pdf")
    async def purchase_order_pdf(
        order_id: str, user: dict[str, Any] = Depends(current_user), active_services: Services = Depends(get_services)
    ) -> Response:
        order = await purchase_order_access(order_id, user, active_services)
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
        pdf.save()
        buffer.seek(0)
        return StreamingResponse(buffer, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{order["po_number"]}.pdf"'})

    @app.get("/v1/missions/{mission_id}/audit")
    async def mission_audit(
        mission_id: str,
        user: dict[str, Any] = Depends(current_user),
        active_services: Services = Depends(get_services),
    ) -> list[dict[str, Any]]:
        await require_mission_access(mission_id, user, active_services)
        return sorted(await active_services.store.find("audit_events", mission_id=mission_id), key=lambda row: row["created_at"])

    @app.get("/v1/missions/{mission_id}/email-dispatches")
    async def mission_email_dispatches(
        mission_id: str,
        user: dict[str, Any] = Depends(current_user),
        active_services: Services = Depends(get_services),
    ) -> list[dict[str, Any]]:
        _, membership = await require_mission_access(mission_id, user, active_services)
        if user["role"] != "coordinator" or membership["role"] not in {"admin", "coordinator"}:
            raise HTTPException(status_code=403, detail="Only coordinators can review email delivery")
        invitations = await active_services.store.find("invitations", mission_id=mission_id)
        attempts = []
        for invitation in invitations:
            attempts.extend(await active_services.store.find("email_dispatches", entity_id=invitation["id"]))
        return sorted(attempts, key=lambda row: row["created_at"], reverse=True)

    @app.get("/v1/jobs/{job_id}")
    async def get_job(
        job_id: str, user: dict[str, Any] = Depends(current_user), active_services: Services = Depends(get_services)
    ) -> dict[str, Any]:
        job = await active_services.store.get("jobs", job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        await require_mission_access(job["mission_id"], user, active_services)
        return job

    @app.get("/v1/emergency-events")
    async def emergency_events() -> list[dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get("https://eonet.gsfc.nasa.gov/api/v3/events?status=open&limit=30")
            response.raise_for_status()
            return [{"id": row["id"], "title": row["title"], "categories": row.get("categories", [])} for row in response.json().get("events", [])]
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"NASA EONET is unavailable: {exc}") from exc

    return app


app = create_app()
