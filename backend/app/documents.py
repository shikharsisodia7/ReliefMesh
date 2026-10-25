"""Procurement documents rendered from stored records (PO and plan PDFs, audit export)."""

from __future__ import annotations

import json
from io import BytesIO
from typing import Any

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def purchase_order_pdf(order: dict[str, Any]) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle(order["po_number"])
    pdf.drawString(72, 740, f"ReliefMesh Purchase Order {order['po_number']}")
    pdf.drawString(72, 720, f"Buyer: {order['buyer_organization']}")
    pdf.drawString(72, 700, f"Supplier: {order['supplier_email']}")
    pdf.drawString(72, 680, f"Delivery: {order['delivery_location']}")
    y = 650
    for line in order["lines"]:
        pdf.drawString(72, y, f"{line['item']}: {line['quantity']} x {line['unit_price']} = {line['line_cost']}")
        y -= 20
    pdf.drawString(72, y - 10, f"Approval reference: {order['approval_id']}")
    pdf.drawString(72, y - 30, f"Plan v{order.get('plan_version', '?')} hash: {order.get('plan_hash', '')[:32]}")
    pdf.save()
    return buffer.getvalue()


def plan_pdf(plan: dict[str, Any], mission: dict[str, Any], approval: dict[str, Any] | None) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle(f"{mission['name']} plan v{plan['version']}")
    rows = [
        f"ReliefMesh Procurement Plan v{plan['version']} - {mission['name']}",
        f"Status: {plan['status']}   Total: {plan['total_cost']} {plan.get('currency', 'USD')}",
        f"Delivery: {mission['delivery_location']} by {mission['delivery_deadline']}",
        f"Plan hash: {plan.get('plan_hash', '')}",
        f"Policy fingerprint: {(plan.get('policy') or {}).get('fingerprint', '')}",
    ]
    if approval:
        rows.append(f"Approved by {approval.get('approver_email')} at {approval.get('approved_at')} "
                    f"({approval.get('segregation_of_duties')})")
    rows.append("")
    rows += [f"{a.get('supplier_email')}: {a['quantity']} x {a['item']} @ {a['unit_price']} = {a['line_cost']}"
             for a in plan.get("allocations") or []]
    y = 740
    for row in rows:
        if y < 72:
            pdf.showPage()
            y = 740
        pdf.drawString(72, y, row[:110])
        y -= 18
    pdf.save()
    return buffer.getvalue()


def audit_export(mission: dict[str, Any], events: list[dict[str, Any]], verification: dict[str, Any]) -> bytes:
    ordered = sorted(events, key=lambda row: row.get("sequence", 0))
    return json.dumps({"mission_id": mission["id"], "mission": mission["name"], "verification": verification,
                       "events": ordered}, indent=2, default=str).encode()
