"""Entity evidence adapters: SAM.gov registration, USAspending award history, openFDA recalls.

What each source does and does NOT prove:
- SAM.gov: an entity is registered with the federal government. Not inventory, quality, or capacity.
- USAspending: historical federal awards. Informational; ReliefMesh does not derive a trust score.
- openFDA: enforcement/recall reports naming a recalling firm. Text matches need human review.
"""

from __future__ import annotations

from datetime import date, timedelta
from difflib import SequenceMatcher
from typing import Any

from .http import AdapterResult, IntegrationHub
from .ofac import normalize_name

SAM_URL = "https://api.sam.gov/entity-information/v3/entities"
USASPENDING_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
OPENFDA_BASE = "https://api.fda.gov"
FDA_DATASETS = ("device", "drug", "food")
# Personal SAM.gov keys allow very few requests a day (10 without a SAM role), so lookups are cached for a day
# per name and a 429 is never retried: it means the daily quota is spent, not a transient error.
SAM_CACHE_SECONDS = 24 * 3600
SAM_QUOTA_MESSAGE = "SAM.gov daily API quota reached for this key; registration lookups resume after the daily reset"


def name_similarity(a: str, b: str) -> float:
    left, right = normalize_name(a), normalize_name(b)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    ratio = SequenceMatcher(None, left, right).ratio()
    left_tokens, right_tokens = set(left.split()), set(right.split())
    containment = len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))
    return round(max(ratio, containment * 0.95 if min(len(left_tokens), len(right_tokens)) >= 2 else ratio), 3)


async def sam_registration(hub: IntegrationHub, api_key: str | None, legal_name: str,
                           uei: str | None = None) -> AdapterResult:
    public_url = f"{SAM_URL}?legalBusinessName={legal_name}"
    if not api_key:
        return hub.blocked("sam_gov", "RELIEFMESH_SAM_GOV_API_KEY is not configured", public_url)
    params: dict[str, Any] = {"api_key": api_key, "includeSections": "entityRegistration,coreData"}
    if uei:
        params["ueiSAM"] = uei
    else:
        params["legalBusinessName"] = legal_name
    result = await hub.fetch(
        "sam_gov", SAM_URL, params=params, cache_key=f"{uei or normalize_name(legal_name)}",
        fresh_seconds=SAM_CACHE_SECONDS, timeout=20, retries=0, source_url=public_url,
    )
    if not result.ok and (result.error or "").startswith("HTTP 429"):
        result.error = SAM_QUOTA_MESSAGE
    if result.ok:
        entities = []
        for row in (result.data or {}).get("entityData", []) or []:
            registration = row.get("entityRegistration", {}) or {}
            core = row.get("coreData", {}) or {}
            address = core.get("physicalAddress", {}) or {}
            business_types = (core.get("businessTypes", {}) or {}).get("businessTypeList", []) or []
            naics = ((row.get("assertions", {}) or {}).get("goodsAndServices", {}) or {}).get("naicsList", []) or []
            entities.append({
                "uei": registration.get("ueiSAM"),
                "legal_business_name": registration.get("legalBusinessName"),
                "registration_status": registration.get("registrationStatus"),
                "registration_expiration": registration.get("registrationExpirationDate"),
                "cage_code": registration.get("cageCode"),
                "address": {k: address.get(k) for k in ("addressLine1", "city", "stateOrProvinceCode", "zipCode",
                                                         "countryCode")},
                "business_types": [b.get("businessTypeDesc") for b in business_types if isinstance(b, dict)],
                "naics": [n.get("naicsCode") for n in naics if isinstance(n, dict)],
                "similarity": name_similarity(legal_name, registration.get("legalBusinessName") or ""),
            })
        entities.sort(key=lambda row: -row["similarity"])
        result.data = {"total_records": (result.data or {}).get("totalRecords", 0), "entities": entities[:5]}
    return result


async def usaspending_awards(hub: IntegrationHub, recipient_name: str, years: int = 6) -> AdapterResult:
    start = (date.today() - timedelta(days=365 * years)).isoformat()
    body = {
        "filters": {
            "recipient_search_text": [recipient_name],
            "award_type_codes": ["A", "B", "C", "D"],
            "time_period": [{"start_date": start, "end_date": date.today().isoformat()}],
        },
        "fields": ["Award ID", "Recipient Name", "Award Amount", "Awarding Agency", "Start Date", "Description",
                   "generated_internal_id"],
        "limit": 10, "page": 1, "sort": "Award Amount", "order": "desc",
    }
    result = await hub.fetch(
        "usaspending", USASPENDING_URL, method="POST", json_body=body,
        cache_key=f"{normalize_name(recipient_name)}:{years}", fresh_seconds=3600, timeout=25,
        source_url=f"https://www.usaspending.gov/search?recipient={recipient_name}",
    )
    if result.ok:
        awards = []
        for row in (result.data or {}).get("results", []):
            similarity = name_similarity(recipient_name, row.get("Recipient Name") or "")
            awards.append({
                "award_id": row.get("Award ID"),
                "recipient_name": row.get("Recipient Name"),
                "amount": row.get("Award Amount"),
                "agency": row.get("Awarding Agency"),
                "start_date": row.get("Start Date"),
                "description": row.get("Description"),
                "similarity": similarity,
                "source_url": f"https://www.usaspending.gov/award/{row.get('generated_internal_id')}",
            })
        # The search is full-text, so keep only recipients whose names genuinely resemble the supplier.
        matching = [award for award in awards if award["similarity"] >= 0.85]
        result.data = {"awards": matching, "unmatched_results": len(awards) - len(matching)}
    return result


async def openfda_recalls(hub: IntegrationHub, firm_name: str) -> AdapterResult:
    quoted = firm_name.replace('"', "").strip()
    found: list[dict[str, Any]] = []
    errors: list[str] = []
    provenance = "LIVE"
    retrieved_at = None
    for dataset in FDA_DATASETS:
        url = f"{OPENFDA_BASE}/{dataset}/enforcement.json"
        result = await hub.fetch(
            "openfda", url, params={"search": f'recalling_firm:"{quoted}"', "limit": 10},
            cache_key=f"{dataset}:{normalize_name(firm_name)}", fresh_seconds=3600, timeout=15,
            not_found_ok=True, source_url=f'{url}?search=recalling_firm:"{quoted}"',
        )
        if not result.ok:
            errors.append(f"{dataset}: {result.error}")
            continue
        provenance = "CACHED" if result.provenance == "CACHED" else provenance
        retrieved_at = result.retrieved_at
        for row in (result.data or {}).get("results", []) or []:
            found.append({
                "dataset": dataset,
                "recall_number": row.get("recall_number"),
                "recalling_firm": row.get("recalling_firm"),
                "classification": row.get("classification"),
                "status": row.get("status"),
                "product_description": (row.get("product_description") or "")[:240],
                "reason_for_recall": (row.get("reason_for_recall") or "")[:240],
                "recall_initiation_date": row.get("recall_initiation_date"),
                "similarity": name_similarity(firm_name, row.get("recalling_firm") or ""),
            })
    if len(errors) == len(FDA_DATASETS):
        return AdapterResult("openfda", "UNAVAILABLE", source_url=OPENFDA_BASE, error="; ".join(errors))
    found.sort(key=lambda row: -row["similarity"])
    return AdapterResult(
        "openfda", "OK", {"recalls": found[:10], "partial_errors": errors}, provenance,
        f'{OPENFDA_BASE}/device/enforcement.json?search=recalling_firm:"{quoted}"', retrieved_at,
    )
