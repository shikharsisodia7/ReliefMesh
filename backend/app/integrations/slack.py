"""Slack adapter: an OAuth-installed app (bot token + chosen channel) or an incoming webhook.

Messages are informational only. ReliefMesh registers no slash commands, interactive
approve buttons, or reaction handlers: the only buttons are links back into ReliefMesh,
where approval still requires the approver's own session and authorization rules.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode, urlparse

import httpx

from ..settings import Settings
from .connections import IntegrationError

AUTHORIZE_URL = "https://slack.com/oauth/v2/authorize"
API = "https://slack.com/api"
# chat:write posts as the app; incoming-webhook gives the installer a channel picker; chat:write.public
# lets the bot post to that public channel without a separate /invite.
BOT_SCOPES = ("chat:write", "chat:write.public", "incoming-webhook")
WEBHOOK_PREFIX = "https://hooks.slack.com/services/"
REAUTH_ERRORS = {"invalid_auth", "token_revoked", "account_inactive", "not_authed", "token_expired"}
RETRYABLE_ERRORS = {"ratelimited", "service_unavailable", "internal_error", "fatal_error", "request_timeout"}


def oauth_configured(settings: Settings) -> bool:
    return bool(settings.slack_client_id and settings.slack_client_secret)


def authorization_url(settings: Settings, state: str) -> str:
    return f"{AUTHORIZE_URL}?" + urlencode({
        "client_id": settings.slack_client_id,
        "scope": ",".join(BOT_SCOPES),
        "redirect_uri": settings.slack_oauth_redirect_uri,
        "state": state,
    })


def _raise_for_slack(response: httpx.Response, action: str) -> dict[str, Any]:
    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After", "30")
        raise IntegrationError(f"{action}: Slack rate limited (retry after {retry_after}s)", retryable=True)
    if response.status_code >= 500:
        raise IntegrationError(f"{action}: Slack returned {response.status_code}", retryable=True)
    try:
        body = response.json()
    except ValueError as exc:
        raise IntegrationError(f"{action}: Slack returned non-JSON ({response.status_code})") from exc
    if not body.get("ok"):
        error = body.get("error", "unknown_error")
        raise IntegrationError(f"{action}: Slack error {error}", retryable=error in RETRYABLE_ERRORS,
                               reauth=error in REAUTH_ERRORS)
    return body


async def _post(client: httpx.AsyncClient, method: str, action: str, *, token: str | None = None,
                json: dict[str, Any] | None = None, data: dict[str, str] | None = None,
                auth: tuple[str, str] | None = None) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        response = await client.post(f"{API}/{method}", headers=headers, json=json, data=data, auth=auth)
    except httpx.HTTPError as exc:
        raise IntegrationError(f"{action}: Slack unreachable ({type(exc).__name__})", retryable=True) from exc
    return _raise_for_slack(response, action)


async def exchange_code(client: httpx.AsyncClient, settings: Settings, code: str) -> dict[str, Any]:
    secret = settings.slack_client_secret.get_secret_value() if settings.slack_client_secret else ""
    return await _post(client, "oauth.v2.access", "Slack install", auth=(settings.slack_client_id or "", secret),
                       data={"code": code, "redirect_uri": settings.slack_oauth_redirect_uri})


async def auth_test(client: httpx.AsyncClient, token: str) -> dict[str, Any]:
    return await _post(client, "auth.test", "Slack auth.test", token=token)


async def post_message(client: httpx.AsyncClient, token: str, channel: str, text: str,
                       blocks: list[dict[str, Any]]) -> dict[str, Any]:
    """chat.postMessage; returns Slack's body including ``ts`` and the resolved ``channel`` id."""

    return await _post(client, "chat.postMessage", "Slack post", token=token, json={
        "channel": channel, "text": text, "blocks": blocks, "unfurl_links": False, "unfurl_media": False,
    })


async def update_message(client: httpx.AsyncClient, token: str, channel: str, ts: str, text: str,
                         blocks: list[dict[str, Any]]) -> dict[str, Any]:
    return await _post(client, "chat.update", "Slack update", token=token,
                       json={"channel": channel, "ts": ts, "text": text, "blocks": blocks})


async def revoke(client: httpx.AsyncClient, token: str) -> bool:
    try:
        await _post(client, "auth.revoke", "Slack revoke", token=token)
        return True
    except IntegrationError:
        return False


def validated_webhook(url: str) -> str:
    """Only Slack's own webhook host is reachable from here (an admin-supplied URL must not become SSRF)."""

    parsed = urlparse(url.strip())
    if (parsed.scheme != "https" or (parsed.hostname or "").rstrip(".").lower() != "hooks.slack.com"
            or parsed.port not in (None, 443) or parsed.username or parsed.password
            or not parsed.path.startswith("/services/")):
        raise IntegrationError(f"Slack webhook URL must start with {WEBHOOK_PREFIX}")
    return f"https://hooks.slack.com{parsed.path}"


async def post_webhook(client: httpx.AsyncClient, url: str, text: str, blocks: list[dict[str, Any]]) -> None:
    target = validated_webhook(url)
    try:
        response = await client.post(target, json={"text": text, "blocks": blocks, "unfurl_links": False},
                                     follow_redirects=False)
    except httpx.HTTPError as exc:
        raise IntegrationError(f"Slack webhook unreachable ({type(exc).__name__})", retryable=True) from exc
    if response.status_code == 429 or response.status_code >= 500:
        raise IntegrationError(f"Slack webhook returned {response.status_code}", retryable=True)
    if response.status_code != 200 or response.text.strip() != "ok":
        error = response.text.strip()[:80] or str(response.status_code)
        raise IntegrationError(f"Slack webhook rejected the message: {error}",
                               reauth=error in {"invalid_token", "no_active_hooks", "action_prohibited"})
