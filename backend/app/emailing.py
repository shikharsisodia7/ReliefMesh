from __future__ import annotations

from dataclasses import dataclass

import httpx

from .settings import Settings


@dataclass(frozen=True)
class EmailResult:
    delivered: bool
    provider_id: str | None = None
    error: str | None = None


class EmailGateway:
    async def send(self, to: str, subject: str, html: str) -> EmailResult:
        raise NotImplementedError


class ResendEmailGateway(EmailGateway):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def send(self, to: str, subject: str, html: str) -> EmailResult:
        api_key = self.settings.resend_api_key
        if api_key is None:
            return EmailResult(delivered=False, error="RESEND_API_KEY is not configured")
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {api_key.get_secret_value()}"},
                    json={"from": self.settings.email_from, "to": [to], "subject": subject, "html": html},
                )
            response.raise_for_status()
            return EmailResult(delivered=True, provider_id=response.json().get("id"))
        except httpx.HTTPError as exc:
            return EmailResult(delivered=False, error=str(exc))


class TestEmailGateway(EmailGateway):
    """No-network email double used only under RELIEFMESH_APP_ENV=test."""

    async def send(self, to: str, subject: str, html: str) -> EmailResult:
        return EmailResult(delivered=True, provider_id=f"test:{to}")
