"""Deterministic procurement policy engine.

The engine is a pure function of persisted state (mission, quotes, supplier evidence,
human review actions, clock). It reads only structured fields: free-text supplier
input such as quote restrictions or company descriptions is never interpreted, so it
cannot grant itself eligibility. No language model participates in any decision here.

Gate semantics:
  PASS / WARN          -> quote may be sent to the optimizer
  NEEDS_REVIEW / BLOCK -> quote is withheld; supplier receives zero allocation
Missing or unavailable critical evidence is NEEDS_REVIEW, never PASS.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

STATUS_ORDER = {"PASS": 0, "WARN": 1, "NEEDS_REVIEW": 2, "BLOCK": 3}
ELIGIBLE = {"PASS", "WARN"}
MAX_UNIT_PRICE = Decimal("1000000000")
MAX_QUANTITY = 1_000_000


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def worst(statuses: list[str]) -> str:
    return max(statuses, key=lambda status: STATUS_ORDER[status]) if statuses else "PASS"


@dataclass(frozen=True)
class EvidenceTTL:
    ofac_hours: int = 24
    sam_hours: int = 24 * 7
    fda_hours: int = 24 * 7
    crs_hours: int = 24 * 7


def decision(rule_id: str, status: str, severity: str, reason: str, subject: str, subject_id: str,
             evidence_ids: list[str] | None = None, **extra: Any) -> dict[str, Any]:
    return {
        "rule_id": rule_id, "status": status, "severity": severity, "reason": reason,
        "subject": subject, "subject_id": subject_id, "evidence_ids": evidence_ids or [], **extra,
    }


def latest_by_type(evidence: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    # The most recent *check* wins (even a failed one), so a later failure is never masked
    # by an older pass; staleness is judged separately from the record's retrieved_at.
    latest: dict[str, dict[str, Any]] = {}
    for record in sorted(evidence, key=lambda row: row["created_at"]):
        latest[record["type"]] = record
    return latest


def review_state(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    """Fold a supplier's review actions (oldest first) into its current manual state."""

    state: dict[str, Any] = {"blocked": False, "block_reason": None, "block_review_id": None, "clearances": {}}
    for review in sorted(reviews, key=lambda row: row["created_at"]):
        if review["action"] == "block":
            state.update(blocked=True, block_reason=review["reason"], block_review_id=review["id"])
        elif review["action"] == "unblock":
            state.update(blocked=False, block_reason=None, block_review_id=None)
        elif review["action"] == "clear" and review.get("rule_id"):
            state["clearances"][review["rule_id"]] = review
    return state


def _cleared(state: dict[str, Any], rule_id: str, evidence_id: str) -> dict[str, Any] | None:
    """A clearance binds to the exact evidence reviewed; new evidence needs a fresh review."""

    clearance = state["clearances"].get(rule_id)
    if clearance and evidence_id in clearance.get("evidence_ids", []):
        return clearance
    return None


def _stale(record: dict[str, Any], hours: int, now: datetime) -> bool:
    retrieved = _dt(record.get("retrieved_at"))
    return retrieved is None or (now - retrieved).total_seconds() > hours * 3600


