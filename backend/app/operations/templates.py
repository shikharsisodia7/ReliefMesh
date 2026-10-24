"""Rendered content for Gmail, Slack, and Calendar. Every value comes from ReliefMesh records.

All dynamic text is escaped for its medium (HTML for email, mrkdwn for Slack). Slack buttons
are plain links back into ReliefMesh; there are no approve actions anywhere in this module.
"""

from __future__ import annotations

import html
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

FOOTER = "ReliefMesh is the system of record. This message is a notification; act inside ReliefMesh."


def money(value: Any) -> str:
    if value in (None, ""):
        return "—"
    return f"${Decimal(str(value)):,.2f}"


def signed_money(value: Any) -> str:
    if value in (None, ""):
        return "—"
    amount = Decimal(str(value))
    return f"{'+' if amount >= 0 else '−'}${abs(amount):,.2f}"


def when(value: str | None) -> str:
    if not value:
        return "—"
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return moment.astimezone(UTC).strftime("%a %b %d, %Y %H:%M UTC")


def requirements_lines(mission: dict[str, Any]) -> list[str]:
    return [f"{row['quantity']:,} × {row['item']}" for row in mission.get("requirements", [])]


def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def slack_esc(value: Any) -> str:
    return str(value if value is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def supplier_changes(plan: dict[str, Any]) -> tuple[list[str], list[str]]:
    removed, added = [], []
    for row in (plan.get("difference") or {}).get("supplier_delta") or []:
        if row["units_before"] and not row["units_after"]:
            removed.append(row["supplier"])
        elif row["units_after"] and not row["units_before"]:
            added.append(row["supplier"])
    return removed, added


def supplier_count(plan: dict[str, Any]) -> int:
    return len({row["supplier_id"] for row in plan.get("allocations") or []})


# ---------------- email ----------------

def _email(title: str, intro: str, rows: list[tuple[str, str]], cta: tuple[str, str] | None,
           extra_html: str = "", tone: str = "#0f766e") -> str:
    table = "".join(
        f'<tr><td style="padding:6px 12px 6px 0;color:#57534e;vertical-align:top;white-space:nowrap">{esc(k)}</td>'
        f'<td style="padding:6px 0;color:#1c1917">{v}</td></tr>' for k, v in rows)
    button = (f'<p style="margin:24px 0"><a href="{esc(cta[1])}" style="background:{tone};color:#ffffff;'
              f'padding:10px 18px;border-radius:6px;text-decoration:none;font-weight:600">{esc(cta[0])}</a></p>'
              if cta else "")
    return (
        '<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;max-width:620px;color:#1c1917">'
        f'<p style="font-size:11px;letter-spacing:.18em;color:{tone};font-weight:700;margin:0">RELIEFMESH</p>'
        f'<h2 style="margin:6px 0 12px;font-size:20px">{esc(title)}</h2>'
        f'<p style="margin:0 0 16px;line-height:1.5">{intro}</p>'
        f'<table style="border-collapse:collapse;font-size:14px">{table}</table>{extra_html}{button}'
        f'<p style="font-size:12px;color:#78716c;border-top:1px solid #e7e5e4;padding-top:12px">{esc(FOOTER)}</p>'
        '</div>'
    )


def _text(title: str, rows: list[tuple[str, str]], link: tuple[str, str] | None) -> str:
    body = [title, ""] + [f"{k}: {v}" for k, v in rows]
    if link:
        body += ["", f"{link[0]}: {link[1]}"]
    return "\n".join(body + ["", FOOTER])


def rfq_email(organization: dict[str, Any], mission: dict[str, Any], url: str) -> tuple[str, str, str]:
    subject = f"Urgent RFQ — ReliefMesh Mission {mission['name']}"
    items = requirements_lines(mission)
    rows = [("Organization", esc(organization.get("name"))), ("Mission", esc(mission["name"])),
            ("Delivery location", esc(mission["delivery_location"])),
            ("Delivery deadline", esc(when(mission["delivery_deadline"]))),
            ("Items", "<br>".join(esc(i) for i in items))]
    intro = (f"{esc(organization.get('name'))} is requesting quotes for emergency relief supplies. "
             "Respond through the secure link below; it is unique to your email address.")
    html_body = _email("Request for quotation", intro, rows, ("Respond to this RFQ", url), tone="#b45309")
    text = _text(subject, [("Organization", organization.get("name") or ""), ("Mission", mission["name"]),
                           ("Delivery location", mission["delivery_location"]),
                           ("Delivery deadline", when(mission["delivery_deadline"])), ("Items", "; ".join(items))],
                 ("Supplier response link", url))
    return subject, html_body, text


def approval_email(mission: dict[str, Any], plan: dict[str, Any], review_url: str,
                   due: str | None) -> tuple[str, str, str]:
    subject = f"Approval Required — ReliefMesh Plan V{plan['version']}"
    rows = [("Mission", esc(mission["name"])), ("Plan version", f"V{plan['version']}"),
            ("Total cost", esc(money(plan["total_cost"]))), ("Suppliers", str(supplier_count(plan))),
            ("Delivery deadline", esc(when(mission["delivery_deadline"]))),
            ("Approve before", esc(when(due))), ("Spending ceiling", esc(money(mission.get("budget"))))]
    intro = ("A procurement plan passed policy and optimization and now needs a human financial approval. "
             "Approval happens only inside ReliefMesh, under your own sign-in.")
    html_body = _email(f"Plan V{plan['version']} needs approval", intro, rows, ("Review plan", review_url))
    text = _text(subject, [(k, html.unescape(v)) for k, v in rows], ("Review", review_url))
    return subject, html_body, text


def disruption_email(mission: dict[str, Any], disruption: dict[str, Any], review_url: str) -> tuple[str, str, str]:
    subject = "URGENT — Supply Chain Disruption"
    stale = ", ".join(f"V{v}" for v in disruption.get("stale_versions") or []) or "—"
    rows = [("Supplier", esc(disruption.get("supplier") or "—")), ("Failure type", esc(disruption["failure_type"])),
            ("What happened", esc(disruption["reason"])), ("Affected mission", esc(mission["name"])),
            ("Old plan", f"{esc(stale)} — now STALE"),
            ("Approvals invalidated", str(disruption.get("approvals_invalidated", 0))),
            ("Replanning", esc(disruption.get("replanning") or "queued automatically"))]
    intro = ("A supplier change invalidated the current procurement plan. Any approval of the old plan was revoked "
             "and ReliefMesh is rebuilding the plan. A fresh human approval will be required.")
    html_body = _email("Supply chain disruption", intro, rows, ("Open mission", review_url), tone="#b91c1c")
    text = _text(subject, [(k, html.unescape(v)) for k, v in rows], ("Mission", review_url))
    return subject, html_body, text


def replan_email(mission: dict[str, Any], plan: dict[str, Any], review_url: str,
                 due: str | None) -> tuple[str, str, str]:
    diff = plan.get("difference") or {}
    removed, added = supplier_changes(plan)
    if plan["status"] == "infeasible":
        subject = f"Action Required — ReliefMesh Replan V{plan['version']} Is Infeasible"
        shortages = "<br>".join(esc(f"{s['item']}: short {s.get('shortage')} ({s.get('reason')})")
                                for s in plan.get("shortages") or []) or "—"
        rows = [("Mission", esc(mission["name"])), ("Plan version", f"V{plan['version']}"),
                ("Shortages", shortages), ("Reason", esc("; ".join(diff.get("why") or []) or "—"))]
        intro = "After the disruption no policy-eligible combination of quotes covers the requirements."
        html_body = _email("Replan is infeasible", intro, rows, ("Open mission", review_url), tone="#b91c1c")
        return subject, html_body, _text(subject, [(k, html.unescape(v)) for k, v in rows], ("Mission", review_url))
    subject = "New Procurement Plan Ready for Approval"
    rows = [("Mission", esc(mission["name"])), ("Plan version", f"V{plan['version']}"),
            ("Old cost", esc(money(diff.get("total_cost_before")))), ("New cost", esc(money(plan["total_cost"]))),
            ("Cost delta", esc(signed_money(diff.get("cost_delta")))),
            ("Removed suppliers", esc(", ".join(removed) or "none")),
            ("Added suppliers", esc(", ".join(added) or "none")),
            ("Reason", esc("; ".join(diff.get("why") or []) or "supplier disruption")),
            ("Approve before", esc(when(due)))]
    intro = "ReliefMesh rebuilt the supply plan after a disruption. The prior approval does not carry over."
    html_body = _email(f"Plan V{plan['version']} is ready for approval", intro, rows,
                       (f"Review plan V{plan['version']}", review_url))
    return subject, html_body, _text(subject, [(k, html.unescape(v)) for k, v in rows], ("Review", review_url))


def purchase_order_email(order: dict[str, Any], mission: dict[str, Any], portal_url: str) -> tuple[str, str, str]:
    subject = f"Purchase Order — ReliefMesh {order['po_number']}"
    lines = [f"{row['quantity']:,} × {row.get('line_description') or row['item']} @ {money(row['unit_price'])} = "
             f"{money(row['line_cost'])}" for row in order["lines"]]
    eta = max((row.get("delivery_date") for row in order["lines"] if row.get("delivery_date")), default=None)
    rows = [("PO number", esc(order["po_number"])), ("Buyer", esc(order.get("buyer_organization"))),
            ("Mission", esc(mission["name"])), ("Deliver to", esc(order["delivery_location"])),
            ("Lines", "<br>".join(esc(line) for line in lines)), ("Subtotal", esc(money(order["subtotal"]))),
            ("Committed delivery", esc(when(eta))), ("Plan", f"V{order.get('plan_version')} · hash "
                                                           f"{esc((order.get('plan_hash') or '')[:16])}…")]
    intro = ("A human-approved purchase order was issued to you. Accept or decline it in the ReliefMesh supplier "
             "portal; the PDF copy is attached.")
    html_body = _email(f"Purchase order {order['po_number']}", intro, rows, ("Open supplier portal", portal_url))
    text = _text(subject, [(k, html.unescape(v).replace("<br>", "; ")) for k, v in rows], ("Supplier portal",
                                                                                           portal_url))
    return subject, html_body, text


# ---------------- slack ----------------

def slack_blocks(title: str, fields: list[tuple[str, str]], body: str | None, link: tuple[str, str] | None,
            context: str | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [{"type": "header", "text": {"type": "plain_text", "text": title[:150],
                                                             "emoji": True}}]
    if body:
        out.append({"type": "section", "text": {"type": "mrkdwn", "text": body[:2900]}})
    if fields:
        out.append({"type": "section", "fields": [
            {"type": "mrkdwn", "text": f"*{slack_esc(k)}*\n{v}"[:1900]} for k, v in fields[:10]]})
    if link:
        out.append({"type": "actions", "elements": [{"type": "button", "text": {"type": "plain_text",
                                                                                  "text": link[0][:75]},
                                                         "url": link[1]}]})
    out.append({"type": "context", "elements": [{"type": "mrkdwn", "text": slack_esc(context or FOOTER)}]})
    return out


def slack_approval(mission: dict[str, Any], plan: dict[str, Any], review_url: str,
                   due: str | None) -> tuple[str, list[dict[str, Any]]]:
    text = (f"🚨 ReliefMesh approval required — {mission['name']} Plan V{plan['version']} "
            f"{money(plan['total_cost'])}")
    fields = [("Mission", slack_esc(mission["name"])), ("Plan", f"V{plan['version']}"),
              ("Cost", money(plan["total_cost"])), ("Suppliers", str(supplier_count(plan))),
              ("Deadline", slack_esc(when(mission["delivery_deadline"]))), ("Approve before", slack_esc(when(due)))]
    return text, slack_blocks("🚨 ReliefMesh approval required", fields,
                         "Approval happens in ReliefMesh under the approver's own sign-in.",
                         ("Review Plan", review_url))


def slack_disruption(mission: dict[str, Any], disruption: dict[str, Any],
                     review_url: str) -> tuple[str, list[dict[str, Any]]]:
    stale = ", ".join(f"V{v}" for v in disruption.get("stale_versions") or [])
    supplier = disruption.get("supplier")
    headline = slack_esc(disruption["reason"])
    lines = [f"*{headline}*", f"Mission: {slack_esc(mission['name'])}"]
    if stale:
        lines.append(f"Plan {stale} is now *STALE*.")
    if disruption.get("approvals_invalidated"):
        lines.append("Approval has been *INVALIDATED*.")
    if disruption.get("sent_orders_affected"):
        lines.append(f"{disruption['sent_orders_affected']} already-sent purchase order(s) are flagged for review.")
    lines.append("Automatic replanning has started.")
    text = f"⚠️ Supplier disruption — {disruption['reason']}"
    fields = [("Supplier", slack_esc(supplier or "—")), ("Failure type", slack_esc(disruption["failure_type"]))]
    return text, slack_blocks("⚠️ Supplier disruption", fields, "\n".join(lines), ("Open mission", review_url))


def slack_replan(mission: dict[str, Any], plan: dict[str, Any], review_url: str) -> tuple[str, list[dict[str, Any]]]:
    diff = plan.get("difference") or {}
    if plan["status"] == "infeasible":
        shortages = "\n".join(f"• {slack_esc(s['item'])}: short {s.get('shortage')} ({slack_esc(s.get('reason'))})"
                              for s in plan.get("shortages") or [])
        text = f"⛔ ReliefMesh replan V{plan['version']} is infeasible — {mission['name']}"
        return text, slack_blocks("⛔ Replan is infeasible", [("Mission", slack_esc(mission["name"])),
                                                         ("Plan", f"V{plan['version']}")],
                             f"No policy-eligible quotes cover the requirements.\n{shortages}",
                             ("Open mission", review_url))
    removed, added = supplier_changes(plan)
    body = (f"Old plan: {money(diff.get('total_cost_before'))}\nNew plan: {money(plan['total_cost'])}\n"
            f"Difference: {signed_money(diff.get('cost_delta'))}\n\n"
            f"*Removed:*\n{slack_esc(chr(10).join(removed) or 'none')}\n\n"
            f"*Added:*\n{slack_esc(chr(10).join(added) or 'none')}\n\nFresh approval is required.")
    text = (f"✅ ReliefMesh rebuilt the supply plan — {mission['name']} V{plan['version']} "
            f"{money(plan['total_cost'])} ({signed_money(diff.get('cost_delta'))})")
    return text, slack_blocks("✅ ReliefMesh rebuilt the supply plan", [], body,
                         (f"Review Plan V{plan['version']}", review_url),
                         context=f"Mission: {mission['name']} · " + FOOTER)


def slack_purchase_order(order: dict[str, Any], mission: dict[str, Any], supplier: str,
                         review_url: str) -> tuple[str, list[dict[str, Any]]]:
    eta = max((row.get("delivery_date") for row in order["lines"] if row.get("delivery_date")), default=None)
    text = f"📦 Purchase order issued — {order['po_number']} to {supplier} {money(order['subtotal'])}"
    fields = [("Supplier", slack_esc(supplier)), ("Amount", money(order["subtotal"])),
              ("PO", slack_esc(order["po_number"])), ("Expected delivery", slack_esc(when(eta)))]
    return text, slack_blocks("📦 Purchase order issued", fields, f"Mission: {slack_esc(mission['name'])}",
                         ("Open mission", review_url))


def slack_fulfillment(order: dict[str, Any], mission: dict[str, Any], supplier: str, status: str,
                      note: str, review_url: str) -> tuple[str, list[dict[str, Any]]]:
    label = {"in_fulfillment": "🚚 In fulfillment", "completed": "✅ Delivered", "cancelled": "⛔ Cancelled"}.get(
        status, status)
    text = f"{label} — {order['po_number']} ({supplier}): {note}"
    return text, slack_blocks(f"{label} — {order['po_number']}", [("Supplier", slack_esc(supplier)),
                                                            ("Mission", slack_esc(mission["name"]))],
                         slack_esc(note), ("Open mission", review_url))


def slack_superseded(original_text: str, reason: str) -> tuple[str, list[dict[str, Any]]]:
    text = f"STALE — {original_text}"
    return text, [{"type": "section", "text": {"type": "mrkdwn", "text": f"~{slack_esc(original_text)}~"}},
                  {"type": "context", "elements": [{"type": "mrkdwn",
                                                    "text": f"*STALE* — {slack_esc(reason)}. A new plan "
                                                            "will need its own approval."}]}]


# ---------------- calendar ----------------

def _window(end: datetime, minutes: int = 30) -> tuple[datetime, datetime]:
    return end - timedelta(minutes=minutes), end


def _calendar_body(summary: str, start: datetime, end: datetime, description: list[str], url: str,
                   location: str | None, private: dict[str, str], color: str | None = None,
                   reminders: tuple[int, ...] = (60,)) -> dict[str, Any]:
    body: dict[str, Any] = {
        "summary": summary[:1000],
        "description": "\n".join(description + ["", url, "", FOOTER]),
        "start": {"dateTime": start.astimezone(UTC).isoformat()},
        "end": {"dateTime": end.astimezone(UTC).isoformat()},
        "source": {"title": "ReliefMesh", "url": url},
        "extendedProperties": {"private": private},
        "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": m} for m in reminders]},
        "transparency": "transparent",
    }
    if location:
        body["location"] = location
    if color:
        body["colorId"] = color
    return body


