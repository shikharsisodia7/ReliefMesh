"""Google OAuth 2.0 (web-server flow with PKCE) shared by Gmail, Calendar, and Drive.

One consent grants the minimum scopes: ``gmail.send`` (send only, no mailbox access),
``calendar.app.created`` (only calendars ReliefMesh creates), and ``drive.file`` (only files
ReliefMesh creates). Google's granular consent lets a user untick any of them, so capabilities
are derived from the scopes Google actually granted, never from the scopes requested.

Refresh handling follows OmniRoute's Google refresh provider (MIT): keep the stored refresh
token when Google omits a new one, and treat ``invalid_grant`` as unrecoverable (re-consent),
not as something to retry.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import secrets
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx

from ..settings import Settings
from ..store import Store
from . import connections
from .connections import IntegrationError, TokenVault

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
SCOPES = {
    "gmail": "https://www.googleapis.com/auth/gmail.send",
    "calendar": "https://www.googleapis.com/auth/calendar.app.created",
    "drive": "https://www.googleapis.com/auth/drive.file",
}
IDENTITY_SCOPES = ("openid", "email")
REFRESH_MARGIN = timedelta(seconds=90)

_refresh_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


def configured(settings: Settings) -> bool:
    return bool(settings.google_oauth_client_id and settings.google_oauth_client_secret)


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def authorization_url(settings: Settings, state: str, code_challenge: str, login_hint: str | None = None) -> str:
    params = {
        "client_id": settings.google_oauth_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join((*IDENTITY_SCOPES, *SCOPES.values())),
        "access_type": "offline",  # a refresh token, so notifications work while nobody is signed in
        "prompt": "consent",  # re-issues a refresh token on reconnect
        "include_granted_scopes": "true",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    if login_hint:
        params["login_hint"] = login_hint
    return f"{AUTH_URL}?{urlencode(params)}"


def capabilities(granted_scope: str | None) -> dict[str, bool]:
    granted = set((granted_scope or "").split())
    return {name: scope in granted for name, scope in SCOPES.items()}


async def account_email(client: httpx.AsyncClient, access_token: str) -> str | None:
    """The connected account, as Google's userinfo endpoint reports it for this access token."""

    try:
        response = await client.get(USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    body = response.json()
    return body.get("email") if body.get("email_verified") else None


def _error_code(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:120]
    error = body.get("error") if isinstance(body, dict) else body
    if isinstance(error, dict):  # Google APIs nest {"error": {"status": ..., "message": ...}}
        return str(error.get("status") or error.get("code") or error.get("message"))
    return str(error)


async def _token_request(client: httpx.AsyncClient, data: dict[str, str]) -> dict[str, Any]:
    try:
        response = await client.post(TOKEN_URL, data=data, headers={"Accept": "application/json"})
    except httpx.HTTPError as exc:
        raise IntegrationError(f"Google token endpoint unreachable: {type(exc).__name__}", retryable=True) from exc
    if response.status_code >= 500 or response.status_code == 429:
        raise IntegrationError(f"Google token endpoint returned {response.status_code}", retryable=True)
    if response.status_code != 200:
        code = _error_code(response)
        if code in {"invalid_grant", "unauthorized_client", "invalid_client"}:
            raise IntegrationError(f"Google authorization is no longer valid ({code}); reconnect Google",
                                   reauth=True)
        raise IntegrationError(f"Google token request rejected: {code}")
    return response.json()


async def exchange_code(client: httpx.AsyncClient, settings: Settings, code: str, verifier: str) -> dict[str, Any]:
    return await _token_request(client, {
        "code": code,
        "client_id": settings.google_oauth_client_id or "",
        "client_secret": settings.google_oauth_client_secret.get_secret_value()
        if settings.google_oauth_client_secret else "",
        "redirect_uri": settings.google_redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": verifier,
    })


def sealed_tokens(vault: TokenVault, tokens: dict[str, Any], previous_refresh: str | None = None) -> str:
    expires_at = datetime.now(UTC) + timedelta(seconds=int(tokens.get("expires_in") or 3600))
    return vault.seal({
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token") or previous_refresh,
        "expires_at": expires_at.isoformat(),
    })


async def mark_reauth(store: Store, connection: dict[str, Any], reason: str) -> None:
    connection.update(status="needs_reauth", last_error=reason, last_error_at=datetime.now(UTC).isoformat())
    await connections.save(store, connection)


async def access_token(store: Store, vault: TokenVault, settings: Settings, client: httpx.AsyncClient,
                       organization_id: str, capability: str) -> tuple[str, dict[str, Any]]:
    """A valid access token for an organization's Google connection, refreshing when near expiry."""

    if not configured(settings):
        raise IntegrationError("Google OAuth client is not configured on this server", not_configured=True)
    async with _refresh_locks[organization_id]:
        connection = await connections.load(store, organization_id, "google")
        if not connection or connection.get("status") == "disconnected":
            raise IntegrationError("Google is not connected for this organization", not_configured=True)
        if connection.get("status") == "needs_reauth":
            raise IntegrationError(connection.get("last_error") or "Google needs to be reconnected", reauth=True)
        if not (connection.get("capabilities") or {}).get(capability):
            raise IntegrationError(f"The Google account did not grant the {capability} permission",
                                   not_configured=True)
        tokens = vault.open(connection.get("token_ciphertext"))
        if not tokens:
            await mark_reauth(store, connection, "Stored Google credentials could not be decrypted; reconnect")
            raise IntegrationError("Stored Google credentials are unreadable; reconnect Google", reauth=True)
        if datetime.fromisoformat(tokens["expires_at"]) - REFRESH_MARGIN > datetime.now(UTC):
            return tokens["access_token"], connection
        if not tokens.get("refresh_token"):
            await mark_reauth(store, connection, "Google did not issue a refresh token; reconnect")
            raise IntegrationError("Google access expired and no refresh token is stored", reauth=True)
        try:
            fresh = await _token_request(client, {
                "client_id": settings.google_oauth_client_id or "",
                "client_secret": settings.google_oauth_client_secret.get_secret_value()
                if settings.google_oauth_client_secret else "",
                "refresh_token": tokens["refresh_token"],
                "grant_type": "refresh_token",
            })
        except IntegrationError as exc:
            if exc.reauth:
                await mark_reauth(store, connection, str(exc))
            raise
        connection["token_ciphertext"] = sealed_tokens(vault, fresh, tokens["refresh_token"])
        connection["token_refreshed_at"] = datetime.now(UTC).isoformat()
        await connections.save(store, connection)
        return fresh["access_token"], connection


async def revoke(client: httpx.AsyncClient, token: str) -> bool:
    try:
        response = await client.post(REVOKE_URL, data={"token": token})
    except httpx.HTTPError:
        return False
    return response.status_code == 200


def raise_for_google(response: httpx.Response, action: str) -> None:
    """Classify a Google API response: retry on 429/5xx, reconnect on 401, fail fast otherwise."""

    if response.status_code < 400:
        return
    code = _error_code(response)
    if response.status_code == 401:
        raise IntegrationError(f"{action}: Google rejected the access token ({code})", retryable=True)
    if response.status_code == 429 or response.status_code >= 500:
        raise IntegrationError(f"{action}: Google returned {response.status_code} ({code})", retryable=True)
    if response.status_code == 403 and "rateLimitExceeded" in response.text:
        raise IntegrationError(f"{action}: Google rate limit ({code})", retryable=True)
    raise IntegrationError(f"{action}: Google returned {response.status_code} ({code})")
