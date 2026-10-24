"""OFAC Specially Designated Nationals screening against the official Treasury CSV exports.

A name screen is evidence for human review, not an identity determination:
- EXACT_MATCH: the normalized name equals an SDN name or alias.
- POTENTIAL_MATCH: a fuzzy name similarity above threshold. Never auto-labels a sanction.
- NO_MATCH: nothing on the current list resembles the name.
"""

from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from .http import AdapterResult, IntegrationHub, iso, utc_now

LEGAL_SUFFIXES = {
    "INC", "INCORPORATED", "LLC", "LLP", "LP", "LTD", "LIMITED", "CO", "COMPANY", "CORP", "CORPORATION",
    "SA", "SAS", "SRL", "GMBH", "AG", "PLC", "PTE", "PVT", "PRIVATE", "NV", "BV", "OOO", "ZAO", "OAO", "PJSC",
    "JSC", "FZE", "FZCO", "DMCC", "SPA", "THE", "OF", "AND", "DE", "LA", "EL", "AL",
}
POTENTIAL_THRESHOLD = 0.86
MEMO_KEY = "ofac:sdn"
MEMO_SECONDS = 6 * 3600


def normalize_name(name: str) -> str:
    text = name.upper().replace("&", " AND ")
    text = re.sub(r"\(.*?\)", " ", text)  # drop parentheticals such as "(TEST)" or country notes
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    tokens = [token for token in text.split() if token not in LEGAL_SUFFIXES]
    return " ".join(tokens)


def name_tokens(normalized: str) -> set[str]:
    return {token for token in normalized.split() if len(token) >= 3}


@dataclass(frozen=True)
class SdnName:
    ent_num: str
    name: str
    normalized: str
    sdn_type: str
    program: str
    primary_name: str
    is_alias: bool


class SdnIndex:
    def __init__(self, entries: list[SdnName], retrieved_at: str, source_url: str, provenance: str) -> None:
        self.entries = entries
        self.retrieved_at = retrieved_at
        self.source_url = source_url
        self.provenance = provenance
        self.by_token: dict[str, list[int]] = defaultdict(list)
        self.exact: dict[str, list[int]] = defaultdict(list)
        for index, entry in enumerate(entries):
            self.exact[entry.normalized].append(index)
            for token in name_tokens(entry.normalized):
                self.by_token[token].append(index)

    def screen(self, name: str, limit: int = 5) -> dict[str, Any]:
        normalized = normalize_name(name)
        tokens = name_tokens(normalized)
        hits: list[dict[str, Any]] = []
        for index in self.exact.get(normalized, []):
            hits.append(self._hit(self.entries[index], 1.0, "exact"))
        if not hits and tokens:
            candidates: set[int] = set()
            for token in tokens:
                postings = self.by_token.get(token, [])
                if len(postings) < 2500:  # ignore tokens so common they carry no signal
                    candidates.update(postings)
            for index in candidates:
                entry = self.entries[index]
                other = name_tokens(entry.normalized)
                if not other:
                    continue
                overlap = len(tokens & other)
                jaccard = overlap / len(tokens | other)
                containment = overlap / min(len(tokens), len(other))
                sorted_a = " ".join(sorted(normalized.split()))
                sorted_b = " ".join(sorted(entry.normalized.split()))
                ratio = max(
                    SequenceMatcher(None, normalized, entry.normalized).ratio(),
                    SequenceMatcher(None, sorted_a, sorted_b).ratio(),
                )
                strong_containment = containment == 1.0 and min(len(tokens), len(other)) >= 2 and jaccard >= 0.5
                if ratio >= POTENTIAL_THRESHOLD or strong_containment:
                    hits.append(self._hit(entry, round(max(ratio, jaccard), 3), "fuzzy"))
        hits.sort(key=lambda row: (-row["score"], row["ent_num"]))
        if any(hit["match_type"] == "exact" for hit in hits):
            status = "EXACT_MATCH"
        elif hits:
            status = "POTENTIAL_MATCH"
        else:
            status = "NO_MATCH"
        return {
            "status": status,
            "screened_name": name,
            "normalized_name": normalized,
            "matches": hits[:limit],
            "entries_screened": len(self.entries),
            "list_retrieved_at": self.retrieved_at,
        }

    @staticmethod
    def _hit(entry: SdnName, score: float, match_type: str) -> dict[str, Any]:
        return {
            "ent_num": entry.ent_num,
            "sdn_name": entry.primary_name,
            "matched_name": entry.name,
            "via_alias": entry.is_alias,
            "sdn_type": entry.sdn_type,
            "program": entry.program,
            "score": score,
            "match_type": match_type,
        }


