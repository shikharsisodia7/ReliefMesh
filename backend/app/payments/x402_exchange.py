"""x402 machine-to-machine payments for premium evidence, settled on Solana devnet.

Seller: the "ReliefMesh Evidence Exchange" resource `GET /x402/v1/entity-dossier?name=...` is gated
by the official Coinbase x402 FastAPI middleware. Without payment it answers HTTP 402 with payment
requirements (exact scheme, USDC on Solana devnet, payTo = the exchange treasury). The x402.org
facilitator verifies and settles the signed transfer on-chain and sponsors fees.

Buyer: ReliefMesh's procurement runtime holds a separate devnet wallet and pays with the official
x402 client (`x402HttpxClient` + `ExactSvmScheme`). Each purchase is bounded by a per-organization
daily data budget, de-duplicated (no re-purchase of the same entity within a cooldown), serialized
per organization, and recorded with its on-chain transaction signature in the audit chain.

Only Solana DEVNET test USDC is used. No procurement funds or real money move through x402.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query

from ..core import Services, audit, current_user, get_services, new_id, now_iso, secret
from ..integrations import entity, ofac
from ..integrations.http import canonical_json
from ..integrations.ofac import normalize_name

DOSSIER_PATH = "/x402/v1/entity-dossier"
REUSE_MINUTES = 15
router = APIRouter()
_purchase_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


def _svm():
    from x402.mechanisms.svm.constants import SOLANA_DEVNET_CAIP2, USDC_DEVNET_ADDRESS
    return SOLANA_DEVNET_CAIP2, USDC_DEVNET_ADDRESS


def build_payment_middleware(services: Services):
    """Create the official x402 FastAPI middleware for the dossier route (lazy facilitator sync)."""

    from x402 import x402ResourceServer
    from x402.http import FacilitatorConfig, HTTPFacilitatorClient, PaymentOption, RouteConfig
    from x402.http.middleware.fastapi import payment_middleware
    from x402.mechanisms.svm.exact import ExactSvmServerScheme

    network, _ = _svm()
    settings = services.settings
    facilitator = HTTPFacilitatorClient(FacilitatorConfig(url=settings.x402_facilitator_url, timeout=60))
    server = x402ResourceServer(facilitator)
    server.register(network, ExactSvmServerScheme())
    routes = {
        f"GET {DOSSIER_PATH}": RouteConfig(
            accepts=PaymentOption(scheme="exact", pay_to=settings.x402_pay_to, price=f"${settings.x402_price_usd}",
                                  network=network, max_timeout_seconds=120),
            description="Live, signed public-records compliance dossier (OFAC SDN, openFDA, USAspending)",
            mime_type="application/json",
            service_name="ReliefMesh Evidence Exchange",
            tags=["compliance", "sanctions", "procurement"],
        )
    }
    # The SDK only retries initialization lazily when sync_facilitator_on_start is True; transient facilitator
    # outages are logged and retried on the next paid request, so the API itself stays up.
    return payment_middleware(routes, server, sync_facilitator_on_start=True)


async def compile_dossier(services: Services, name: str) -> dict[str, Any]:
    settings = services.settings
    screen, recalls, awards = await asyncio.gather(
        ofac.screen_name(services.hub, name, settings.ofac_sdn_url, settings.ofac_alt_url),
        entity.openfda_recalls(services.hub, name),
        entity.usaspending_awards(services.hub, name),
    )
    sections = {
        "ofac_sdn": {"status": screen.status, "provenance": screen.provenance, "retrieved_at": screen.retrieved_at,
                     "source_url": screen.source_url, "result": screen.data if screen.ok else None,
                     "error": screen.error},
        "openfda_enforcement": {"status": recalls.status, "provenance": recalls.provenance,
                                "retrieved_at": recalls.retrieved_at, "source_url": recalls.source_url,
                                "result": recalls.data if recalls.ok else None, "error": recalls.error},
        "usaspending_awards": {"status": awards.status, "provenance": awards.provenance,
                               "retrieved_at": awards.retrieved_at, "source_url": awards.source_url,
                               "result": awards.data if awards.ok else None, "error": awards.error},
    }
    body = {
        "entity_name": name,
        "normalized_name": normalize_name(name),
        "generated_at": now_iso(),
        "issuer": "ReliefMesh Evidence Exchange",
        "sections": sections,
        "disclaimer": "Name-based public-record screening. A fuzzy sanctions match requires human review and does "
                      "not establish identity.",
    }
    digest = hashlib.sha256(canonical_json(body).encode()).hexdigest()
    signature, signer = None, None
    treasury_key = secret(settings.x402_treasury_private_key)
    if treasury_key:
        from solders.keypair import Keypair

        keypair = Keypair.from_base58_string(treasury_key)
        signature = str(keypair.sign_message(digest.encode()))
        signer = str(keypair.pubkey())
    return {**body, "dossier_sha256": digest, "signature_ed25519": signature, "signer": signer}


@router.get(DOSSIER_PATH)
async def entity_dossier(name: str = Query(min_length=2, max_length=200),
                         services: Services = Depends(get_services)) -> dict:
    """Reached only after the x402 middleware has verified payment (when payments are configured)."""

    if not services.settings.x402_pay_to:
        raise HTTPException(status_code=503, detail="BLOCKED_EXTERNAL: x402 payments are not configured")
    return await compile_dossier(services, " ".join(name.split()))


def decode_settlement(response_headers: Any) -> dict[str, Any] | None:
    from x402.http.utils import decode_payment_response_header

    header = response_headers.get("PAYMENT-RESPONSE") or response_headers.get("X-PAYMENT-RESPONSE")
    if not header:
        return None
    settle = decode_payment_response_header(header)
    return settle.model_dump(by_alias=False)


async def pay_for_dossier(services: Services, name: str) -> tuple[dict[str, Any], dict[str, Any], int]:
    """Buy the dossier through the real HTTP 402 flow. Returns (dossier, settlement, http_status)."""

    from solders.keypair import Keypair
    from x402 import x402Client
    from x402.http.clients.httpx import x402HttpxClient
    from x402.mechanisms.svm.exact import register_exact_svm_client
    from x402.mechanisms.svm.signers import KeypairSigner

    network, _ = _svm()
    settings = services.settings
    signer = KeypairSigner(Keypair.from_base58_string(secret(settings.x402_buyer_private_key) or ""))
    client = x402Client()
    register_exact_svm_client(client, signer, networks=[network])
    url = f"{settings.public_api_url.rstrip('/')}{DOSSIER_PATH}?{urlencode({'name': name})}"
    async with x402HttpxClient(client, timeout=120) as http:
        response = await http.get(url)
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Evidence Exchange returned HTTP {response.status_code}: "
                                                    f"{response.text[:200]}")
    settlement = decode_settlement(response.headers)
    if not settlement or not settlement.get("success"):
        raise HTTPException(status_code=502, detail="Payment settlement was not confirmed by the facilitator")
    return response.json(), settlement, response.status_code


def atomic_usdc(price_usd: str) -> int:
    return int(Decimal(price_usd) * Decimal(1_000_000))


async def purchase_supplier_dossier(services: Services, mission: dict[str, Any], supplier: dict[str, Any],
                                    actor: dict[str, Any], buyer=pay_for_dossier) -> dict[str, Any]:
    settings = services.settings
    if not (settings.x402_pay_to and settings.x402_buyer_private_key):
        raise HTTPException(status_code=503, detail="BLOCKED_EXTERNAL: x402 buyer wallet or payTo is not configured")
    name = supplier.get("legal_name")
    if not name:
        raise HTTPException(status_code=422, detail="Supplier has no legal business name to research")
    org = mission["organization_id"]
    key = normalize_name(name)
    async with _purchase_locks[org]:  # one purchase at a time per org: no double-click double pay
        payments = await services.store.find("payments", organization_id=org)
        cutoff = (datetime.now(UTC) - timedelta(minutes=REUSE_MINUTES)).isoformat()
        recent = [p for p in payments if p["subject_key"] == key and p["created_at"] >= cutoff and p["status"] == "settled"]
        if recent:
            return {"payment": recent[-1], "reused": True,
                    "evidence": await services.store.get("evidence", recent[-1]["evidence_id"])}
        today = datetime.now(UTC).date().isoformat()
        spent = sum(int(p["amount_atomic"]) for p in payments if p["created_at"][:10] == today and p["status"] == "settled")
        price = atomic_usdc(settings.x402_price_usd)
        if spent + price > atomic_usdc(settings.x402_daily_cap_usd):
            raise HTTPException(status_code=409, detail="Daily x402 data budget for this organization is exhausted")
        dossier, settlement, _ = await buyer(services, name)
        transaction = settlement.get("transaction")
        if not transaction or any(p.get("transaction") == transaction for p in payments):
            raise HTTPException(status_code=409, detail="Duplicate or missing settlement transaction rejected")
        network, asset = _svm()
        ofac_status = ((dossier.get("sections") or {}).get("ofac_sdn") or {}).get("result") or {}
        evidence = {
            "id": new_id(), "organization_id": org, "mission_id": mission["id"], "subject_type": "supplier",
            "subject_id": supplier["id"], "subject_name": name, "type": "PAID_DOSSIER",
            "provider": "X402_EVIDENCE_EXCHANGE", "status": ofac_status.get("status", "COMPILED"),
            "summary": f"Signed dossier bought via x402 for {settings.x402_price_usd} devnet USDC "
                       f"(tx {transaction[:12]}…); informational, does not change policy by itself.",
            "confidence": None, "source_url": f"https://explorer.solana.com/tx/{transaction}?cluster=devnet",
            "retrieved_at": dossier.get("generated_at"), "expires_at": None, "provenance": "LIVE",
            "adapter_status": "OK", "adapter_error": None,
            "raw_reference": {"dossier_sha256": dossier.get("dossier_sha256"), "signer": dossier.get("signer"),
                              "signature_ed25519": dossier.get("signature_ed25519"), "dossier": dossier},
            "created_at": now_iso(),
        }
        await services.store.insert("evidence", evidence)
        payment = {
            "id": new_id(), "organization_id": org, "mission_id": mission["id"], "supplier_id": supplier["id"],
            "subject_name": name, "subject_key": key, "resource": DOSSIER_PATH, "protocol": "x402",
            "scheme": "exact", "network": network, "network_label": "solana-devnet", "asset": asset,
            "asset_symbol": "USDC", "amount_atomic": str(price), "amount_display": f"{settings.x402_price_usd} USDC",
            "pay_to": settings.x402_pay_to, "payer": settlement.get("payer"), "transaction": transaction,
            "explorer_url": f"https://explorer.solana.com/tx/{transaction}?cluster=devnet",
            "facilitator": settings.x402_facilitator_url, "status": "settled", "verified": True,
            "dossier_sha256": dossier.get("dossier_sha256"), "evidence_id": evidence["id"],
            "actor_id": actor["id"], "created_at": now_iso(),
        }
        await services.store.insert("payments", payment)
        await audit("payment.x402.settled", actor["id"], org, mission["id"], "payment", payment["id"], services, {
            "transaction": transaction, "network": network, "amount": payment["amount_display"],
            "resource": DOSSIER_PATH, "payer": payment["payer"], "pay_to": payment["pay_to"],
            "dossier_sha256": payment["dossier_sha256"],
        })
        return {"payment": payment, "reused": False, "evidence": evidence}


def dossier_hash_matches(dossier: dict[str, Any]) -> bool:
    body = {k: v for k, v in dossier.items() if k not in {"dossier_sha256", "signature_ed25519", "signer"}}
    return hashlib.sha256(canonical_json(body).encode()).hexdigest() == dossier.get("dossier_sha256")


async def payments_for_mission(services: Services, mission_id: str) -> list[dict[str, Any]]:
    return sorted(await services.store.find("payments", mission_id=mission_id), key=lambda row: row["created_at"],
                  reverse=True)


PROOF_SUBJECT = "ReliefMesh x402 devnet proof"
PROOF_COOLDOWN_MINUTES = 10
PROOF_DAILY_LIMIT = 10
_proof_lock = asyncio.Lock()


def _proof_view(row: dict[str, Any] | None) -> dict[str, Any]:
    notice = ("DEVNET TEST PAYMENT: a real HTTP 402 payment settled in test USDC on Solana devnet. It proves "
              "machine-to-machine payment works; no supplier is paid and no real money moves.")
    return {"proof": row, "notice": notice, "provenance": "SANDBOX"}


async def latest_proof(services: Services) -> dict[str, Any]:
    rows = sorted(await services.store.find("sandbox_proofs", kind="x402"), key=lambda r: r["created_at"])
    return _proof_view(rows[-1] if rows else None)


async def run_proof(services: Services, actor: dict[str, Any], buyer=pay_for_dossier) -> dict[str, Any]:
    """Signed-in, judge-triggered devnet payment. Throttled per user and globally; every run is audited."""
    settings = services.settings
    if not (settings.x402_pay_to and settings.x402_buyer_private_key):
        raise HTTPException(status_code=503, detail="BLOCKED_EXTERNAL: x402 buyer wallet or payTo is not configured")
    async with _proof_lock:
        rows = sorted(await services.store.find("sandbox_proofs", kind="x402"), key=lambda r: r["created_at"])
        cutoff = (datetime.now(UTC) - timedelta(minutes=PROOF_COOLDOWN_MINUTES)).isoformat()
        if rows and rows[-1]["created_at"] >= cutoff:
            return {**_proof_view(rows[-1]), "reused": True}
        today = datetime.now(UTC).date().isoformat()
        if sum(1 for r in rows if r["created_at"][:10] == today) >= PROOF_DAILY_LIMIT:
            raise HTTPException(status_code=429, detail="Daily devnet proof limit reached; the latest proof is shown")
        dossier, settlement, _ = await buyer(services, PROOF_SUBJECT)
        transaction = settlement.get("transaction")
        if not transaction or any(r.get("transaction") == transaction for r in rows):
            raise HTTPException(status_code=409, detail="Duplicate or missing settlement transaction rejected")
        network, asset = _svm()
        row = {
            "id": new_id(), "kind": "x402", "transaction": transaction, "network": network,
            "network_label": "solana-devnet", "asset": asset, "amount_display": f"{settings.x402_price_usd} USDC",
            "payer": settlement.get("payer"), "pay_to": settings.x402_pay_to, "resource": DOSSIER_PATH,
            "facilitator": settings.x402_facilitator_url, "dossier_sha256": dossier.get("dossier_sha256"),
            "explorer_url": f"https://explorer.solana.com/tx/{transaction}?cluster=devnet", "created_at": now_iso(),
        }
        row["actor_id"] = actor["id"]
        await services.store.insert("sandbox_proofs", row)
        await audit("sandbox.x402_proof.settled", actor["id"], None, None, "sandbox_proof", row["id"], services,
                    {"transaction": transaction, "network": network, "amount": row["amount_display"],
                     "payer": row["payer"], "pay_to": row["pay_to"]})
        return {**_proof_view(row), "reused": False}


@router.get("/v1/sandbox/x402-proof")
async def get_x402_proof(services: Services = Depends(get_services)) -> dict[str, Any]:
    return await latest_proof(services)


@router.post("/v1/sandbox/x402-proof")
async def post_x402_proof(user: dict = Depends(current_user), services: Services = Depends(get_services)) -> dict:
    services.assist_limiter.check(f"x402-proof:{user['id']}")  # per-user floor on top of the global cooldown
    return await run_proof(services, user)
