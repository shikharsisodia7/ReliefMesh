"""CRS Credit API sandbox: TransUnion TruValidate identity verification of a supplier's authorized signer.

Sandbox rule: only CRS's published test personas may be sent. Any input that does not match a
persona is forwarded to the real vendor, so ReliefMesh never sends a real supplier's personal data.
Only suppliers whose signer is bound to a CRS sandbox persona (the labeled TEST suppliers) are
checked; results are recorded with SANDBOX provenance.

What it proves: whether the signer's name, SSN, DOB and address belong together and carry no
deceased / mismatch / fraud-alert flags. It does NOT prove inventory, product quality, bank
ownership, or a business's ability to fulfill.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Awaitable, Callable
from uuid import uuid4

from .http import AdapterResult, IntegrationHub, iso, utc_now

IDV_PATH = "/transunion/identity-manager-verification/basic"

# Fake identities published by CRS for the Cal Hacks 13.0 sandbox (crs-calhacks-mcp-server test data).
SANDBOX_PERSONAS: dict[str, dict[str, Any]] = {
    "P01": {"name": "MARGARET OKAFOR", "expected": "PASS", "body": {
        "firstName": "MARGARET", "lastName": "OKAFOR", "ssn": "666701001", "dob": "1984-03-14",
        "street1": "1420 WILLOW CREEK DR", "city": "SAN JOSE", "state": "CA", "zip": "95125"}},
    "P02": {"name": "DANIEL WHITFIELD", "expected": "PASS", "body": {
        "firstName": "DANIEL", "lastName": "WHITFIELD", "ssn": "666701002", "dob": "1972-11-02",
        "street1": "88 LAKESHORE BLVD", "city": "AUSTIN", "state": "TX", "zip": "78746"}},
    "P12": {"name": "VICTOR ANAND", "expected": "FAIL", "body": {
        "firstName": "VICTOR", "lastName": "ANAND", "ssn": "666701012", "dob": "1968-08-08",
        "street1": "55 WATER ST FL 20", "city": "NEW YORK", "state": "NY", "zip": "10041"}},
    "P19": {"name": "GRACE NAKAMURA", "expected": "PASS", "body": {
        "firstName": "GRACE", "lastName": "NAKAMURA", "ssn": "666701019", "dob": "1976-09-16",
        "street1": "1850 SOLANO AVE", "city": "BERKELEY", "state": "CA", "zip": "94707"}},
}


class CrsSession:
    """Caches one bearer token. A failed login is never retried in-process (sandbox lockout risk)."""

    def __init__(self) -> None:
        self.token: str | None = None
        self.login_failure: str | None = None


def _session(hub: IntegrationHub) -> CrsSession:
    session = hub.memo_get("crs:session", 10**9)
    if session is None:
        session = CrsSession()
        hub.memo_set("crs:session", session)
    return session


async def login(hub: IntegrationHub, base_url: str, username: str | None, password: str | None,
                force: bool = False) -> AdapterResult:
    url = f"{base_url}/users/login"
    if not (username and password):
        return hub.blocked("crs", "RELIEFMESH_CRS_USERNAME / RELIEFMESH_CRS_PASSWORD are not configured", url)
    session = _session(hub)
    if session.login_failure:
        return AdapterResult("crs", "UNAVAILABLE", source_url=url, error=session.login_failure)
    if session.token and not force:
        return AdapterResult("crs", "OK", session.token, "SANDBOX", url, iso(utc_now()))
    result = await hub.fetch("crs", url, method="POST", json_body={"username": username, "password": password},
                             retries=0, timeout=20, provenance="SANDBOX")
    if not result.ok or not (result.data or {}).get("token"):
        session.login_failure = f"CRS login failed ({result.error or 'no token returned'}); not retrying"
        return AdapterResult("crs", "UNAVAILABLE", source_url=url, error=session.login_failure)
    session.token = result.data["token"]
    return AdapterResult("crs", "OK", session.token, "SANDBOX", url, result.retrieved_at)


async def verify_identity(hub: IntegrationHub, base_url: str, username: str | None, password: str | None,
                          persona_id: str) -> AdapterResult:
    persona = SANDBOX_PERSONAS.get(persona_id)
    url = f"{base_url}{IDV_PATH}"
    if not persona:
        return AdapterResult("crs", "UNAVAILABLE", source_url=url,
                             error="Not a CRS sandbox persona; real personal data is never sent to the sandbox")
    auth = await login(hub, base_url, username, password)
    if not auth.ok:
        return auth
    for attempt in range(2):
        result = await hub.fetch("crs", url, method="POST", json_body=persona["body"], retries=1, timeout=30,
                                 headers={"Authorization": f"Bearer {auth.data}"}, provenance="SANDBOX")
        if result.ok or attempt or "401" not in (result.error or ""):
            break
        auth = await login(hub, base_url, username, password, force=True)  # expired token: refresh once
        if not auth.ok:
            return auth
    if not result.ok:
        return result
    data = result.data or {}
    if data.get("codes"):  # CRS error envelope
        return AdapterResult("crs", "UNAVAILABLE", source_url=url, error=f"CRS {data.get('codes')}: {data.get('messages')}")
    add_ons = data.get("addOnProducts") or [{}]
    messages = ((add_ons[0] or {}).get("idManagerVerification") or {}).get("messages") or []
    result.data = {
        "persona_id": persona_id,
        "signer": persona["name"],
        "verified": not messages,
        "messages": [{"code": m.get("code"), "text": m.get("text")} for m in messages if isinstance(m, dict)],
        "product": "TransUnion TruValidate (identity-manager-verification/basic)",
    }
    return result


def crs_checker(services: Any) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]] | None:
    from ..core import secret

    settings = services.settings
    username, password = secret(settings.crs_username), secret(settings.crs_password)
    if not (username and password):
        return None

    async def check(supplier: dict[str, Any]) -> dict[str, Any] | None:
        signer = supplier.get("authorized_signer") or {}
        persona_id = signer.get("crs_persona_id")
        if not persona_id:
            return None  # only sandbox-persona signers are ever sent to CRS
        result = await verify_identity(services.hub, settings.crs_base_url, username, password, persona_id)
        if result.ok:
            verified = result.data["verified"]
            texts = "; ".join(f"{m['code']}: {m['text']}" for m in result.data["messages"])
            status = "PASS" if verified else "FAIL"
            summary = (f"Signer {result.data['signer']} identity verified by TransUnion TruValidate (CRS sandbox)"
                       if verified else f"Signer {result.data['signer']} failed identity verification: {texts}")
        else:
            status, summary = "UNAVAILABLE", result.error or "CRS check failed"
        retrieved = result.retrieved_at or iso(utc_now())
        return {
            "id": str(uuid4()), "subject_type": "supplier", "subject_id": supplier["id"],
            "subject_name": supplier.get("legal_name"), "type": "CRS_VERIFICATION", "provider": "CRS",
            "status": status, "summary": summary, "confidence": None,
            "source_url": f"{settings.crs_base_url}{IDV_PATH}", "retrieved_at": retrieved,
            "expires_at": iso(utc_now() + timedelta(hours=settings.crs_evidence_ttl_hours)),
            "provenance": "SANDBOX", "adapter_status": result.status, "adapter_error": result.error,
            "raw_reference": result.data if result.ok else {}, "created_at": iso(utc_now()),
        }

    return check
