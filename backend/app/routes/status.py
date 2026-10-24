"""Integration health. A service is reported "ok" only after a real request to it succeeds."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable

from fastapi import APIRouter, Depends

from ..core import Services, get_services, now_iso, secret
from ..integrations import apify, emergency, ofac
from ..integrations.http import AdapterResult

router = APIRouter()
CACHE_SECONDS = 60

Check = Callable[[Services], Awaitable[tuple[str, str, str | None]]]


def from_result(result: AdapterResult, ok_detail: str) -> tuple[str, str, str | None]:
    if result.status == "BLOCKED_EXTERNAL":
        return "not_configured", result.error or "credential missing", None
    if not result.ok:
        return "error", result.error or "request failed", None
    if result.provenance == "CACHED":
        return "degraded", f"live request failed; serving cached data from {result.retrieved_at}", "CACHED"
    return "ok", ok_detail, result.provenance


async def check_mongo(services: Services) -> tuple[str, str, str | None]:
    if services.settings.storage_mode != "mongo":
        return "degraded", "in-memory store (non-persistent; local/test mode only)", None
    await services.store.ping()
    return "ok", f"ping succeeded on database '{services.settings.mongodb_database}'", "LIVE"


async def check_eonet(services: Services) -> tuple[str, str, str | None]:
    result = await services.hub.fetch("nasa_eonet", f"{emergency.EONET_BASE}/events", params={"status": "open",
                                                                                              "limit": 1})
    return from_result(result, "open events endpoint responded")


async def check_nws(services: Services) -> tuple[str, str, str | None]:
    result = await services.hub.fetch("nws", f"{emergency.NWS_BASE}/alerts/active/count",
                                      headers={"Accept": "application/geo+json"})
    total = (result.data or {}).get("total") if result.ok else None
    return from_result(result, f"{total} active alerts nationwide")


async def check_firms(services: Services) -> tuple[str, str, str | None]:
    key = secret(services.settings.nasa_firms_map_key)
    if not key:
        return "not_configured", "RELIEFMESH_NASA_FIRMS_MAP_KEY is not configured", None
    result = await services.hub.fetch("nasa_firms", f"https://firms.modaps.eosdis.nasa.gov/mapserver/mapkey_status/"
                                                    f"?MAP_KEY={key}", source_url="FIRMS mapkey_status")
    if result.ok and isinstance(result.data, dict) and "current_transactions" in result.data:
        return "ok", (f"MAP_KEY valid; {result.data.get('current_transactions')} of "
                      f"{result.data.get('transaction_limit')} transactions used"), "LIVE"
    return from_result(result, "MAP_KEY responded")


async def check_fema(services: Services) -> tuple[str, str, str | None]:
    result = await services.hub.fetch("openfema", emergency.FEMA_URL, params={"$top": 1})
    return from_result(result, "DisasterDeclarationsSummaries responded")


async def check_ofac(services: Services) -> tuple[str, str, str | None]:
    result = await ofac.load_index(services.hub, services.settings.ofac_sdn_url, services.settings.ofac_alt_url)
    if result.ok:
        index = result.data
        status = "ok" if index.provenance == "LIVE" else "degraded"
        return status, f"{len(index.entries):,} SDN names/aliases loaded at {index.retrieved_at[:19]}Z", index.provenance
    return from_result(result, "")


async def check_usaspending(services: Services) -> tuple[str, str, str | None]:
    result = await services.hub.fetch("usaspending", "https://api.usaspending.gov/api/v2/autocomplete/recipient/",
                                      method="POST", json_body={"search_text": "3M", "limit": 1})
    return from_result(result, "recipient search responded")


async def check_openfda(services: Services) -> tuple[str, str, str | None]:
    result = await services.hub.fetch("openfda", "https://api.fda.gov/device/enforcement.json", params={"limit": 1})
    return from_result(result, "device enforcement endpoint responded")


async def check_sam(services: Services) -> tuple[str, str, str | None]:
    key = secret(services.settings.sam_gov_api_key)
    if not key:
        return "not_configured", "RELIEFMESH_SAM_GOV_API_KEY is not configured (requires a SAM.gov account)", None
    result = await services.hub.fetch("sam_gov", "https://api.sam.gov/entity-information/v3/entities",
                                      params={"api_key": key, "legalBusinessName": "3M Company"},
                                      source_url="https://api.sam.gov/entity-information/v3/entities")
    return from_result(result, "entity API accepted the key")


async def check_apify(services: Services) -> tuple[str, str, str | None]:
    result = await apify.account(services.hub, secret(services.settings.apify_api_token))
    detail = f"authenticated as {(result.data or {}).get('username')} ({(result.data or {}).get('plan')})" \
        if result.ok else ""
    return from_result(result, detail)


async def check_resend(services: Services) -> tuple[str, str, str | None]:
    if services.settings.app_env == "test":
        return "degraded", "test email double (no network delivery)", None
    if not services.settings.resend_api_key:
        return "not_configured", "RELIEFMESH_RESEND_API_KEY is not configured; RFQ emails are recorded as failed", None
    dispatches = await services.store.find("email_dispatches")
    if not dispatches:
        return "degraded", "configured; no delivery attempted yet", None
    last = max(dispatches, key=lambda row: row["created_at"])
    if last["status"] == "sent":
        return "ok", f"last delivery accepted by Resend at {last['created_at'][:19]}Z", "LIVE"
    return "error", f"last delivery failed: {last.get('error')}", None


async def check_x402(services: Services) -> tuple[str, str, str | None]:
    settings = services.settings
    if not settings.x402_pay_to:
        return "not_configured", "RELIEFMESH_X402_PAY_TO is not configured", None
    result = await services.hub.fetch("x402_facilitator", f"{settings.x402_facilitator_url.rstrip('/')}/supported")
    if not result.ok:
        return from_result(result, "")
    kinds = [k for k in (result.data or {}).get("kinds", []) if str(k.get("network", "")).startswith("solana:EtWT")]
    if not kinds:
        return "error", "facilitator does not advertise Solana devnet", None
    balance = await services.hub.fetch("solana_devnet", "https://api.devnet.solana.com", method="POST", json_body={
        "jsonrpc": "2.0", "id": 1, "method": "getTokenAccountsByOwner",
        "params": [settings.x402_pay_to, {"mint": "4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU"},
                   {"encoding": "jsonParsed"}]})
    accounts = ((balance.data or {}).get("result") or {}).get("value") or [] if balance.ok else []
    held = sum(a["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"] or 0 for a in accounts)
    return "ok", (f"facilitator supports exact/solana-devnet; treasury {settings.x402_pay_to[:6]}… holds "
                  f"{held:g} devnet USDC"), "SANDBOX"


async def check_crs(services: Services) -> tuple[str, str, str | None]:
    from ..integrations import crs

    settings = services.settings
    result = await crs.login(services.hub, settings.crs_base_url, secret(settings.crs_username),
                             secret(settings.crs_password))
    return from_result(result, "sandbox login token active (TransUnion TruValidate identity verification)")


async def check_gemini(services: Services) -> tuple[str, str, str | None]:
    from ..integrations import gemini

    key, model = secret(services.settings.gemini_api_key), services.settings.gemini_model
    if not key:
        return "not_configured", "RELIEFMESH_GEMINI_API_KEY is not configured (quote assistant hidden)", None
    result = await services.hub.fetch("gemini", f"{gemini.API_BASE}/models/{model}", headers={"x-goog-api-key": key},
                                      retries=0, source_url=f"{gemini.API_BASE}/models/{model}")
    return from_result(result, f"{model} available to the quote-draft assistant (free tier)")


CHECKS: dict[str, tuple[str, str, Check]] = {
    "mongodb": ("MongoDB Atlas", "core", check_mongo),
    "nasa_eonet": ("NASA EONET", "open data", check_eonet),
    "nws": ("NWS alerts", "open data", check_nws),
    "nasa_firms": ("NASA FIRMS", "open data", check_firms),
    "openfema": ("OpenFEMA", "open data", check_fema),
    "ofac": ("OFAC SDN list", "evidence", check_ofac),
    "sam_gov": ("SAM.gov", "evidence", check_sam),
    "usaspending": ("USAspending", "evidence", check_usaspending),
    "openfda": ("openFDA", "evidence", check_openfda),
    "apify": ("Apify", "sponsor", check_apify),
    "crs": ("CRS Credit API sandbox", "sponsor", check_crs),
    "x402": ("Coinbase x402 · Solana devnet", "sponsor", check_x402),
    "gemini": ("Google Gemini", "sponsor", check_gemini),
    "resend": ("Resend email", "core", check_resend),
}


def register_check(key: str, name: str, category: str, check: Check) -> None:
    CHECKS[key] = (name, category, check)


async def run_check(services: Services, key: str, name: str, category: str, check: Check) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        status, detail, provenance = await asyncio.wait_for(check(services), timeout=25)
    except Exception as exc:  # a failing check must render as an error, never as success
        status, detail, provenance = "error", f"{type(exc).__name__}: {exc}", None
    return {"id": key, "name": name, "category": category, "status": status, "detail": detail,
            "provenance": provenance, "latency_ms": int((time.perf_counter() - started) * 1000),
            "checked_at": now_iso()}


@router.get("/v1/integrations/status")
async def integrations_status(refresh: bool = False, services: Services = Depends(get_services)) -> dict:
    cached = services.status_cache.get("status")
    if cached and not refresh and time.monotonic() - cached[0] < CACHE_SECONDS:
        return cached[1]
    results = await asyncio.gather(*(run_check(services, key, *spec) for key, spec in CHECKS.items()))
    payload = {"checked_at": now_iso(), "environment": services.settings.app_env, "integrations": list(results),
               "breakers": services.hub.breaker_status()}
    services.status_cache["status"] = (time.monotonic(), payload)
    return payload
