"""Gmail API adapter: RFC 5322 messages sent with the ``gmail.send`` scope."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Any

import httpx

from .connections import IntegrationError
from .google_auth import raise_for_google

SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


@dataclass(frozen=True)
class Attachment:
    filename: str
    content: bytes
    mime_type: str = "application/pdf"


@dataclass(frozen=True)
class OutgoingEmail:
    to: str
    subject: str
    html: str
    text: str | None = None
    attachments: tuple[Attachment, ...] = field(default_factory=tuple)
    headers: dict[str, str] = field(default_factory=dict)


def build_raw(message: OutgoingEmail, sender: str | None, sender_name: str = "ReliefMesh Operations") -> str:
    mime = EmailMessage()
    mime["To"] = message.to
    if sender:  # Gmail rewrites From to the authenticated account; set it explicitly for a clean display name
        mime["From"] = formataddr((sender_name, sender))
    mime["Subject"] = message.subject
    mime["Message-ID"] = make_msgid(domain="reliefmesh.app")
    for name, value in message.headers.items():
        mime[name] = value
    mime.set_content(message.text or "This message requires an HTML-capable email client.")
    mime.add_alternative(message.html, subtype="html")
    for attachment in message.attachments:
        maintype, subtype = attachment.mime_type.split("/", 1)
        mime.add_attachment(attachment.content, maintype=maintype, subtype=subtype, filename=attachment.filename)
    return base64.urlsafe_b64encode(mime.as_bytes()).decode()


async def send(client: httpx.AsyncClient, access_token: str, message: OutgoingEmail,
               sender: str | None) -> dict[str, Any]:
    """Send one message; returns Gmail's ``{"id", "threadId", "labelIds"}``."""

    try:
        response = await client.post(SEND_URL, headers={"Authorization": f"Bearer {access_token}"},
                                     json={"raw": build_raw(message, sender)})
    except httpx.HTTPError as exc:
        raise IntegrationError(f"Gmail unreachable: {type(exc).__name__}", retryable=True) from exc
    raise_for_google(response, "Gmail send")
    body = response.json()
    if not body.get("id"):
        raise IntegrationError("Gmail accepted the request but returned no message id")
    return body
