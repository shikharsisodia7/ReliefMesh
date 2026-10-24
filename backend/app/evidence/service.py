"""Supplier evidence collection.

Every record states its provider, status, provenance (LIVE / CACHED / SANDBOX / ...),
retrieval time, expiry, and a raw reference to what the provider returned. Records
are append-only: a re-check adds a new record and the policy engine reads the latest.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any
from uuid import uuid4

from ..integrations import entity, ofac
from ..integrations.http import AdapterResult, IntegrationHub, iso, parse_iso, utc_now
from ..settings import Settings
from ..store import Store

EVIDENCE_TYPES = ("OFAC_SCREENING", "SAM_REGISTRATION", "FEDERAL_AWARDS", "FDA_RECALLS", "CRS_VERIFICATION")


def _expires(retrieved_at: str | None, hours: int) -> str | None:
    return iso(parse_iso(retrieved_at) + timedelta(hours=hours)) if retrieved_at else None


def make_record(*, organization_id: str, supplier: dict[str, Any], mission_id: str | None, type_: str,
                provider: str, status: str, summary: str, result: AdapterResult, ttl_hours: int,
                confidence: float | None, raw: dict[str, Any], provenance: str | None = None) -> dict[str, Any]:
    retrieved_at = result.retrieved_at
    return {
        "id": str(uuid4()),
        "organization_id": organization_id,
        "mission_id": mission_id,
        "subject_type": "supplier",
        "subject_id": supplier["id"],
        "subject_name": supplier.get("legal_name"),
        "type": type_,
        "provider": provider,
        "status": status,
        "summary": summary,
        "confidence": confidence,
        "source_url": result.source_url,
        "retrieved_at": retrieved_at,
        "expires_at": _expires(retrieved_at, ttl_hours),
        "provenance": provenance or result.provenance or ("BLOCKED_EXTERNAL" if result.status == "BLOCKED_EXTERNAL"
                                                          else "UNAVAILABLE"),
        "adapter_status": result.status,
        "adapter_error": result.error,
        "raw_reference": raw,
        "created_at": iso(utc_now()),
    }


async def check_ofac(hub: IntegrationHub, settings: Settings, name: str) -> tuple[str, str, float | None, dict, AdapterResult]:
    result = await ofac.screen_name(hub, name, settings.ofac_sdn_url, settings.ofac_alt_url)
    if not result.ok:
        return "UNAVAILABLE", result.error or "OFAC list unavailable", None, {}, result
    screen = result.data
    top = screen["matches"][0] if screen["matches"] else None
    if top:
        summary = (f"{screen['status'].replace('_', ' ').lower()}: '{top['matched_name']}' "
                   f"(SDN #{top['ent_num']}, program {top['program']}, score {top['score']})")
    else:
        summary = f"no match among {screen['entries_screened']:,} SDN names and aliases"
    return screen["status"], summary, top["score"] if top else 1.0, screen, result


async def check_sam(hub: IntegrationHub, settings: Settings, name: str) -> tuple[str, str, float | None, dict, AdapterResult]:
    key = settings.sam_gov_api_key.get_secret_value() if settings.sam_gov_api_key else None
    result = await entity.sam_registration(hub, key, name)
    if result.status == "BLOCKED_EXTERNAL":
        return "BLOCKED_EXTERNAL", result.error or "SAM.gov key missing", None, {}, result
    if not result.ok:
        return "UNAVAILABLE", result.error or "SAM.gov unavailable", None, {}, result
    entities = result.data["entities"]
    best = entities[0] if entities else None
    if best and best["similarity"] >= 0.9:
        active = (best.get("registration_status") or "").upper() in {"A", "ACTIVE"}
        status = "MATCH" if active else "INACTIVE"
        summary = (f"{best['legal_business_name']} UEI {best['uei']} status {best['registration_status']} "
                   f"(expires {best.get('registration_expiration')})")
        return status, summary, best["similarity"], result.data, result
    return "NO_MATCH", f"{result.data['total_records']} SAM records, none closely matching", None, result.data, result


async def check_awards(hub: IntegrationHub, name: str) -> tuple[str, str, float | None, dict, AdapterResult]:
    result = await entity.usaspending_awards(hub, name)
    if not result.ok:
        return "UNAVAILABLE", result.error or "USAspending unavailable", None, {}, result
    awards = result.data["awards"]
    if awards:
        total = sum(float(award["amount"] or 0) for award in awards)
        summary = f"{len(awards)} matching federal contract award(s), ${total:,.0f} total (informational)"
        return "FOUND", summary, awards[0]["similarity"], result.data, result
    return "NOT_FOUND", "no matching federal contract awards in the last 6 years (informational)", None, \
        result.data, result


async def check_fda(hub: IntegrationHub, name: str) -> tuple[str, str, float | None, dict, AdapterResult]:
    result = await entity.openfda_recalls(hub, name)
    if not result.ok:
        return "UNAVAILABLE", result.error or "openFDA unavailable", None, {}, result
    recalls = result.data["recalls"]
    strong = [row for row in recalls if row["similarity"] >= 0.9]
    if strong:
        first = strong[0]
        summary = (f"{len(strong)} enforcement report(s) naming '{first['recalling_firm']}', e.g. "
                   f"{first['recall_number']} ({first['classification']}, {first['status']})")
        return "POTENTIAL_MATCH", summary, first["similarity"], result.data, result
    if recalls:
        return "WEAK_MATCH", f"{len(recalls)} report(s) with only partial firm-name overlap", \
            recalls[0]["similarity"], result.data, result
    return "NO_MATCH", "no device, drug, or food enforcement reports", 1.0, result.data, result


async def collect_supplier_evidence(store: Store, hub: IntegrationHub, settings: Settings, *,
                                    organization_id: str, supplier: dict[str, Any],
                                    mission_id: str | None, crs_check: Any = None) -> list[dict[str, Any]]:
    name = supplier.get("legal_name")
    if not name:
        return []
    checks = await asyncio.gather(
        check_ofac(hub, settings, name),
        check_sam(hub, settings, name),
        check_awards(hub, name),
        check_fda(hub, name),
        return_exceptions=True,
    )
    specs = [
        ("OFAC_SCREENING", "OFAC", settings.ofac_evidence_ttl_hours),
        ("SAM_REGISTRATION", "SAM_GOV", settings.sam_evidence_ttl_hours),
        ("FEDERAL_AWARDS", "USASPENDING", settings.sam_evidence_ttl_hours),
        ("FDA_RECALLS", "OPENFDA", settings.fda_evidence_ttl_hours),
    ]
    records = []
    for (type_, provider, ttl), outcome in zip(specs, checks, strict=True):
        if isinstance(outcome, BaseException):
            failure = AdapterResult(provider.lower(), "UNAVAILABLE", error=f"{type(outcome).__name__}: {outcome}")
            records.append(make_record(
                organization_id=organization_id, supplier=supplier, mission_id=mission_id, type_=type_,
                provider=provider, status="UNAVAILABLE", summary=failure.error or "check failed",
                result=failure, ttl_hours=ttl, confidence=None, raw={},
            ))
            continue
        status, summary, confidence, raw, result = outcome
        records.append(make_record(
            organization_id=organization_id, supplier=supplier, mission_id=mission_id, type_=type_,
            provider=provider, status=status, summary=summary, result=result, ttl_hours=ttl,
            confidence=confidence, raw=raw,
        ))
    if crs_check is not None:
        crs_record = await crs_check(supplier)
        if crs_record:
            records.append(crs_record | {"organization_id": organization_id, "mission_id": mission_id})
    for record in records:
        await store.insert("evidence", record)
    return records


async def supplier_evidence(store: Store, organization_id: str, supplier_id: str) -> list[dict[str, Any]]:
    rows = await store.find("evidence", organization_id=organization_id, subject_id=supplier_id)
    return sorted(rows, key=lambda row: row["created_at"], reverse=True)
