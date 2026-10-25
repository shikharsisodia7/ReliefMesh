"""Answers to continuity questions, explained from stored deterministic Continuity Engine results.

Nothing here calculates resilience. Every number comes from the persisted analysis (an exact MILP re-solve per
hypothetical scenario) or from persisted plans; this module only selects, orders, and phrases them. A question
the stored results cannot answer gets "not known", never an estimate.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

HYPOTHETICAL = "HYPOTHETICAL STRESS TEST (no supplier quote, plan, or approval was changed)"
FOOTER = "Numbers come from the deterministic Continuity Engine; I explain them and cannot approve, order, or pay."

QUESTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("most_fragile", re.compile(r"(?=.*\bmissions?\b).*\b(most|least)\s+(fragile|vulnerable|resilient|at[- ]risk|risky)\b",
                                re.I)),
    ("plan_changes", re.compile(r"\b(what|which)\b.*\b(changed|different|difference)\b.*\b(v\d+|version|plan)", re.I)),
    ("cheapest_resilient", re.compile(r"\b(cheapest|least expensive|lowest[- ]cost|minimum[- ]cost)\b.*\b(resilien|n-?1|survive)", re.I)),
    ("survive_losing", re.compile(r"\b(surviv\w*|withstand|recover\w*|ok|fine)\b.*\b(los(?:e|ing|t)|without|if)\b"
                                  r"|\b(what if|if)\b.*\b(fails?|drops? out|goes? down|unavailable|backs? out)\b", re.I)),
    ("single_point", re.compile(r"\b(single point of failure|biggest\s+(risk|failure|weakness)|critical supplier|"
                                r"weakest (link|supplier))\b", re.I)),
]

_SUPPLIER_AFTER = re.compile(r"\b(?:los(?:e|ing|t)|without|if)\s+(?:supplier\s+)?(.+?)(?:\s+(?:fails?|drops? out|goes? down|"
                             r"is unavailable|backs? out))?[?.!]*$", re.I)


def classify(text: str) -> str | None:
    """Return the continuity question type, or None when the text is not a continuity question."""
    for name, pattern in QUESTION_PATTERNS:
        if pattern.search(text):
            return name
    return None


def supplier_from_question(text: str) -> str | None:
    match = _SUPPLIER_AFTER.search(text.strip())
    if not match:
        return None
    candidate = re.sub(r"^(the|our|supplier)\s+", "", match.group(1).strip(), flags=re.I)
    return candidate or None


def money(value: Any) -> str:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return "unknown"
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.2f}"


def signed(value: Any) -> str:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return "unknown"
    return f"+{money(amount)}" if amount > 0 else money(amount)


def _units(analysis: dict[str, Any]) -> dict[str, int]:
    return {row["supplier_id"]: int(row.get("units", 0))
            for row in (analysis.get("baseline") or {}).get("supplier_concentration", [])}


def _current(analysis: dict[str, Any] | None) -> bool:
    return bool(analysis) and analysis.get("status") == "COMPLETE"


def _not_current(analysis: dict[str, Any] | None) -> str:
    if analysis and analysis.get("status") == "STALE":
        return ("The last continuity analysis is **STALE**: a quote, evidence, or policy input changed after it ran, "
                "so I won't present it as current. A fresh analysis runs automatically for the new plan.")
    return "There is no current continuity analysis for this plan yet, so I can't answer that without guessing."


def _match_scenario(analysis: dict[str, Any], name: str) -> dict[str, Any] | None:
    wanted = re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()
    if not wanted:
        return None
    scenarios = analysis.get("n1_scenarios", [])
    exact = [row for row in scenarios if row["supplier"].lower() == name.lower()]
    if exact:
        return exact[0]
    tokens = set(wanted.split())
    scored = []
    for row in scenarios:
        label = set(re.sub(r"[^a-z0-9 ]", "", row["supplier"].lower()).split())
        overlap = len(tokens & label)
        if overlap:
            scored.append((overlap, row["supplier"], row))
    return max(scored, key=lambda item: (item[0], item[1]))[2] if scored else None


def single_point_of_failure(analysis: dict[str, Any] | None) -> str:
    if not _current(analysis):
        return _not_current(analysis)
    units = _units(analysis)
    scenarios = analysis.get("n1_scenarios", [])
    n1 = analysis["metrics"]["n1_survivability"]
    head = f"**Plan v{analysis['plan_version']}**, {HYPOTHETICAL}. N-1 survivability {n1['survives']}/{n1['tested']}."
    unrecoverable = sorted((row for row in scenarios if not row["feasible"]),
                           key=lambda row: (-units.get(row["supplier_id"], 0), row["supplier"]))
    if unrecoverable:
        worst = unrecoverable[0]
        others = ", ".join(row["supplier"] for row in unrecoverable[1:])
        return "\n".join(filter(None, [
            head,
            f"Biggest single point of failure: **{worst['supplier']}** "
            f"({units.get(worst['supplier_id'], 0)} allocated units). If it becomes unavailable the plan is "
            f"**UNRECOVERABLE**: {worst.get('lost_quantity', 0)} units cannot be covered by any eligible supplier.",
            f"Also unrecoverable on its own: {others}." if others else None,
            FOOTER]))
    if not scenarios:
        return f"{head}\nNo allocated supplier was stress-tested.\n{FOOTER}"
    costliest = max(scenarios, key=lambda row: (Decimal(str(row.get("cost_delta") or 0)), row["supplier"]))
    return "\n".join([
        head,
        "No single supplier failure breaks this plan. The most expensive loss to absorb is "
        f"**{costliest['supplier']}**: recovery costs {signed(costliest['cost_delta'])} using "
        f"{', '.join(costliest.get('replacement_suppliers') or []) or 'the remaining suppliers'}.",
        FOOTER])


def survive_losing(analysis: dict[str, Any] | None, supplier: str | None) -> str:
    if not _current(analysis):
        return _not_current(analysis)
    if not supplier:
        return "Which supplier? For example: `can this plan survive losing Alpha Textiles?`"
    scenario = _match_scenario(analysis, supplier)
    if not scenario:
        tested = ", ".join(row["supplier"] for row in analysis.get("n1_scenarios", [])) or "none"
        return (f"**{supplier}** has no allocation in plan v{analysis['plan_version']}, so losing it does not change "
                f"this plan. Allocated suppliers that were stress-tested: {tested}.\n{FOOTER}")
    lines = [f"**{scenario['supplier']} unavailable** — {HYPOTHETICAL}, plan v{analysis['plan_version']}."]
    if scenario["feasible"]:
        replacements = ", ".join(scenario.get("replacement_suppliers") or []) or "remaining suppliers"
        delay = scenario.get("deadline_delta_hours")
        lines.append(f"**Yes, RECOVERABLE.** Recovery plan: {money(scenario['new_cost'])} "
                     f"({signed(scenario['cost_delta'])}) using {replacements}"
                     + (f"; latest delivery shifts {delay:+d} h." if isinstance(delay, int) and delay else "."))
    else:
        reasons = []
        if scenario.get("budget_feasible") is False:
            reasons.append("the budget cannot cover the replacement")
        if scenario.get("deadline_feasible") is False:
            reasons.append("no replacement delivers before the deadline")
        lines.append(f"**No, UNRECOVERABLE.** {scenario.get('lost_quantity', 0)} units would go uncovered"
                     + (f" ({'; '.join(reasons)})." if reasons else "."))
    lines.append(FOOTER)
    return "\n".join(lines)


def cheapest_resilient(analysis: dict[str, Any] | None) -> str:
    if not _current(analysis):
        return _not_current(analysis)
    n1 = analysis["metrics"]["n1_survivability"]
    cost = analysis["baseline"]["total_cost"]
    if n1["tested"] and n1["survives"] == n1["tested"]:
        return (f"Plan v{analysis['plan_version']} ({money(cost)}) already survives every single-supplier failure "
                f"({n1['survives']}/{n1['tested']}), so N-1 resilience costs nothing extra.\n{FOOTER}")
    alternative = analysis.get("resilient_alternative") or {}
    if alternative.get("status") != "AVAILABLE":
        return (f"Current plan: {money(cost)}, N-1 {n1['survives']}/{n1['tested']}. **No feasible alternative** "
                f"satisfies the stronger concentration guardrail ({alternative.get('reason', 'no feasible plan')}). "
                "More eligible supplier capacity is needed; that is a sourcing gap, not something a re-plan can fix."
                f"\n{FOOTER}")
    alt_n1 = alternative.get("n1_survivability") or {}
    fully = alt_n1.get("tested") and alt_n1.get("survives") == alt_n1.get("tested")
    verdict = ("This alternative **is N-1 resilient**: it survives the loss of any one of its suppliers."
               if fully else
               f"This alternative **reduces concentration but is not fully N-1 resilient** "
               f"({alt_n1.get('survives')}/{alt_n1.get('tested')} single failures recoverable).")
    return "\n".join([
        f"Current plan v{analysis['plan_version']}: {money(cost)}, N-1 {n1['survives']}/{n1['tested']}.",
        f"Cheapest plan under the {alternative.get('constraint', {}).get('max_supplier_share')} max-supplier-share "
        f"guardrail: **{money(alternative['total_cost'])} ({signed(alternative['added_cost'])})** across "
        f"{alternative.get('supplier_count')} suppliers. {verdict}",
        f"It is a {HYPOTHETICAL.split(' (')[0].lower()} proposal: adopting it means re-planning and a new human approval.",
        FOOTER])


def plan_changes(older: dict[str, Any], newer: dict[str, Any]) -> str:
    """Explain the difference between two persisted plans.

    Uses the planner's own stored ``difference`` record when the newer plan was computed directly against the
    older one; otherwise falls back to comparing the two plans' persisted allocations. Either way every number is
    read from the plans, not estimated.
    """
    lines = [f"**Plan v{older['version']} → v{newer['version']}**: {money(older.get('total_cost'))} → "
             f"{money(newer.get('total_cost'))}; status {older.get('status')} → {newer.get('status')}."]
    stored = newer.get("difference") or {}
    if stored.get("previous_plan_id") == older.get("id"):
        if stored.get("cost_delta"):
            lines[0] = lines[0].replace(";", f" ({signed(stored['cost_delta'])});", 1)
        if stored.get("why"):
            lines.append("Why it changed: " + "; ".join(stored["why"]))
        moves = [(row["supplier"] or row["supplier_id"], int(row["units_before"]), int(row["units_after"]))
                 for row in stored.get("supplier_delta", [])]
    else:
        def units(plan: dict[str, Any]) -> dict[str, tuple[str, int]]:
            out: dict[str, tuple[str, int]] = {}
            for row in plan.get("allocations", []):
                name = row.get("supplier_name") or row.get("supplier_email") or row["supplier_id"]
                out[row["supplier_id"]] = (name, out.get(row["supplier_id"], (name, 0))[1] + int(row["quantity"]))
            return out
        before, after = units(older), units(newer)
        delta = Decimal(str(newer.get("total_cost") or 0)) - Decimal(str(older.get("total_cost") or 0))
        lines[0] = lines[0].replace(";", f" ({signed(delta)});", 1)
        moves = [((after.get(sid) or before.get(sid))[0], before.get(sid, ("", 0))[1], after.get(sid, ("", 0))[1])
                 for sid in sorted(set(before) | set(after))]
    changed = False
    for name, units_before, units_after in sorted(moves):
        if units_before == units_after:
            continue
        changed = True
        if not units_before:
            lines.append(f"- {name}: added ({units_after} units).")
        elif not units_after:
            lines.append(f"- {name}: removed (was {units_before} units).")
        else:
            lines.append(f"- {name}: {units_before} → {units_after} units.")
    if not changed:
        lines.append("- Same suppliers and quantities; only prices or terms changed.")
    lines.append("A changed plan needs a new human approval; earlier approvals do not carry over.")
    return "\n".join(lines)


def fragility_key(analysis: dict[str, Any]) -> tuple:
    """Deterministic ordering, most fragile first: lowest N-1 survival share, then an unrecoverable critical
    supplier, then least budget headroom, then highest single-supplier concentration."""
    n1 = analysis["metrics"]["n1_survivability"]
    share = Decimal(n1["survives"]) / Decimal(n1["tested"]) if n1["tested"] else Decimal(1)
    headroom = Decimal(str(analysis["metrics"].get("budget_headroom") or 0))
    concentration = Decimal(str(analysis["metrics"].get("largest_supplier_concentration") or 0))
    return (share, analysis["metrics"].get("critical_supplier") is None, headroom, -concentration)


def most_fragile(missions: list[tuple[dict[str, Any], dict[str, Any] | None]]) -> str:
    """`missions` pairs each mission with its continuity view's analysis (None when not available)."""
    ranked = sorted(((m, a) for m, a in missions if _current(a)), key=lambda pair: (fragility_key(pair[1]), pair[0]["name"]))
    unknown = [m["name"] for m, a in missions if not _current(a)]
    if not ranked:
        return ("None of your missions has a current continuity analysis, so I can't rank fragility without guessing."
                + (f" Missions without one: {', '.join(unknown)}." if unknown else ""))
    lines = [f"Ranked by deterministic fragility ({HYPOTHETICAL.split(' (')[0].lower()} results):"]
    for index, (mission, analysis) in enumerate(ranked, start=1):
        n1, metrics = analysis["metrics"]["n1_survivability"], analysis["metrics"]
        critical = metrics.get("critical_supplier")
        lines.append(f"{index}. **{mission['name']}** — N-1 {n1['survives']}/{n1['tested']}, budget headroom "
                     f"{money(metrics.get('budget_headroom'))}, largest supplier share "
                     f"{Decimal(str(metrics.get('largest_supplier_concentration') or 0)) * 100:.0f}%"
                     + (f"; single point of failure: {critical['supplier']}." if critical else "."))
    if unknown:
        lines.append(f"Not ranked (no current analysis): {', '.join(unknown)}.")
    lines.append(FOOTER)
    return "\n".join(lines)
