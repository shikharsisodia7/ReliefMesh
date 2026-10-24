"""Stable requirement identity: mission requirement -> RFQ -> quote line -> optimizer.

Every mission requirement carries a server-assigned `id`. Quote lines reference it through
`requirement_id`, so a supplier may describe the product in its own words ("Fleece blanket, 50x60")
without breaking the match. Missions created before IDs existed get a deterministic legacy key.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import HTTPException


def new_requirement_id() -> str:
    return f"req_{uuid4().hex[:12]}"


def requirement_key(row: dict[str, Any]) -> str:
    return row.get("id") or f"legacy:{row['item']}"


def requirement_map(mission: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {requirement_key(row): row for row in mission["requirements"]}


def line_requirement(line: dict[str, Any], mission: dict[str, Any]) -> str | None:
    """Return the requirement key a stored quote line covers, or None when it maps to nothing."""

    requirements = requirement_map(mission)
    requirement_id = line.get("requirement_id")
    if requirement_id:
        return requirement_id if requirement_id in requirements else None
    matches = [key for key, row in requirements.items() if row["item"] == line.get("item")]
    return matches[0] if len(matches) == 1 else None  # legacy quotes without IDs


def mapping_error(code: str, message: str, **details: Any) -> HTTPException:
    return HTTPException(status_code=422, detail={"code": code, "message": message, **details})


def assign_quote_lines(lines: list[dict[str, Any]], mission: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate a submitted quote's lines and pin each to exactly one mission requirement."""

    requirements = requirement_map(mission)
    seen: dict[str, int] = {}
    assigned = []
    for index, line in enumerate(lines):
        requirement_id = line.get("requirement_id")
        if requirement_id:
            if requirement_id not in requirements:
                raise mapping_error("QUOTE_LINE_REQUIREMENT_MISMATCH",
                                    f"Line {index + 1} references requirement {requirement_id!r}, which is not part "
                                    "of this mission.", line_index=index, requirement_id=requirement_id,
                                    valid_requirement_ids=sorted(requirements))
        else:
            matches = [key for key, row in requirements.items() if row["item"] == line.get("item")]
            if len(matches) != 1:
                raise mapping_error("QUOTE_LINE_REQUIREMENT_MISMATCH",
                                    f"Line {index + 1} ({line.get('item')!r}) does not identify a mission requirement; "
                                    "send requirement_id.", line_index=index, item=line.get("item"),
                                    valid_requirement_ids=sorted(requirements))
            requirement_id = matches[0]
        if requirement_id in seen:
            raise mapping_error("QUOTE_LINE_DUPLICATE_REQUIREMENT",
                                f"Lines {seen[requirement_id] + 1} and {index + 1} both quote requirement "
                                f"{requirement_id!r}; submit one line per requirement.",
                                line_index=index, requirement_id=requirement_id)
        seen[requirement_id] = index
        assigned.append({**line, "requirement_id": requirement_id})
    return assigned