def _clean(value: str) -> str:
    value = value.strip()
    return "" if value == "-0-" else value


def parse_lists(sdn_csv: str, alt_csv: str) -> list[list[str]]:
    """Return compact rows [ent_num, name, sdn_type, program, primary_name, is_alias]."""

    rows: list[list[str]] = []
    primaries: dict[str, tuple[str, str, str]] = {}
    for record in csv.reader(io.StringIO(sdn_csv)):
        if len(record) < 4 or not record[0].strip().isdigit():
            continue
        ent_num, name, sdn_type, program = (_clean(record[i]) for i in range(4))
        sdn_type = sdn_type or "entity"
        primaries[ent_num] = (name, sdn_type, program)
        rows.append([ent_num, name, sdn_type, program, name, "0"])
    for record in csv.reader(io.StringIO(alt_csv)):
        if len(record) < 4 or not record[0].strip().isdigit():
            continue
        ent_num, alt_name = _clean(record[0]), _clean(record[3])
        primary = primaries.get(ent_num)
        if primary and alt_name:
            rows.append([ent_num, alt_name, primary[1], primary[2], primary[0], "1"])
    return rows


def build_index(rows: list[list[str]], retrieved_at: str, source_url: str, provenance: str) -> SdnIndex:
    entries = [
        SdnName(row[0], row[1], normalize_name(row[1]), row[2], row[3], row[4], row[5] == "1")
        for row in rows if row[1]
    ]
    return SdnIndex(entries, retrieved_at, source_url, provenance)


async def load_index(hub: IntegrationHub, sdn_url: str, alt_url: str) -> AdapterResult:
    memo = hub.memo_get(MEMO_KEY, MEMO_SECONDS)
    if memo is not None:
        return AdapterResult("ofac", "OK", memo, memo.provenance, memo.source_url, memo.retrieved_at)
    sdn = await hub.fetch("ofac", sdn_url, expect="text", timeout=45, retries=1, headers={"Accept": "text/csv,*/*"})
    alt = await hub.fetch("ofac", alt_url, expect="text", timeout=45, retries=1, headers={"Accept": "text/csv,*/*"}) if sdn.ok else sdn
    if sdn.ok and alt.ok and sdn.provenance == "LIVE":
        rows = parse_lists(sdn.data, alt.data)
        retrieved_at = sdn.retrieved_at or iso(utc_now())
        # Persist a compact last-known-good copy so an outage degrades to CACHED, not to "no screening".
        await hub.write_cache("ofac", "sdn_rows", rows, sdn_url, retrieved_at)
        index = build_index(rows, retrieved_at, sdn_url, "LIVE")
        hub.memo_set(MEMO_KEY, index)
        return AdapterResult("ofac", "OK", index, "LIVE", sdn_url, retrieved_at)
    cached = await hub.read_cache("ofac", "sdn_rows")
    if cached:
        index = build_index(cached["data"], cached["retrieved_at"], cached["source_url"], "CACHED")
        return AdapterResult(
            "ofac", "OK", index, "CACHED", cached["source_url"], cached["retrieved_at"],
            error=f"Live SDN download failed ({sdn.error or alt.error}); using last-known-good list.",
        )
    return AdapterResult("ofac", "UNAVAILABLE", source_url=sdn_url, error=sdn.error or alt.error)


async def screen_name(hub: IntegrationHub, name: str, sdn_url: str, alt_url: str) -> AdapterResult:
    loaded = await load_index(hub, sdn_url, alt_url)
    if not loaded.ok:
        return loaded
    index: SdnIndex = loaded.data
    return AdapterResult(
        "ofac", "OK", index.screen(name), index.provenance, index.source_url, index.retrieved_at,
        error=loaded.error,
    )