def supplier_decisions(supplier: dict[str, Any], evidence: list[dict[str, Any]],
                       reviews: list[dict[str, Any]], now: datetime, ttl: EvidenceTTL,
                       regulated_goods: bool) -> list[dict[str, Any]]:
    sid = supplier["id"]
    out: list[dict[str, Any]] = []
    state = review_state(reviews)
    latest = latest_by_type(evidence)

    if state["blocked"]:
        out.append(decision("SUPPLIER_BLOCKED", "BLOCK", "CRITICAL",
                            f"Blocked by a coordinator: {state['block_reason']}", "supplier", sid,
                            review_id=state["block_review_id"]))

    if not supplier.get("legal_name"):
        out.append(decision("SUPPLIER_IDENTITY_MISSING", "NEEDS_REVIEW", "HIGH",
                            "Supplier has not provided a legal business name, so it cannot be screened.",
                            "supplier", sid))

    # Sanctions screening is critical evidence: absent, failed, or stale means a human must look.
    ofac = latest.get("OFAC_SCREENING")
    if not ofac:
        out.append(decision("SANCTIONS_SCREENING_MISSING", "NEEDS_REVIEW", "HIGH",
                            "No OFAC sanctions screening on record. Missing evidence never counts as a pass.",
                            "supplier", sid))
    elif ofac["status"] in {"UNAVAILABLE", "BLOCKED_EXTERNAL"}:
        out.append(decision("SANCTIONS_SCREENING_INCOMPLETE", "NEEDS_REVIEW", "HIGH",
                            f"OFAC screening could not complete: {ofac.get('summary')}", "supplier", sid,
                            [ofac["id"]]))
    elif _stale(ofac, ttl.ofac_hours, now):
        out.append(decision("SANCTIONS_SCREENING_STALE", "NEEDS_REVIEW", "HIGH",
                            f"OFAC screening is older than {ttl.ofac_hours}h; re-run evidence checks.",
                            "supplier", sid, [ofac["id"]]))
    elif ofac["status"] == "EXACT_MATCH":
        cleared = _cleared(state, "SANCTIONS_EXACT_MATCH", ofac["id"])
        if cleared:
            out.append(decision("SANCTIONS_EXACT_MATCH", "WARN", "HIGH",
                                f"Exact SDN name match cleared by a reviewer: {cleared['reason']}",
                                "supplier", sid, [ofac["id"]], review_id=cleared["id"]))
        else:
            out.append(decision("SANCTIONS_EXACT_MATCH", "BLOCK", "CRITICAL",
                                f"Name exactly matches an OFAC SDN entry ({ofac.get('summary')}). "
                                "Blocked pending compliance review; a name match alone does not prove identity.",
                                "supplier", sid, [ofac["id"]]))
    elif ofac["status"] == "POTENTIAL_MATCH":
        cleared = _cleared(state, "SANCTIONS_POTENTIAL_MATCH", ofac["id"])
        if cleared:
            out.append(decision("SANCTIONS_POTENTIAL_MATCH", "PASS", "MEDIUM",
                                f"Potential SDN match reviewed and cleared: {cleared['reason']}",
                                "supplier", sid, [ofac["id"]], review_id=cleared["id"]))
        else:
            out.append(decision("SANCTIONS_POTENTIAL_MATCH", "NEEDS_REVIEW", "HIGH",
                                f"Fuzzy name similarity to an OFAC SDN entry ({ofac.get('summary')}). "
                                "Requires human review; ReliefMesh never labels a supplier sanctioned from a "
                                "fuzzy match.", "supplier", sid, [ofac["id"]]))
    else:
        out.append(decision("SANCTIONS_SCREENING", "PASS", "INFO",
                            "No OFAC SDN name match on the current list.", "supplier", sid, [ofac["id"]]))

    sam = latest.get("SAM_REGISTRATION")
    if not sam or sam["status"] in {"BLOCKED_EXTERNAL", "UNAVAILABLE"}:
        out.append(decision("ENTITY_REGISTRATION_UNVERIFIED", "WARN", "MEDIUM",
                            "SAM.gov registration was not verified"
                            + (f" ({sam.get('summary')})." if sam else "."),
                            "supplier", sid, [sam["id"]] if sam else []))
    elif _stale(sam, ttl.sam_hours, now):
        out.append(decision("ENTITY_REGISTRATION_STALE", "WARN", "LOW", "SAM.gov evidence is stale.",
                            "supplier", sid, [sam["id"]]))
    elif sam["status"] == "MATCH":
        out.append(decision("ENTITY_REGISTRATION", "PASS", "INFO",
                            "Active SAM.gov registration (registration only; not proof of inventory or capacity).",
                            "supplier", sid, [sam["id"]]))
    else:
        out.append(decision("ENTITY_REGISTRATION_NOT_FOUND", "WARN", "MEDIUM",
                            f"No active SAM.gov registration matched ({sam.get('summary')}).",
                            "supplier", sid, [sam["id"]]))

    fda = latest.get("FDA_RECALLS")
    severity = "HIGH" if regulated_goods else "MEDIUM"
    if not fda or fda["status"] in {"UNAVAILABLE", "BLOCKED_EXTERNAL"}:
        out.append(decision("PRODUCT_RECALL_UNCHECKED", "WARN", severity,
                            "openFDA recall history was not checked.", "supplier", sid,
                            [fda["id"]] if fda else []))
    elif _stale(fda, ttl.fda_hours, now):
        out.append(decision("PRODUCT_RECALL_STALE", "WARN", "LOW", "openFDA evidence is stale.", "supplier", sid,
                            [fda["id"]]))
    elif fda["status"] == "POTENTIAL_MATCH":
        cleared = _cleared(state, "PRODUCT_RECALL_MATCH", fda["id"])
        if cleared:
            out.append(decision("PRODUCT_RECALL_MATCH", "WARN", severity,
                                f"Recall history reviewed: {cleared['reason']}", "supplier", sid, [fda["id"]],
                                review_id=cleared["id"]))
        else:
            out.append(decision("PRODUCT_RECALL_MATCH", "NEEDS_REVIEW", severity,
                                f"openFDA enforcement reports name a closely matching firm ({fda.get('summary')}).",
                                "supplier", sid, [fda["id"]]))
    elif fda["status"] == "WEAK_MATCH":
        out.append(decision("PRODUCT_RECALL_WEAK_MATCH", "WARN", "LOW",
                            f"Only weak text matches in openFDA ({fda.get('summary')}); not treated as a recall.",
                            "supplier", sid, [fda["id"]]))
    else:
        out.append(decision("PRODUCT_RECALL", "PASS", "INFO", "No openFDA enforcement reports for this firm.",
                            "supplier", sid, [fda["id"]]))

    crs = latest.get("CRS_VERIFICATION")
    if crs:
        if crs["status"] == "PASS" and not _stale(crs, ttl.crs_hours, now):
            out.append(decision("CRS_VERIFICATION", "PASS", "INFO", crs.get("summary") or "CRS check passed.",
                                "supplier", sid, [crs["id"]]))
        elif crs["status"] == "FAIL":
            cleared = _cleared(state, "CRS_VERIFICATION", crs["id"])
            out.append(decision("CRS_VERIFICATION", "WARN" if cleared else "NEEDS_REVIEW", "HIGH",
                                (f"CRS finding reviewed: {cleared['reason']}" if cleared
                                 else f"CRS sandbox check flagged this contact: {crs.get('summary')}"),
                                "supplier", sid, [crs["id"]]))
        else:
            out.append(decision("CRS_VERIFICATION_INCOMPLETE", "WARN", "MEDIUM",
                                f"CRS check did not complete: {crs.get('summary')}", "supplier", sid, [crs["id"]]))

    if supplier.get("is_demo"):
        out.append(decision("TEST_SUPPLIER", "WARN", "INFO",
                            "Clearly labeled TEST supplier seeded for demonstration; its quotes are synthetic.",
                            "supplier", sid))
    return out


