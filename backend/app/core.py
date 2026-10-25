"""Shared services, authentication dependencies, audit chaining, and notifications."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any, Awaitable, Callable
from uuid import uuid4

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .auth import decode_access_token
from .emailing import EmailGateway
from .integrations.http import IntegrationHub, canonical_json
from .settings import Settings
from .store import Store

bearer = HTTPBearer(auto_error=False)
AGENT_TOKEN_PREFIX = "rm_agent_"
GENESIS_HASH = "0" * 64


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def new_id() -> str:
    return str(uuid4())


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in user.items() if key not in {"password_hash"}}


class RateLimiter:
    def __init__(self, per_minute: int, message: str = "Too many authentication attempts") -> None:
        self.per_minute = per_minute
        self.message = message
        self.events: dict[str, list[float]] = defaultdict(list)

    def check(self, client_key: str) -> None:
        loop_time = asyncio.get_running_loop().time()
        events = [time for time in self.events[client_key] if loop_time - time < 60]
        if len(events) >= self.per_minute:
            raise HTTPException(status_code=429, detail=self.message)
        events.append(loop_time)
        self.events[client_key] = events


class Services:
    def __init__(self, settings: Settings, store: Store, email: EmailGateway, hub: IntegrationHub) -> None:
        self.settings = settings
        self.store = store
        self.email = email
        self.hub = hub
        self.rate_limiter = RateLimiter(settings.auth_rate_limit_per_minute)
        self.assist_limiter = RateLimiter(settings.quote_draft_per_minute, "Too many quote drafts; try again in a minute")
        self.jobs: set[asyncio.Task] = set()
        self.audit_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.telegram_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.sms_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.job_handlers: dict[str, Callable[[Services, dict[str, Any]], Awaitable[dict[str, Any]]]] = {}
        self.status_cache: dict[str, Any] = {}
        # Operations integrations (Gmail/Calendar/Slack/Drive); wired in main.create_app.
        self.vault: Any = None
        self.ops: Any = None
        # Continuity Engine: MILP stress tests run in worker threads, a bounded number at a time per process,
        # identical (plan, input-hash) runs are shared, and progress is readable while a run is in flight.
        self.continuity_slots = asyncio.Semaphore(settings.continuity_max_concurrent)
        self.continuity_inflight: dict[tuple[str, str], asyncio.Future] = {}
        self.continuity_progress: dict[str, dict[str, Any]] = {}

    def schedule(self, coroutine: Any, delay: float = 0.0) -> None:
        async def runner() -> None:
            if delay:
                await asyncio.sleep(delay)
            await coroutine

        task = asyncio.create_task(runner())
        self.jobs.add(task)
        task.add_done_callback(self.jobs.discard)


def get_services(request: Request) -> Services:
    return request.app.state.services


async def current_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    services: Services = Depends(get_services),
) -> dict[str, Any]:
    """Resolve a user JWT or a scoped organization agent token."""

    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication is required")
    raw = credentials.credentials
    if raw.startswith(AGENT_TOKEN_PREFIX):
        tokens = await services.store.find("agent_tokens", token_hash=token_hash(raw))
        if not tokens or tokens[0].get("revoked_at"):
            raise HTTPException(status_code=401, detail="Agent token is invalid or revoked")
        token = tokens[0]
        return {
            "id": f"agent:{token['id']}",
            "role": "agent",
            "email": None,
            "name": token["name"],
            "organization_id": token["organization_id"],
            "scopes": token["scopes"],
            "created_by": token["created_by"],
            # The agent runtime (the token holder) identifies which chat user it is acting for,
            # so missions stay isolated between ASI:One users sharing one organization token.
            "sender": (request.headers.get("X-Agent-Sender") or "")[:120] or None,
            "active": True,
        }
    claims = decode_access_token(raw, services.settings)
    user = await services.store.get("users", claims["sub"])
    if not user or not user.get("active", False):
        raise HTTPException(status_code=401, detail="Session user is unavailable")
    return user


async def current_user(principal: dict[str, Any] = Depends(current_principal)) -> dict[str, Any]:
    """Human users only. Agent tokens can never reach approval, PO, or spending endpoints."""

    if principal["role"] == "agent":
        raise HTTPException(status_code=403, detail="Agent tokens cannot perform this action")
    return principal


async def require_org_member(organization_id: str, user: dict[str, Any], services: Services) -> dict[str, Any]:
    if user.get("role") == "agent":
        if user["organization_id"] != organization_id:
            raise HTTPException(status_code=403, detail="Organization access denied")
        return {"organization_id": organization_id, "user_id": user["id"], "role": "agent"}
    memberships = await services.store.find("memberships", organization_id=organization_id, user_id=user["id"])
    if not memberships:
        raise HTTPException(status_code=403, detail="Organization access denied")
    return memberships[0]


async def require_mission_access(
    mission_id: str, user: dict[str, Any], services: Services
) -> tuple[dict[str, Any], dict[str, Any]]:
    mission = await services.store.get("missions", mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    membership = await require_org_member(mission["organization_id"], user, services)
    if user.get("role") == "agent" and mission.get("agent_sender") != user.get("sender"):
        raise HTTPException(status_code=403, detail="This mission belongs to a different agent conversation")
    return mission, membership


async def require_admin(mission: dict[str, Any], user: dict[str, Any], services: Services) -> dict[str, Any]:
    membership = await require_org_member(mission["organization_id"], user, services)
    if user.get("role") != "coordinator" or membership["role"] != "admin":
        raise HTTPException(status_code=403, detail="An organization administrator is required")
    return membership


# ----- tamper-evident audit chain -----
HASHED_FIELDS = ("sequence", "previous_hash", "chain_key", "action", "actor_id", "organization_id", "mission_id",
                 "entity_type", "entity_id", "metadata", "created_at")


def event_digest(event: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json({key: event.get(key) for key in HASHED_FIELDS}).encode()).hexdigest()


def head_mac(secret_key: str, chain_key: str, sequence: int, event_hash: str) -> str:
    """HMAC over the chain head with a server-side secret that is never stored in the database, so someone who
    can write the database cannot rewrite the head to hide removed events."""
    message = f"reliefmesh-audit-head:{chain_key}:{sequence}:{event_hash}".encode()
    return hmac.new(hashlib.sha256(f"audit-head:{secret_key}".encode()).digest(), message, hashlib.sha256).hexdigest()


def audit_head_key(services: Services) -> str:
    return services.settings.jwt_secret.get_secret_value()


async def audit(
    action: str,
    actor_id: str | None,
    organization_id: str | None,
    mission_id: str | None,
    entity_type: str,
    entity_id: str,
    services: Services,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append a hash-chained audit event. Each chain (per mission, else per org) is serialized."""

    chain_key = f"mission:{mission_id}" if mission_id else f"org:{organization_id}" if organization_id else "global"
    async with services.audit_locks[chain_key]:
        head = await services.store.get("audit_chain_heads", chain_key)
        event = {
            "id": new_id(),
            "chain_key": chain_key,
            "sequence": (head["sequence"] + 1) if head else 1,
            "previous_hash": head["event_hash"] if head else GENESIS_HASH,
            "action": action,
            "actor_id": actor_id,
            "organization_id": organization_id,
            "mission_id": mission_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "metadata": metadata or {},
            "created_at": now_iso(),
        }
        event["event_hash"] = event_digest(event)
        await services.store.insert("audit_events", event)
        await services.store.upsert("audit_chain_heads", {
            "id": chain_key, "sequence": event["sequence"], "event_hash": event["event_hash"],
            "mac": head_mac(audit_head_key(services), chain_key, event["sequence"], event["event_hash"]),
        })
        return event


