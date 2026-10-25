"""Drive the full operations workflow against a running ReliefMesh API with REAL integrations.

Prerequisite (human, once): sign in to the web app as the coordinator, create the organization,
and connect Google + Slack on /settings/integrations. This script then plays every other role
with real accounts (approver and two suppliers on plus-addresses of one inbox) and prints the
external deliveries each step produced.

    RM_API=http://localhost:8300 RM_COORDINATOR_EMAIL=you+coord@gmail.com RM_PASSWORD=... \
    RM_ALIAS_BASE=you@gmail.com python scripts/ops_live_check.py

Nothing is mocked: emails go through the organization's Gmail, events land on its calendar.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import UTC, datetime, timedelta

import httpx

API = os.environ.get("RM_API", "http://localhost:8300").rstrip("/")
COORDINATOR = os.environ["RM_COORDINATOR_EMAIL"]
PASSWORD = os.environ["RM_PASSWORD"]
LOCAL, DOMAIN = os.environ["RM_ALIAS_BASE"].split("@")
RUN = datetime.now(UTC).strftime("%H%M%S")
client = httpx.Client(base_url=API, timeout=60)


def alias(tag: str) -> str:
    return f"{LOCAL}+{tag}{RUN}@{DOMAIN}"


def call(method: str, path: str, token: str | None = None, **kwargs) -> dict | list:
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = client.request(method, path, headers=headers, **kwargs)
    if response.status_code >= 400:
        sys.exit(f"{method} {path} -> {response.status_code}: {response.text[:400]}")
    return response.json()


def account(email: str, role: str) -> str:
    response = client.post("/v1/auth/register", json={"email": email, "password": PASSWORD, "role": role})
    if response.status_code == 409:
        response = client.post("/v1/auth/login", json={"email": email, "password": PASSWORD})
    response.raise_for_status()
    return response.json()["access_token"]


def wait(predicate, label: str, seconds: int = 180):
    deadline = time.time() + seconds
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(2)
    sys.exit(f"timed out waiting for {label}")


def settled(token: str, mission_id: str) -> list[dict]:
    def check():
        rows = call("GET", f"/v1/missions/{mission_id}/operations", token)
        return rows if rows and all(r["status"] not in {"PENDING", "SENDING", "RETRYING"} for r in rows) else None
    return wait(check, "deliveries to settle")


def report(rows: list[dict], events: set[str]) -> None:
    for row in sorted((r for r in rows if r["event_type"] in events), key=lambda r: r["created_at"]):
        print(f"   {row['event_type']:<24} {row['channel']:<8} {row['status']:<14} -> {row['target'][:44]:<44} "
              f"{(row['provider_id'] or '')[:24]} {row['last_error'] or ''}")


coordinator = account(COORDINATOR, "coordinator")
organization = call("GET", "/v1/organizations", coordinator)[0]
org_id = organization["id"]
view = call("GET", f"/v1/organizations/{org_id}/integrations", coordinator)
print(f"Org {organization['name']}: google={view['google']['status']} slack={view['slack']['status']} "
      f"email={view['email']['mode']}/{view['email']['transport']}")

approver_email = alias("approver")
approver = account(approver_email, "coordinator")
invite = call("POST", f"/v1/organizations/{org_id}/members", coordinator, json={"email": approver_email,
                                                                              "role": "approver"})
call("POST", f"/v1/org-invites/{invite['invite_url'].rsplit('/', 1)[1]}/accept", approver)
suppliers = {name: (alias(name), account(alias(name), "supplier")) for name in ("bayside", "sierra")}

print("1. Coordinator creates mission -> Calendar delivery deadline")
mission = call("POST", "/v1/missions", coordinator, json={
    "organization_id": org_id, "name": f"Oakland Shelter Supplies {RUN}", "delivery_location": "Oakland, CA",
    "delivery_deadline": (datetime.now(UTC) + timedelta(days=4)).isoformat(), "budget": "8000.00",
    "currency": "USD", "requirements": [{"item": "blankets", "quantity": 400}, {"item": "water cases", "quantity": 200}]})
mission_id = mission["id"]
report(settled(coordinator, mission_id), {"mission_created"})

print("2. Coordinator invites suppliers -> Gmail RFQ")
tokens = {}
for name, (email, _) in suppliers.items():
    invitation = call("POST", f"/v1/missions/{mission_id}/invitations", coordinator, json={"supplier_email": email})
    print(f"   RFQ to {email}: {invitation['delivery_status']} via {invitation.get('delivery', {}).get('provider')}")
    tokens[name] = invitation.get("token")
if not all(tokens.values()):
    sys.exit("RFQ emails were sent; open each RFQ link from the inbox to continue (tokens are not exposed).")

print("3. Suppliers submit quotes")
prices = {"bayside": ("6.00", "11.00", "Bayside Relief Supply Co"), "sierra": ("7.50", "12.50", "Sierra Backup Provisions")}
quote_ids = {}
for name, (_, token) in suppliers.items():
    call("POST", f"/v1/supplier-invitations/{tokens[name]}/accept", token)
    blanket, water, legal = prices[name]
    quote = call("POST", "/v1/quotes", token, json={
        "invitation_token": tokens[name], "expires_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
        "shipping_cost": "40.00", "supplier_profile": {"legal_name": legal, "country": "US"},
        "lines": [{"item": "blankets", "unit_price": blanket, "available_quantity": 400,
                   "delivery_date": (datetime.now(UTC) + timedelta(days=2)).isoformat()},
                  {"item": "water cases", "unit_price": water, "available_quantity": 200,
                   "delivery_date": (datetime.now(UTC) + timedelta(days=2, hours=6)).isoformat()}]})
    quote_ids[name] = quote["id"]
wait(lambda: all(j["status"] in {"succeeded", "failed"} for j in call("GET", f"/v1/missions/{mission_id}/jobs",
                                                                       coordinator)), "evidence checks")

print("4. Optimizer creates Plan V1 -> Gmail approval, Slack alert, Calendar approval")
plan = call("POST", f"/v1/missions/{mission_id}/optimize", coordinator)
if plan["status"] != "feasible":
    sys.exit(f"plan v1 is {plan['status']}; check policy evidence on the mission page")
report(settled(coordinator, mission_id), {"approval_required"})

print("5. Approver approves Plan V1")
call("POST", f"/v1/plans/{plan['plan_id']}/approve", approver)
report(settled(coordinator, mission_id), {"plan_approved"})

print("6. Supplier fails (Bayside withdraws) -> Slack + Gmail disruption, Calendar approval marked stale")
call("POST", f"/v1/quotes/{quote_ids['bayside']}/withdraw", suppliers["bayside"][1])
plans = wait(lambda: (lambda rows: rows if len(rows) >= 2 else None)(
    call("GET", f"/v1/missions/{mission_id}/plans", coordinator)), "automatic replan")
v2 = plans[0]
rows = settled(coordinator, mission_id)
report(rows, {"supplier_disrupted"})
print(f"7. ReliefMesh replanned automatically -> Plan V{v2['version']} {v2['status']} ${v2['total_cost']} "
      f"({v2['difference'].get('cost_delta')})")
report(rows, {"plan_replanned"})

print("8. Approver approves Plan V2; coordinator issues the PO -> Gmail PO (PDF), Slack, Drive archive")
call("POST", f"/v1/plans/{v2['id']}/approve", approver)
orders = call("POST", f"/v1/plans/{v2['id']}/purchase-orders", coordinator, headers={"Idempotency-Key": f"live-{RUN}"})
for order in orders:
    sent = call("POST", f"/v1/purchase-orders/{order['id']}/send", coordinator, json={"confirm": True})
    print(f"   {sent['po_number']} sent ({sent['events'][-1].get('email_delivery')} via "
          f"{sent['events'][-1].get('email_provider')})")
    supplier_token = next(token for email, token in suppliers.values() if email == order["supplier_email"])
    call("POST", f"/v1/purchase-orders/{order['id']}/supplier-response", supplier_token, json={"accepted": True})
    call("POST", f"/v1/purchase-orders/{order['id']}/fulfillment", supplier_token,
         json={"status": "completed", "note": "Delivered to Oakland shelter dock 3"})
rows = settled(coordinator, mission_id)
report(rows, {"plan_approved", "purchase_order_sent", "purchase_order_accepted", "fulfillment_updated"})
failed = [r for r in rows if r["status"] == "FAILED"]
print(f"\nMission {mission_id}: {len(rows)} deliveries, {sum(r['status'] == 'SENT' for r in rows)} SENT, "
      f"{len(failed)} FAILED")
sys.exit(1 if failed else 0)