def _money(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def quote_decisions(quote: dict[str, Any], mission: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
    qid = quote["id"]
    out: list[dict[str, Any]] = []
    requirements = {row["item"]: int(row["quantity"]) for row in mission["requirements"]}
    deadline = _dt(mission["delivery_deadline"])
    budget = _money(mission["budget"]) or Decimal("0")

    if quote["status"] != "submitted":
        out.append(decision("QUOTE_NOT_ACTIVE", "BLOCK", "HIGH", f"Quote is {quote['status']}.", "quote", qid))
    expires = _dt(quote.get("expires_at"))
    if expires is None or expires <= now:
        out.append(decision("QUOTE_EXPIRED", "BLOCK", "HIGH", "Quote validity has expired.", "quote", qid))
    currency = (quote.get("currency") or "USD").upper()
    if currency != mission.get("currency", "USD"):
        out.append(decision("CURRENCY_MISMATCH", "BLOCK", "HIGH",
                            f"Quote currency {currency} does not match mission currency {mission.get('currency')}.",
                            "quote", qid))
    shipping = _money(quote.get("shipping_cost", "0"))
    if shipping is None or shipping < 0 or shipping > MAX_UNIT_PRICE:
        out.append(decision("INVALID_SHIPPING", "BLOCK", "HIGH", "Shipping cost is invalid.", "quote", qid))

    relevant = [line for line in quote.get("lines", []) if line.get("item") in requirements]
    if not relevant:
        out.append(decision("NO_REQUIRED_ITEMS", "BLOCK", "MEDIUM", "Quote offers none of the required items.",
                            "quote", qid))
    invalid = []
    late = []
    unaffordable = []
    for line in relevant:
        price = _money(line.get("unit_price"))
        quantity = line.get("available_quantity")
        if price is None or price <= 0 or price > MAX_UNIT_PRICE or not isinstance(quantity, int) \
                or quantity <= 0 or quantity > MAX_QUANTITY:
            invalid.append(line.get("item"))
            continue
        delivery = _dt(line.get("delivery_date"))
        if delivery is None or (deadline and delivery > deadline):
            late.append(line.get("item"))
        if price > budget:
            unaffordable.append(line.get("item"))
    if invalid:
        out.append(decision("INVALID_QUANTITY_OR_PRICE", "BLOCK", "HIGH",
                            f"Invalid quantity or price on: {', '.join(sorted(set(invalid)))}.", "quote", qid))
    if relevant and len(late) == len(relevant):
        out.append(decision("DELIVERY_DEADLINE", "BLOCK", "HIGH",
                            "No offered line can be delivered before the mission deadline.", "quote", qid))
    elif late:
        out.append(decision("DELIVERY_DEADLINE_PARTIAL", "WARN", "MEDIUM",
                            f"Lines arriving after the deadline are excluded: {', '.join(sorted(set(late)))}.",
                            "quote", qid))
    if relevant and len(unaffordable) == len(relevant):
        out.append(decision("BUDGET_UNIT_EXCEEDS", "BLOCK", "MEDIUM",
                            "A single unit costs more than the entire mission budget.", "quote", qid))
    return out


REGULATED_HINTS = ("mask", "n95", "respirator", "glove", "medical", "medicine", "drug", "insulin", "vaccine",
                   "bandage", "gauze", "syringe", "food", "meal", "formula", "water", "antiseptic", "sanitizer",
                   "test kit", "thermometer", "ppe")


def mission_has_regulated_goods(mission: dict[str, Any]) -> bool:
    return any(hint in row["item"] for row in mission["requirements"] for hint in REGULATED_HINTS)


def evaluate(mission: dict[str, Any], quotes: list[dict[str, Any]], suppliers: dict[str, dict[str, Any]],
             evidence: dict[str, list[dict[str, Any]]], reviews: dict[str, list[dict[str, Any]]],
             now: datetime | None = None, ttl: EvidenceTTL | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    ttl = ttl or EvidenceTTL()
    regulated = mission_has_regulated_goods(mission)
    supplier_report: dict[str, Any] = {}
    for supplier_id in sorted({quote["supplier_id"] for quote in quotes} | set(suppliers)):
        supplier = suppliers.get(supplier_id) or {"id": supplier_id}
        decisions = supplier_decisions(supplier, evidence.get(supplier_id, []), reviews.get(supplier_id, []),
                                       now, ttl, regulated)
        supplier_report[supplier_id] = {
            "status": worst([row["status"] for row in decisions]),
            "decisions": decisions,
            "legal_name": supplier.get("legal_name"),
            "email": supplier.get("email"),
            "is_demo": bool(supplier.get("is_demo")),
        }
    quote_report: dict[str, Any] = {}
    for quote in sorted(quotes, key=lambda row: row["id"]):
        own = quote_decisions(quote, mission, now)
        supplier_status = supplier_report[quote["supplier_id"]]["status"]
        status = worst([row["status"] for row in own] + [supplier_status])
        quote_report[quote["id"]] = {
            "status": status,
            "eligible": status in ELIGIBLE,
            "supplier_id": quote["supplier_id"],
            "supplier_status": supplier_status,
            "decisions": own,
            "version": quote.get("version", 1),
        }
    eligible = sorted(quote_id for quote_id, row in quote_report.items() if row["eligible"])
    fingerprint_source = {
        "quotes": {qid: [row["version"], row["status"]] for qid, row in quote_report.items()},
        "suppliers": {sid: row["status"] for sid, row in supplier_report.items()},
    }
    return {
        "evaluated_at": now.isoformat(),
        "suppliers": supplier_report,
        "quotes": quote_report,
        "eligible_quote_ids": eligible,
        "fingerprint": hashlib.sha256(json.dumps(fingerprint_source, sort_keys=True).encode()).hexdigest(),
    }