def verify_chain(events: list[dict[str, Any]], head: dict[str, Any] | None = None, *,
                 secret_key: str | None = None) -> dict[str, Any]:
    """Recompute the hash chain. With ``secret_key`` the signed chain head is required too, which detects events
    removed from the end, a deleted head, and a head rewritten without the server-side key."""
    ordered = sorted(events, key=lambda row: row.get("sequence", 0))
    previous = GENESIS_HASH
    for expected_sequence, event in enumerate(ordered, start=1):
        if event.get("sequence") != expected_sequence:
            return {"valid": False, "length": len(ordered), "broken_at": expected_sequence,
                    "reason": "sequence gap or reordering"}
        if event.get("previous_hash") != previous:
            return {"valid": False, "length": len(ordered), "broken_at": expected_sequence,
                    "reason": "previous_hash does not link to the prior event"}
        if event_digest(event) != event.get("event_hash"):
            return {"valid": False, "length": len(ordered), "broken_at": expected_sequence,
                    "reason": "event contents do not match their hash"}
        previous = event["event_hash"]
    if secret_key is not None and ordered:
        failure = None
        if head is None:
            failure = "chain head record is missing: it was deleted or never written"
        elif head.get("sequence") != len(ordered) or head.get("event_hash") != previous:
            failure = "chain head does not match: events were removed or replaced at the end"
        elif not hmac.compare_digest(str(head.get("mac") or ""),
                                     head_mac(secret_key, head["id"], head["sequence"], head["event_hash"])):
            failure = "chain head signature is invalid: the head was rewritten outside ReliefMesh"
        if failure:
            return {"valid": False, "length": len(ordered), "broken_at": len(ordered) + 1, "reason": failure}
    return {"valid": True, "length": len(ordered), "head_hash": previous, "broken_at": None, "reason": None}


