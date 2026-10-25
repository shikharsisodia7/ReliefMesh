"""Organization operations integrations: Google (Gmail, Calendar, Drive) and Slack.

Connections are made by an organization administrator through each provider's own OAuth
consent screen (or, for Slack, a bot token / webhook the admin pastes). A connection shows
CONNECTED only after the provider returned credentials, and a capability shows LIVE only
after a real call with those credentials succeeded.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from ..core import Services, audit, current_user, get_services, new_id, now_iso, require_org_member
from ..emailing import recipient_allowed
from ..integrations import connections, google_auth, google_calendar, google_drive, slack
from ..integrations.connections import IntegrationError
from ..integrations.gmail import OutgoingEmail
from . import status as status_routes

router = APIRouter()
STATE_TTL = timedelta(minutes=15)
CAPABILITY_CHANNEL = {"gmail": "gmail", "calendar": "calendar", "drive": "drive"}


class SlackManualConfig(BaseModel):
    bot_token: str | None = Field(default=None, max_length=300)
    channel: str | None = Field(default=None, max_length=120)
    webhook_url: str | None = Field(default=None, max_length=500)


class IntegrationTestRequest(BaseModel):
    channel: Literal["gmail", "calendar", "drive", "slack"]


async def require_org_admin(organization_id: str, user: dict[str, Any], services: Services) -> dict[str, Any]:
    membership = await require_org_member(organization_id, user, services)
    if user.get("role") != "coordinator" or membership["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only an organization administrator can manage integrations")
    return membership


def settings_url(services: Services, organization_id: str, **params: str) -> str:
    query = urlencode({"org": organization_id, **params})
    return f"{services.settings.frontend_origin.rstrip('/')}/settings/integrations?{query}"


async def new_state(services: Services, provider: str, organization_id: str, user: dict[str, Any],
                    verifier: str | None = None) -> str:
    state = secrets.token_urlsafe(32)
    await services.store.insert("oauth_states", {
        "id": state, "provider": provider, "organization_id": organization_id, "user_id": user["id"],
        "code_verifier": verifier, "expires_at": (datetime.now(UTC) + STATE_TTL).isoformat(),
        "used_at": None, "created_at": now_iso()})
    return state


async def consume_state(services: Services, provider: str, state: str | None) -> dict[str, Any]:
    record = await services.store.get("oauth_states", state) if state else None
    if not record or record["provider"] != provider:
        raise HTTPException(status_code=400, detail="Unknown OAuth state; start the connection again")
    if record.get("used_at"):
        raise HTTPException(status_code=400, detail="This OAuth response was already used")
    if record["expires_at"] <= now_iso():
        raise HTTPException(status_code=400, detail="The OAuth request expired; start the connection again")
    record["used_at"] = now_iso()
    await services.store.replace("oauth_states", record["id"], record)
    return record


# ------------------------------------------------------------------ view
async def last_delivery(services: Services, organization_id: str, channel: str) -> dict[str, Any] | None:
    rows = [row for row in await services.store.find("ops_deliveries", organization_id=organization_id,
                                                      channel=channel)
            if row["status"] in {"SENT", "FAILED", "RETRYING"}]
    if channel == "gmail":
        rows += [{"status": "SENT" if row["status"] == "sent" else "FAILED", "updated_at": row["created_at"],
                  "last_error": row.get("error")}
                 for row in await services.store.find("email_dispatches", organization_id=organization_id,
                                                      provider="gmail")]
    return max(rows, key=lambda row: row["updated_at"]) if rows else None


def capability_state(connection: dict[str, Any] | None, capability: str, oauth_ready: bool,
                     last: dict[str, Any] | None) -> dict[str, Any]:
    if not oauth_ready:
        return {"state": "NOT_CONFIGURED", "detail": "The server has no OAuth app credentials for this provider"}
    if not connection or connection.get("status") == "disconnected":
        return {"state": "NOT_CONFIGURED", "detail": "Not connected"}
    if connection.get("status") == "needs_reauth":
        return {"state": "BLOCKED", "detail": connection.get("last_error") or "Reconnect required"}
    if capability != "slack" and not (connection.get("capabilities") or {}).get(capability):
        return {"state": "NOT_CONFIGURED", "detail": "Permission not granted on the consent screen"}
    success = (connection.get("last_success") or {}).get(capability)
    if last and last["status"] in {"FAILED", "RETRYING"} and (not success or last["updated_at"] > success):
        return {"state": "DEGRADED", "detail": f"Last delivery {last['status'].lower()}: {last.get('last_error')}",
                "last_success": success}
    if success:
        return {"state": "LIVE", "detail": "Last real call succeeded", "last_success": success}
    return {"state": "DEGRADED", "detail": "Connected; no successful call yet (use Send test)"}


def public_delivery(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("payload") or {}
    return {key: row.get(key) for key in (
        "id", "event_type", "mission_id", "subject_id", "version", "channel", "target", "summary", "status",
        "attempts", "max_attempts", "provider", "provider_id", "provider_url", "last_error", "next_retry_at",
        "sent_at", "created_at", "updated_at", "history")} | {
        "subject": payload.get("subject"), "operation": payload.get("op")}


@router.get("/v1/organizations/{organization_id}/integrations")
async def organization_integrations(organization_id: str, user: dict = Depends(current_user),
                                    services: Services = Depends(get_services)) -> dict:
    membership = await require_org_member(organization_id, user, services)
    settings = services.settings
    google = await connections.load(services.store, organization_id, "google")
    slack_connection = await connections.load(services.store, organization_id, "slack")
    google_ready = google_auth.configured(settings)
    google_view = {
        "oauth_configured": google_ready,
        "status": "NOT_CONFIGURED" if not google_ready else (google or {}).get("status", "not_connected").upper(),
        "account_email": (google or {}).get("account_email"),
        "connected_at": (google or {}).get("connected_at"),
        "granted_scopes": (google or {}).get("granted_scopes", []),
        "calendar_id": (google or {}).get("calendar_id"),
        "capabilities": {cap: capability_state(google, cap, google_ready,
                                               await last_delivery(services, organization_id, channel))
                         for cap, channel in CAPABILITY_CHANNEL.items()},
    }
    slack_ready = True  # manual bot token / webhook needs no server OAuth app
    slack_view = {
        "oauth_configured": slack.oauth_configured(settings),
        "status": (slack_connection or {}).get("status", "not_connected").upper(),
        "mode": (slack_connection or {}).get("mode"),
        "team_name": (slack_connection or {}).get("team_name"),
        "channel_name": (slack_connection or {}).get("channel_name"),
        "connected_at": (slack_connection or {}).get("connected_at"),
        **capability_state(slack_connection, "slack", slack_ready,
                           await last_delivery(services, organization_id, "slack")),
    }
    transport = "gmail" if google_view["capabilities"]["gmail"]["state"] in {"LIVE", "DEGRADED"} else (
        "resend" if settings.resend_api_key else "none")
    deliveries = sorted(await services.store.find("ops_deliveries", organization_id=organization_id),
                        key=lambda row: row["created_at"], reverse=True)[:60]
    return {
        "organization_id": organization_id, "membership_role": membership["role"],
        "email": {"mode": settings.resolved_email_mode, "transport": transport,
                  "allowlist_active": bool(settings.email_allowed_recipients)},
        "google": google_view, "slack": slack_view,
        "deliveries": [public_delivery(row) for row in deliveries],
    }


@router.get("/v1/missions/{mission_id}/operations")
async def mission_operations(mission_id: str, user: dict = Depends(current_user),
                             services: Services = Depends(get_services)) -> list:
    from ..core import require_mission_access

    await require_mission_access(mission_id, user, services)
    rows = await services.store.find("ops_deliveries", mission_id=mission_id)
    return [public_delivery(row) for row in sorted(rows, key=lambda row: row["created_at"], reverse=True)]


@router.post("/v1/integrations/deliveries/{delivery_id}/retry")
async def retry_delivery(delivery_id: str, user: dict = Depends(current_user),
                         services: Services = Depends(get_services)) -> dict:
    delivery = await services.store.get("ops_deliveries", delivery_id)
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")
    await require_org_admin(delivery["organization_id"], user, services)
    if delivery["status"] not in {"FAILED", "NOT_CONFIGURED"}:
        raise HTTPException(status_code=409, detail=f"A {delivery['status']} delivery cannot be retried")
    return public_delivery(await services.ops.retry(delivery))


# ------------------------------------------------------------------ Google
@router.post("/v1/organizations/{organization_id}/integrations/google/connect")
async def google_connect(organization_id: str, user: dict = Depends(current_user),
                         services: Services = Depends(get_services)) -> dict:
    await require_org_admin(organization_id, user, services)
    if not google_auth.configured(services.settings):
        raise HTTPException(status_code=503, detail="Google OAuth is NOT_CONFIGURED on this server "
                                                    "(RELIEFMESH_GOOGLE_OAUTH_CLIENT_ID/SECRET)")
    verifier, challenge = google_auth.pkce_pair()
    state = await new_state(services, "google", organization_id, user, verifier)
    return {"authorization_url": google_auth.authorization_url(services.settings, state, challenge),
            "redirect_uri": services.settings.google_redirect_uri}


@router.get("/v1/integrations/google/callback", include_in_schema=False)
async def google_callback(code: str | None = None, state: str | None = None, error: str | None = None,
                          services: Services = Depends(get_services)) -> RedirectResponse:
    record = await consume_state(services, "google", state)
    organization_id = record["organization_id"]
    if error or not code:
        return RedirectResponse(settings_url(services, organization_id, google="error", reason=error or "no_code"),
                                status_code=303)
    try:
        async with services.hub.client(timeout=20) as client:
            tokens = await google_auth.exchange_code(client, services.settings, code, record["code_verifier"])
            email = await google_auth.account_email(client, tokens["access_token"])
    except IntegrationError as exc:
        return RedirectResponse(settings_url(services, organization_id, google="error", reason=str(exc)[:160]),
                                status_code=303)
    previous = await connections.load(services.store, organization_id, "google") or {}
    same_account = previous.get("account_email") == email
    connection = {
        "id": connections.connection_id(organization_id, "google"), "organization_id": organization_id,
        "provider": "google", "status": "connected", "account_email": email,
        "granted_scopes": sorted((tokens.get("scope") or "").split()),
        "capabilities": google_auth.capabilities(tokens.get("scope")),
        "token_ciphertext": google_auth.sealed_tokens(services.vault, tokens),
        "connected_by": record["user_id"], "connected_at": now_iso(), "last_error": None,
        "last_success": previous.get("last_success", {}) if same_account else {},
        # Keep the same ReliefMesh calendar / Drive folders when the same account reconnects.
        "calendar_id": previous.get("calendar_id") if same_account else None,
        "drive_root_id": previous.get("drive_root_id") if same_account else None,
        "drive_missions_id": previous.get("drive_missions_id") if same_account else None,
    }
    if not tokens.get("refresh_token"):
        connection.update(status="needs_reauth", last_error="Google returned no refresh token; reconnect")
    await connections.save(services.store, connection)
    services.ops.calendars.pop(organization_id, None)
    await audit("integration.google.connected", record["user_id"], organization_id, None, "integration",
                connection["id"], services, {"account_email": email, "capabilities": connection["capabilities"]})
    return RedirectResponse(settings_url(services, organization_id, google="connected"), status_code=303)


@router.post("/v1/organizations/{organization_id}/integrations/google/disconnect")
async def google_disconnect(organization_id: str, user: dict = Depends(current_user),
                            services: Services = Depends(get_services)) -> dict:
    await require_org_admin(organization_id, user, services)
    connection = await connections.load(services.store, organization_id, "google")
    revoked = False
    if connection:
        tokens = services.vault.open(connection.get("token_ciphertext")) or {}
        if tokens.get("refresh_token") or tokens.get("access_token"):
            async with services.hub.client(timeout=10) as client:
                revoked = await google_auth.revoke(client, tokens.get("refresh_token") or tokens["access_token"])
        connection.update(status="disconnected", token_ciphertext=None, disconnected_at=now_iso())
        await connections.save(services.store, connection)
        services.ops.calendars.pop(organization_id, None)
        await audit("integration.google.disconnected", user["id"], organization_id, None, "integration",
                    connection["id"], services, {"revoked_at_google": revoked})
    return {"status": "disconnected", "revoked_at_google": revoked}


# ------------------------------------------------------------------ Slack
@router.post("/v1/organizations/{organization_id}/integrations/slack/connect")
async def slack_connect(organization_id: str, user: dict = Depends(current_user),
                        services: Services = Depends(get_services)) -> dict:
    await require_org_admin(organization_id, user, services)
    if not slack.oauth_configured(services.settings):
        raise HTTPException(status_code=503, detail="Slack OAuth is NOT_CONFIGURED on this server "
                                                    "(RELIEFMESH_SLACK_CLIENT_ID/SECRET); paste a bot token or "
                                                    "webhook instead")
    state = await new_state(services, "slack", organization_id, user)
    return {"authorization_url": slack.authorization_url(services.settings, state),
            "redirect_uri": services.settings.slack_oauth_redirect_uri}


async def save_slack(services: Services, organization_id: str, user_id: str, *, mode: str,
                     sealed: dict[str, str], team: dict[str, Any], channel_id: str | None,
                     channel_name: str | None) -> dict[str, Any]:
    connection = {
        "id": connections.connection_id(organization_id, "slack"), "organization_id": organization_id,
        "provider": "slack", "status": "connected", "mode": mode, "team_id": team.get("id"),
        "team_name": team.get("name"), "channel_id": channel_id, "channel_name": channel_name,
        "token_ciphertext": services.vault.seal(sealed), "connected_by": user_id, "connected_at": now_iso(),
        "last_error": None, "last_success": {"slack": now_iso()},
    }
    await connections.save(services.store, connection)
    await audit("integration.slack.connected", user_id, organization_id, None, "integration", connection["id"],
                services, {"mode": mode, "team": team.get("name"), "channel": channel_name})
    return connection


@router.get("/v1/integrations/slack/callback", include_in_schema=False)
async def slack_callback(code: str | None = None, state: str | None = None, error: str | None = None,
                         services: Services = Depends(get_services)) -> RedirectResponse:
    record = await consume_state(services, "slack", state)
    organization_id = record["organization_id"]
    if error or not code:
        return RedirectResponse(settings_url(services, organization_id, slack="error", reason=error or "no_code"),
                                status_code=303)
    try:
        async with services.hub.client(timeout=20) as client:
            body = await slack.exchange_code(client, services.settings, code)
            hook = body.get("incoming_webhook") or {}
            channel_id = hook.get("channel_id")
            if channel_id:
                await slack.post_message(client, body["access_token"], channel_id,
                                         "✅ ReliefMesh is connected to this channel.", [
                                             {"type": "section", "text": {"type": "mrkdwn", "text":
                                                 "✅ *ReliefMesh is connected to this channel.* Approval, "
                                                 "disruption, replan and purchase-order alerts will post here. "
                                                 "Approvals still happen only inside ReliefMesh."}}])
    except IntegrationError as exc:
        return RedirectResponse(settings_url(services, organization_id, slack="error", reason=str(exc)[:160]),
                                status_code=303)
    await save_slack(services, organization_id, record["user_id"], mode="bot",
                     sealed={"bot_token": body["access_token"], "webhook_url": hook.get("url") or ""},
                     team=body.get("team") or {}, channel_id=channel_id, channel_name=hook.get("channel"))
    return RedirectResponse(settings_url(services, organization_id, slack="connected"), status_code=303)


@router.put("/v1/organizations/{organization_id}/integrations/slack")
async def slack_manual(organization_id: str, payload: SlackManualConfig, user: dict = Depends(current_user),
                       services: Services = Depends(get_services)) -> dict:
    """Connect with a bot token + channel or an incoming webhook; a real test post must succeed first."""

    await require_org_admin(organization_id, user, services)
    test_text = "✅ ReliefMesh is connected to this channel."
    test_blocks = [{"type": "section", "text": {"type": "mrkdwn", "text":
                    "✅ *ReliefMesh is connected to this channel.* Operations alerts will post here; "
                    "approvals still happen only inside ReliefMesh."}}]
    try:
        async with services.hub.client(timeout=15) as client:
            if payload.bot_token:
                if not payload.channel:
                    raise HTTPException(status_code=422, detail="A channel is required with a bot token")
                identity = await slack.auth_test(client, payload.bot_token.strip())
                # chat.postMessage accepts a channel ID or a public channel name.
                posted = await slack.post_message(client, payload.bot_token.strip(),
                                                  payload.channel.strip().lstrip("#"), test_text, test_blocks)
                connection = await save_slack(
                    services, organization_id, user["id"], mode="bot",
                    sealed={"bot_token": payload.bot_token.strip()},
                    team={"id": identity.get("team_id"), "name": identity.get("team")},
                    channel_id=posted["channel"], channel_name=payload.channel.strip())
            elif payload.webhook_url:
                await slack.post_webhook(client, payload.webhook_url.strip(), test_text, test_blocks)
                connection = await save_slack(services, organization_id, user["id"], mode="webhook",
                                              sealed={"webhook_url": payload.webhook_url.strip()}, team={},
                                              channel_id=None, channel_name="(incoming webhook channel)")
            else:
                raise HTTPException(status_code=422, detail="Provide a bot token and channel, or a webhook URL")
    except IntegrationError as exc:
        raise HTTPException(status_code=400, detail=f"Slack rejected the configuration: {exc}") from exc
    return connections.public(connection) or {}


@router.post("/v1/organizations/{organization_id}/integrations/slack/disconnect")
async def slack_disconnect(organization_id: str, user: dict = Depends(current_user),
                           services: Services = Depends(get_services)) -> dict:
    await require_org_admin(organization_id, user, services)
    connection = await connections.load(services.store, organization_id, "slack")
    revoked = False
    if connection:
        secrets_ = services.vault.open(connection.get("token_ciphertext")) or {}
        if secrets_.get("bot_token") and connection.get("mode") == "bot":
            async with services.hub.client(timeout=10) as client:
                revoked = await slack.revoke(client, secrets_["bot_token"])
        connection.update(status="disconnected", token_ciphertext=None, disconnected_at=now_iso())
        await connections.save(services.store, connection)
        await audit("integration.slack.disconnected", user["id"], organization_id, None, "integration",
                    connection["id"], services, {"revoked_at_slack": revoked})
    return {"status": "disconnected", "revoked_at_slack": revoked}


# ------------------------------------------------------------------ real test sends
@router.post("/v1/organizations/{organization_id}/integrations/test")
async def integration_test(organization_id: str, payload: IntegrationTestRequest,
                           user: dict = Depends(current_user), services: Services = Depends(get_services)) -> dict:
    """Make one real provider call and record it like any other delivery."""

    await require_org_admin(organization_id, user, services)
    record: dict[str, Any] = {
        "id": new_id(), "idempotency_key": f"integration_test|{new_id()}", "event_type": "integration_test",
        "organization_id": organization_id, "mission_id": None, "subject_id": organization_id, "version": None,
        "channel": payload.channel, "target": user["email"] if payload.channel == "gmail" else payload.channel,
        "summary": f"Connection test ({payload.channel})", "payload": {}, "attempts": 1, "max_attempts": 1,
        "sequence": 0, "provider": None, "provider_id": None, "provider_url": None, "last_error": None,
        "next_retry_at": None, "sent_at": None, "history": [], "created_at": now_iso(), "updated_at": now_iso(),
    }
    try:
        record.update(await run_test(services, organization_id, payload.channel, user))
        record["status"] = record.get("status") or "SENT"
        record["sent_at"] = now_iso() if record["status"] == "SENT" else None
    except IntegrationError as exc:
        record.update(status="NOT_CONFIGURED" if exc.not_configured else "FAILED", last_error=str(exc))
    await services.store.insert("ops_deliveries", record)
    return public_delivery(record)


async def run_test(services: Services, organization_id: str, channel: str, user: dict[str, Any]) -> dict[str, Any]:
    if channel == "gmail":
        if not recipient_allowed(services.settings, user["email"]):
            raise IntegrationError("Your address is outside RELIEFMESH_EMAIL_ALLOWED_RECIPIENTS")
        result = await services.email.send(OutgoingEmail(
            to=user["email"], subject="ReliefMesh — Gmail connection test",
            html="<p>This is a real test message from ReliefMesh operations integrations. Procurement emails "
                 "(RFQs, approval requests, disruption alerts, purchase orders) will be sent this way.</p>",
            text="This is a real test message from ReliefMesh operations integrations.",
            headers={"X-ReliefMesh-Event": "integration_test"}), organization_id, inline_retries=0, gmail_only=True)
        if result.status == "failed":
            raise IntegrationError(result.error or "Gmail send failed")
        if result.status == "not_configured":
            raise IntegrationError(result.error or "no transport", not_configured=True)
        return {"status": {"sent": "SENT", "test": "TEST", "disabled": "DISABLED", "suppressed": "SUPPRESSED"}[
            result.status], "provider": result.provider, "provider_id": result.provider_id,
            "last_error": result.error if result.status != "sent" else None}
    if channel == "slack":
        connection, secrets_ = await services.ops.slack_connection(organization_id)
        text = "✅ ReliefMesh connection test — operations alerts will appear in this channel."
        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]
        async with services.hub.client(timeout=15) as client:
            if connection["mode"] == "bot":
                body = await slack.post_message(client, secrets_["bot_token"], connection["channel_id"], text, blocks)
                outcome = {"provider": "slack", "provider_id": body["ts"]}
            else:
                await slack.post_webhook(client, secrets_["webhook_url"], text, blocks)
                outcome = {"provider": "slack_webhook"}
        connection.setdefault("last_success", {})["slack"] = now_iso()
        await connections.save(services.store, connection)
        return outcome
    async with services.hub.client(timeout=20) as client:
        token, connection = await google_auth.access_token(services.store, services.vault, services.settings,
                                                           client, organization_id, channel)
        if channel == "calendar":
            calendar_id = await services.ops.calendar_id_for(client, token, connection, refresh=False)
            calendar = await google_calendar.ensure_calendar(client, token, calendar_id)
            outcome = {"provider": "google_calendar", "provider_id": calendar["id"],
                       "provider_url": f"https://calendar.google.com/calendar/r?cid={calendar['id']}"}
        else:
            latest = await connections.load(services.store, organization_id, "google") or connection
            root = await google_drive.ensure_folder(client, token, "ReliefMesh", None, latest.get("drive_root_id"))
            if root["id"] != latest.get("drive_root_id"):
                latest.update(drive_root_id=root["id"], drive_missions_id=None)
                await connections.save(services.store, latest)
            outcome = {"provider": "google_drive", "provider_id": root["id"], "provider_url": root.get("webViewLink")}
    latest = await connections.load(services.store, organization_id, "google")
    if latest:
        latest.setdefault("last_success", {})[channel] = now_iso()
        await connections.save(services.store, latest)
    return outcome


# ------------------------------------------------------------------ public health (/v1/integrations/status)
async def _google_health(services: Services, capability: str) -> tuple[str, str, str | None]:
    if not google_auth.configured(services.settings):
        return "not_configured", "Google OAuth client is not configured on this server", None
    rows = [row for row in await connections.all_connected(services.store, "google")
            if (row.get("capabilities") or {}).get(capability)]
    if not rows:
        return "not_configured", f"no organization has granted {capability} access yet", None
    live = [row for row in rows if row.get("status") == "connected"]
    if not live:
        return "error", "BLOCKED: Google authorization expired or was revoked; an admin must reconnect", None
    connection = max(live, key=lambda row: row.get("connected_at") or "")
    async with services.hub.client(timeout=15) as client:
        try:
            token, connection = await google_auth.access_token(services.store, services.vault, services.settings,
                                                               client, connection["organization_id"], capability)
            if capability == "calendar" and connection.get("calendar_id"):
                await google_calendar.ensure_calendar(client, token, connection["calendar_id"])
                return "ok", f"{len(live)} organization(s) connected; Calendar API reachable", "LIVE"
            if capability == "drive" and connection.get("drive_root_id"):
                if await google_drive.get_file(client, token, connection["drive_root_id"]):
                    return "ok", f"{len(live)} organization(s) connected; Drive archive folder reachable", "LIVE"
        except IntegrationError as exc:
            return ("error" if exc.reauth else "degraded"), f"{'BLOCKED: ' if exc.reauth else ''}{exc}", None
    success = (connection.get("last_success") or {}).get(capability)
    if success:
        return "ok", f"authorized (token refresh OK); last successful {capability} call {success[:19]}Z", "LIVE"
    return "degraded", f"authorized (token refresh OK); no {capability} call made yet", None


async def check_gmail(services: Services) -> tuple[str, str, str | None]:
    return await _google_health(services, "gmail")


async def check_calendar(services: Services) -> tuple[str, str, str | None]:
    return await _google_health(services, "calendar")


async def check_drive(services: Services) -> tuple[str, str, str | None]:
    return await _google_health(services, "drive")


async def check_slack(services: Services) -> tuple[str, str, str | None]:
    rows = await connections.all_connected(services.store, "slack")
    if not rows:
        return "not_configured", "no organization has connected Slack yet", None
    live = [row for row in rows if row.get("status") == "connected"]
    if not live:
        return "error", "BLOCKED: Slack token revoked or webhook disabled; an admin must reconnect", None
    bots = [row for row in live if row.get("mode") == "bot"]
    if bots:
        secrets_ = services.vault.open(max(bots, key=lambda r: r["connected_at"]).get("token_ciphertext")) or {}
        async with services.hub.client(timeout=10) as client:
            try:
                await slack.auth_test(client, secrets_.get("bot_token", ""))
            except IntegrationError as exc:
                return ("error" if exc.reauth else "degraded"), str(exc), None
        return "ok", f"{len(live)} workspace connection(s); auth.test succeeded", "LIVE"
    success = max((row.get("last_success") or {}).get("slack") or "" for row in live)
    return ("ok", f"incoming webhook; last successful post {success[:19]}Z", "LIVE") if success else (
        "degraded", "incoming webhook configured; nothing posted yet", None)


for key, name, check in (("gmail", "Gmail", check_gmail), ("google_calendar", "Google Calendar", check_calendar),
                         ("google_drive", "Google Drive", check_drive), ("slack", "Slack", check_slack)):
    status_routes.register_check(key, name, "operations", check)
