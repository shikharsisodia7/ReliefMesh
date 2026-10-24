"""Shared HTTP plumbing for every external data source.

Each adapter call returns an ``AdapterResult`` whose ``provenance`` says exactly where
the data came from. A live response is ``LIVE``; a stored last-known-good copy is
``CACHED`` and keeps its original retrieval time; a missing credential is
``BLOCKED_EXTERNAL`` and never pretends to succeed.

The breaker follows the per-provider pattern used in OmniRoute's token-refresh
service (consecutive failures trip a cooldown, success resets it), shortened for
interactive use.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import httpx

from ..store import Store

AdapterStatus = Literal["OK", "BLOCKED_EXTERNAL", "UNAVAILABLE"]
Provenance = Literal["LIVE", "CACHED", "SANDBOX", "USER_SUBMITTED", "SYNTHETIC"]

BREAKER_THRESHOLD = 3
BREAKER_COOLDOWN_SECONDS = 120
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso(value: datetime) -> str:
    return value.isoformat()


def parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


@dataclass
class AdapterResult:
    provider: str
    status: AdapterStatus
    data: Any = None
    provenance: Provenance | None = None
    source_url: str | None = None
    retrieved_at: str | None = None
    error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "OK"

    def public(self) -> dict[str, Any]:
        return asdict(self)


class ExternalHTTPError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class _Breaker:
    failures: int = 0
    open_until: float = 0.0


class IntegrationHub:
    """Executes outbound requests with timeout, retry, breaker, and cache fallback."""

    def __init__(self, store: Store, user_agent: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.store = store
        self.user_agent = user_agent
        self.transport = transport
        self._breakers: dict[str, _Breaker] = {}
        self._memo: dict[str, tuple[float, Any]] = {}

    def client(self, timeout: float = 10.0) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=timeout,
            transport=self.transport,
            headers={"User-Agent": self.user_agent, "Accept": "application/json"},
            follow_redirects=True,
        )

    # ----- breaker -----
    def breaker_open(self, provider: str) -> bool:
        breaker = self._breakers.get(provider)
        if not breaker or not breaker.open_until:
            return False
        if breaker.open_until > time.monotonic():
            return True
        self._breakers.pop(provider, None)
        return False

    def _record_success(self, provider: str) -> None:
        self._breakers.pop(provider, None)

    def _record_failure(self, provider: str) -> None:
        breaker = self._breakers.setdefault(provider, _Breaker())
        breaker.failures += 1
        if breaker.failures >= BREAKER_THRESHOLD:
            breaker.open_until = time.monotonic() + BREAKER_COOLDOWN_SECONDS

    def breaker_status(self) -> dict[str, dict[str, Any]]:
        now = time.monotonic()
        return {
            provider: {"failures": state.failures, "open": state.open_until > now}
            for provider, state in self._breakers.items()
        }

    # ----- cache -----
    @staticmethod
    def cache_id(provider: str, key: str) -> str:
        return hashlib.sha256(f"{provider}:{key}".encode()).hexdigest()

    async def read_cache(self, provider: str, key: str) -> dict[str, Any] | None:
        return await self.store.get("integration_cache", self.cache_id(provider, key))

    async def write_cache(self, provider: str, key: str, data: Any, source_url: str, retrieved_at: str) -> None:
        await self.store.upsert(
            "integration_cache",
            {
                "id": self.cache_id(provider, key),
                "provider": provider,
                "key": key,
                "data": data,
                "source_url": source_url,
                "retrieved_at": retrieved_at,
            },
        )

    # ----- request -----
    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None,
        headers: dict[str, str] | None,
        json_body: Any,
        timeout: float,
        retries: int,
        expect: Literal["json", "text"],
        not_found_ok: bool,
    ) -> Any:
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            if attempt:
                await asyncio.sleep(0.4 * (2 ** (attempt - 1)))
            try:
                async with self.client(timeout) as client:
                    response = await client.request(method, url, params=params, headers=headers, json=json_body)
                if not_found_ok and response.status_code == 404:
                    return None
                if response.status_code in RETRYABLE_STATUS:
                    last_error = ExternalHTTPError(f"HTTP {response.status_code}", response.status_code)
                    continue
                if response.status_code >= 400:
                    detail = response.text[:300]
                    raise ExternalHTTPError(f"HTTP {response.status_code}: {detail}", response.status_code)
                return response.json() if expect == "json" else response.text
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = ExternalHTTPError(f"{type(exc).__name__}: {exc}" or type(exc).__name__)
            except ValueError as exc:  # malformed JSON from upstream is not retryable
                raise ExternalHTTPError(f"Malformed response: {exc}") from exc
        raise last_error or ExternalHTTPError("request failed")

    async def fetch(
        self,
        provider: str,
        url: str,
        *,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        json_body: Any = None,
        cache_key: str | None = None,
        fresh_seconds: int = 0,
        timeout: float = 10.0,
        retries: int = 2,
        expect: Literal["json", "text"] = "json",
        not_found_ok: bool = False,
        provenance: Provenance = "LIVE",
        source_url: str | None = None,
    ) -> AdapterResult:
        """Fetch a resource, falling back to the last-known-good cache on failure."""

        public_url = source_url or url
        cached = await self.read_cache(provider, cache_key) if cache_key else None
        if cached and fresh_seconds:
            age = (utc_now() - parse_iso(cached["retrieved_at"])).total_seconds()
            if age < fresh_seconds:
                return AdapterResult(
                    provider, "OK", cached["data"], "CACHED", cached["source_url"], cached["retrieved_at"],
                    meta={"cache_age_seconds": int(age)},
                )

        if self.breaker_open(provider):
            error = f"{provider} circuit breaker open after repeated failures"
        else:
            try:
                data = await self._request(
                    method, url, params=params, headers=headers, json_body=json_body,
                    timeout=timeout, retries=retries, expect=expect, not_found_ok=not_found_ok,
                )
                self._record_success(provider)
                retrieved_at = iso(utc_now())
                if cache_key:
                    await self.write_cache(provider, cache_key, data, public_url, retrieved_at)
                return AdapterResult(provider, "OK", data, provenance, public_url, retrieved_at)
            except ExternalHTTPError as exc:
                # 4xx (other than 429) is a request problem, not provider health.
                if exc.status_code is None or exc.status_code in RETRYABLE_STATUS:
                    self._record_failure(provider)
                error = str(exc)

        if cached:
            return AdapterResult(
                provider, "OK", cached["data"], "CACHED", cached["source_url"], cached["retrieved_at"],
                error=f"Live request failed ({error}); serving last-known-good data.",
            )
        return AdapterResult(provider, "UNAVAILABLE", None, None, public_url, None, error=error)

    def blocked(self, provider: str, reason: str, source_url: str | None = None) -> AdapterResult:
        return AdapterResult(provider, "BLOCKED_EXTERNAL", None, None, source_url, None, error=reason)

    # ----- process-local memo for large reference datasets (e.g. OFAC SDN list) -----
    def memo_get(self, key: str, max_age_seconds: int) -> Any | None:
        entry = self._memo.get(key)
        if entry and time.monotonic() - entry[0] < max_age_seconds:
            return entry[1]
        return None

    def memo_set(self, key: str, value: Any) -> None:
        self._memo[key] = (time.monotonic(), value)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def window_start(days: int) -> str:
    return iso(utc_now() - timedelta(days=days))
