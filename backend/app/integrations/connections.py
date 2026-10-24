"""Per-organization OAuth connections (Google, Slack) with tokens encrypted at rest.

A connection document never holds a plaintext credential: tokens live in ``token_ciphertext``
(Fernet). Everything else (granted scopes, account, channel, health) is plain so the settings
view can render it. A connection is only reported connected after the provider returned tokens.
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from ..settings import Settings
from ..store import Store

COLLECTION = "integration_connections"


class IntegrationError(Exception):
    """A failed provider call. ``retryable`` drives backoff; ``reauth`` means a human must reconnect."""

    def __init__(self, message: str, *, retryable: bool = False, reauth: bool = False,
                 not_configured: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.reauth = reauth
        self.not_configured = not_configured


class TokenVault:
    def __init__(self, settings: Settings) -> None:
        explicit = settings.integration_encryption_key
        if explicit is not None:
            key = explicit.get_secret_value().encode()
        else:  # domain-separated derivation; rotating the JWT secret forces a reconnect
            digest = hashlib.sha256(b"reliefmesh-integration-tokens:" + settings.jwt_secret.get_secret_value().encode())
            key = base64.urlsafe_b64encode(digest.digest())
        self._fernet = Fernet(key)

    def seal(self, tokens: dict[str, Any]) -> str:
        return self._fernet.encrypt(json.dumps(tokens).encode()).decode()

    def open(self, ciphertext: str | None) -> dict[str, Any] | None:
        if not ciphertext:
            return None
        try:
            return json.loads(self._fernet.decrypt(ciphertext.encode()))
        except (InvalidToken, ValueError):
            return None


def connection_id(organization_id: str, provider: str) -> str:
    return f"{organization_id}:{provider}"


async def load(store: Store, organization_id: str, provider: str) -> dict[str, Any] | None:
    return await store.get(COLLECTION, connection_id(organization_id, provider))


async def save(store: Store, connection: dict[str, Any]) -> dict[str, Any]:
    return await store.upsert(COLLECTION, connection)


async def all_connected(store: Store, provider: str) -> list[dict[str, Any]]:
    return [row for row in await store.find(COLLECTION, provider=provider) if row.get("status") != "disconnected"]


def public(connection: dict[str, Any] | None) -> dict[str, Any] | None:
    if not connection:
        return None
    return {key: value for key, value in connection.items() if key not in {"token_ciphertext"}}