def parse(value: str) -> datetime:
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def calendar_deadline(mission: dict[str, Any], url: str) -> dict[str, Any]:
    start, end = _window(parse(mission["delivery_deadline"]))
    return _calendar_body(
        f"ReliefMesh — Delivery Deadline: {mission['name']}", start, end,
        [f"Delivery location: {mission['delivery_location']}", "Required items:",
         *[f"  • {line}" for line in requirements_lines(mission)]],
        url, mission["delivery_location"], {"reliefmesh_mission_id": mission["id"], "slot": "deadline"},
        reminders=(24 * 60, 120))


def approval_due(mission: dict[str, Any], quotes: list[dict[str, Any]], plan: dict[str, Any]) -> str:
    """Approve before the first allocated quote expires (prices stop binding), never after the deadline."""

    allocated = {row["quote_id"] for row in plan.get("allocations") or []}
    candidates = [parse(q["expires_at"]) for q in quotes if q["id"] in allocated and q.get("expires_at")]
    candidates.append(parse(mission["delivery_deadline"]))
    return min(candidates).isoformat()


def calendar_approval(mission: dict[str, Any], plan: dict[str, Any], due: str, url: str,
                      state: str = "required", reason: str | None = None) -> dict[str, Any]:
    now = datetime.now(UTC)
    due_at = parse(due)
    start = max(now, due_at - timedelta(minutes=30))
    end = max(start + timedelta(minutes=30), due_at)
    version = f"V{plan['version']}"
    titles = {
        "required": f"ReliefMesh — Approval Required: {mission['name']} (Plan {version})",
        "stale": f"STALE — ReliefMesh Approval: {mission['name']} (Plan {version} superseded)",
        "approved": f"Approved — ReliefMesh Plan {version}: {mission['name']}",
        "infeasible": f"Action Required — ReliefMesh Replan {version} infeasible: {mission['name']}",
    }
    details = {
        "required": [f"Plan {version} total: {money(plan['total_cost'])} across {supplier_count(plan)} supplier(s)",
                     f"Approve before: {when(due)} (first allocated quote expiry or the delivery deadline)",
                     f"Delivery deadline: {when(mission['delivery_deadline'])}"],
        "stale": [f"Plan {version} became STALE: {reason or 'a supplier changed'}",
                  "Its approval was invalidated and ReliefMesh started replanning automatically.",
                  "This event will be replaced when the new plan is ready."],
        "approved": [f"Plan {version} was approved for {money(plan['total_cost'])}.",
                     "Purchase orders can now be issued in ReliefMesh."],
        "infeasible": ["No policy-eligible quotes cover the requirements after the disruption.",
                       *[f"  • {s['item']}: short {s.get('shortage')}" for s in plan.get("shortages") or []]],
    }
    colors = {"stale": "8", "approved": "10", "infeasible": "11"}
    return _calendar_body(titles[state], start, end, details[state], url, mission["delivery_location"],
                          {"reliefmesh_mission_id": mission["id"], "slot": "approval",
                           "plan_version": str(plan["version"]), "state": state},
                          color=colors.get(state), reminders=(30,) if state == "required" else ())


def calendar_supplier_eta(order: dict[str, Any], mission: dict[str, Any], supplier: str, url: str,
                          delivered: bool = False) -> dict[str, Any] | None:
    eta = max((row.get("delivery_date") for row in order["lines"] if row.get("delivery_date")), default=None)
    if not eta:
        return None
    start = parse(eta)
    summary = (f"Delivered — {supplier} ({order['po_number']})" if delivered
               else f"ReliefMesh — Supplier Delivery: {supplier}")
    return _calendar_body(
        summary, start, start + timedelta(hours=1),
        [f"Purchase order {order['po_number']} · {money(order['subtotal'])}", f"Mission: {mission['name']}",
         *[f"  • {row['quantity']:,} × {row['item']}" for row in order["lines"]]],
        url, order["delivery_location"], {"reliefmesh_mission_id": mission["id"], "slot": f"eta:{order['id']}"},
        color="10" if delivered else None, reminders=() if delivered else (120,))