async def notify(services: Services, mission: dict[str, Any], kind: str, message: str,
                 severity: str = "info", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    notification = {
        "id": new_id(),
        "organization_id": mission["organization_id"],
        "mission_id": mission["id"],
        "kind": kind,
        "severity": severity,
        "message": message,
        "metadata": metadata or {},
        "created_at": now_iso(),
    }
    await services.store.insert("notifications", notification)
    return notification


async def record_email(*, to: str, subject: str, html: str, kind: str, entity_id: str,
                       services: Services, organization_id: str | None = None, text: str | None = None,
                       attachments: tuple = ()) -> dict[str, Any]:
    """Send a transactional email (RFQ, PO, org invite) via the org's Gmail or Resend and record it."""

    from .integrations.gmail import OutgoingEmail

    result = await services.email.send(
        OutgoingEmail(to=to, subject=subject, html=html, text=text, attachments=attachments,
                      headers={"X-ReliefMesh-Event": kind}), organization_id)
    attempt = {
        "id": new_id(),
        "to": to,
        "subject": subject,
        "kind": kind,
        "entity_id": entity_id,
        "organization_id": organization_id,
        # sent | failed | not_configured | test (EMAIL_MODE=test) | disabled | suppressed
        "status": result.status,
        "provider": result.provider,
        "provider_id": result.provider_id,
        "message_id": result.provider_id,
        "thread_id": result.thread_id,
        "sender": result.sender,
        "attachments": [a.filename for a in attachments],
        "error": result.error,
        "sent_at": now_iso() if result.delivered else None,
        "created_at": now_iso(),
    }
    await services.store.insert("email_dispatches", attempt)
    return attempt


async def invitation_from_token(token: str, services: Services) -> dict[str, Any]:
    invitations = await services.store.find("invitations", token_hash=token_hash(token))
    if not invitations:
        raise HTTPException(status_code=404, detail="Invitation not found")
    invitation = invitations[0]
    if invitation["expires_at"] <= now_iso():
        raise HTTPException(status_code=410, detail="Invitation has expired")
    return invitation


def secret(value: Any) -> str | None:
    if value is None:
        return None
    return value.get_secret_value() if hasattr(value, "get_secret_value") else str(value)
