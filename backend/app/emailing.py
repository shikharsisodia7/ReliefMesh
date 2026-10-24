"""Outbound email routing: one gateway, an explicit mode, and an organization's own Gmail.

``RELIEFMESH_EMAIL_MODE``:
  * ``disabled`` - nothing is sent; the attempt is recorded as ``disabled``.
  * ``test``     - the fully rendered message is stored in ``email_outbox``; no network call.
  * ``live``     - the organization's connected Gmail account, else Resend, else ``not_configured``.

A result is ``sent`` only when a provider returned a message id for it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

import httpx

from .integrations import gmail, google_auth
from .integrations.connections import IntegrationError, TokenVault
from .integrations.gmail import OutgoingEmail
from .settings import Settings
from .store import Store


@dataclass(frozen=True)
class EmailResult:
    delivered: bool
    provider_id: str | None = None
    error: str | None = None
    status: str = ""  # sent | failed | not_configured | test | disabled | suppressed
    provider: str | None = None  # gmail | resend | test
    thread_id: str | None = None
    retryable: bool = False
    sender: str | None = None

    def __post_init__(self) -> None:
        if not self.status:
            object.__setattr__(self, "status", "sent" if self.delivered else "failed")


def recipient_allowed(settings: Settings, address: str) -> bool:
    allowed = [entry.strip().lower() for entry in settings.email_allowed_recipients if entry.strip()]
    if not allowed:
        return True
    address = address.lower()
    return any(address == entry or (entry.startswith("@") and address.endswith(entry)) for entry in allowed)


class EmailGateway:
    def __init__(self, settings: Settings, store: Store, vault: TokenVault,
                 client: Callable[..., httpx.AsyncClient]) -> None:
        self.settings = settings
        self.store = store
        self.vault = vault
        self.client = client

    async def send(self, message: OutgoingEmail, organization_id: str | None = None,
                   inline_retries: int = 1) -> EmailResult:
        mode = self.settings.resolved_email_mode
        if mode == "disabled":
            return EmailResult(False, status="disabled", error="RELIEFMESH_EMAIL_MODE=disabled")
        if not recipient_allowed(self.settings, message.to):
            return EmailResult(False, status="suppressed",
                               error="recipient is outside RELIEFMESH_EMAIL_ALLOWED_RECIPIENTS")
        if mode == "test":
            outbox_id = str(uuid4())
            await self.store.insert("email_outbox", {
                "id": outbox_id, "organization_id": organization_id, "to": message.to, "subject": message.subject,
                "html": message.html, "text": message.text, "headers": message.headers,
                "attachments": [{"filename": a.filename, "mime_type": a.mime_type, "bytes": len(a.content)}
                                for a in message.attachments],
                "created_at": datetime.now(UTC).isoformat(),
            })
            return EmailResult(False, provider_id=f"outbox:{outbox_id}", status="test", provider="test")
        gmail_result = None
        if organization_id:
            for attempt in range(inline_retries + 1):
                gmail_result = await self._gmail(message, organization_id)
                if gmail_result.status != "failed" or not gmail_result.retryable or attempt == inline_retries:
                    break
                await asyncio.sleep(1.5 * (attempt + 1))
            if gmail_result.status == "sent":
                return gmail_result
        if self.settings.resend_api_key is not None:
            return await self._resend(message)
        if gmail_result and gmail_result.status == "failed":
            return gmail_result
        return EmailResult(False, status="not_configured",
                           error="Email is not configured: connect Gmail in Operations Integrations or set "
                                 "RELIEFMESH_RESEND_API_KEY; no email was sent")

    async def _gmail(self, message: OutgoingEmail, organization_id: str) -> EmailResult:
        async with self.client(timeout=20) as client:
            try:
                token, connection = await google_auth.access_token(
                    self.store, self.vault, self.settings, client, organization_id, "gmail")
                sent = await gmail.send(client, token, message, connection.get("account_email"))
            except IntegrationError as exc:
                status = "not_configured" if exc.not_configured else "failed"
                return EmailResult(False, error=str(exc), status=status, provider="gmail", retryable=exc.retryable)
        await self._record_gmail_success(organization_id)
        return EmailResult(True, provider_id=sent["id"], thread_id=sent.get("threadId"), provider="gmail",
                           sender=connection.get("account_email"))

    async def _record_gmail_success(self, organization_id: str) -> None:
        from .integrations import connections

        connection = await connections.load(self.store, organization_id, "google")
        if connection:
            connection.setdefault("last_success", {})["gmail"] = datetime.now(UTC).isoformat()
            await connections.save(self.store, connection)

    async def _resend(self, message: OutgoingEmail) -> EmailResult:
        api_key = self.settings.resend_api_key
        assert api_key is not None
        body = {"from": self.settings.email_from, "to": [message.to], "subject": message.subject,
                "html": message.html, "text": message.text}
        if message.attachments:
            import base64

            body["attachments"] = [{"filename": a.filename, "content": base64.b64encode(a.content).decode()}
                                   for a in message.attachments]
        try:
            async with self.client(timeout=10) as client:
                response = await client.post("https://api.resend.com/emails",
                                             headers={"Authorization": f"Bearer {api_key.get_secret_value()}"},
                                             json=body)
        except httpx.HTTPError as exc:
            return EmailResult(False, error=f"{type(exc).__name__}: {exc}", provider="resend", retryable=True)
        if response.status_code >= 400:
            try:
                reason = response.json().get("message") or response.text[:200]
            except ValueError:
                reason = response.text[:200]
            return EmailResult(False, error=f"Resend HTTP {response.status_code}: {reason}", provider="resend",
                               retryable=response.status_code >= 500 or response.status_code == 429)
        return EmailResult(True, provider_id=response.json().get("id"), provider="resend")
