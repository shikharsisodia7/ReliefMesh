"""End-to-end smoke test against a DEMO ReliefMesh API (RELIEFMESH_DEMO_MODE=true) using LIVE public data.

Production has no seeded suppliers; verify production with real supplier accounts instead.

Usage: python scripts/smoke.py http://127.0.0.1:8100
Creates a coordinator + org, picks a real open NASA EONET event, seeds labeled TEST suppliers,
waits for live evidence checks, optimizes, approves, disrupts, waits for the autonomous replan,
re-approves, and verifies the audit chain. Exits non-zero on any failed expectation.
"""

from __future__ import annotations

import sys
import time
from datetime import UTC, datetime, timedelta

import httpx


def main(base: str) -> None:
    client = httpx.Client(base_url=base, timeout=90)
    stamp = int(time.time())
    reg = client.post("/v1/auth/register", json={"email": f"smoke-{stamp}@reliefmesh-smoke.example.com",
                                                  "password": "correct horse battery staple", "role": "coordinator"})
    reg.raise_for_status()
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    org = client.post("/v1/organizations", json={"name": f"Smoke Relief {stamp}", "demo": True}, headers=headers).json()
    events = client.get("/v1/emergency-events").json()
    us_events = [e for e in events if e.get("state")] or events
    event = us_events[0]
    print(f"EONET event: {event['id']} {event['title']} [{event['provenance']}] state={event.get('state')}")
    mission = client.post("/v1/missions", headers=headers, json={
        "organization_id": org["id"], "name": "Smoke: shelter blankets", "emergency_event_id": event["id"],
        "delivery_location": f"Response staging, {event.get('state') or 'CA'}",
        "delivery_deadline": (datetime.now(UTC) + timedelta(days=4)).isoformat(), "budget": "5000.00",
        "currency": "USD", "requirements": [{"item": "blankets", "quantity": 100}],
    })
    mission.raise_for_status()
    mid = mission.json()["id"]
    assert mission.json()["emergency_event"]["id"] == event["id"], "event snapshot missing"
    seed = client.post(f"/v1/missions/{mid}/demo/seed", headers=headers).json()
    wait_jobs(client, headers, mid)
    suppliers = client.get(f"/v1/missions/{mid}/suppliers", headers=headers).json()
    for row in suppliers:
        ev = row["latest_evidence"]
        print(f"  {row['supplier']['legal_name']:32} policy={row['policy']['status']:13} "
              + " ".join(f"{k.split('_')[0]}={v['status']}/{v['provenance']}" for k, v in sorted(ev.items())))
    plan = client.get(f"/v1/plans/{client.post(f'/v1/missions/{mid}/optimize', headers=headers).json()['plan_id']}",
                      headers=headers).json()
    print(f"Plan v{plan['version']} {plan['status']} total ${plan['total_cost']}: "
          + ", ".join(f"{a['supplier_email'].split('@')[0]}={a['quantity']}" for a in plan["allocations"]))
    assert plan["status"] == "feasible", plan.get("shortages")
    approval = client.post(f"/v1/plans/{plan['id']}/approve", headers=headers)
    assert approval.status_code == 201, approval.text
    target = next(r for r in suppliers if r["supplier"]["legal_name"] == "Bayside Relief Supply Co")
    disruption = client.post(f"/v1/missions/{mid}/disruptions", headers=headers,
                             json={"kind": "withdraw", "supplier_id": target["supplier"]["id"]})
    assert disruption.status_code == 202, disruption.text
    deadline = time.time() + 60
    while time.time() < deadline:
        plans = client.get(f"/v1/missions/{mid}/plans", headers=headers).json()
        if plans[0]["version"] > plan["version"]:
            break
        time.sleep(1)
    v2 = plans[0]
    print(f"Plan v{v2['version']} {v2['status']} total ${v2['total_cost']} delta {v2['difference']['cost_delta']} "
          f"why={v2['difference']['why']}")
    approvals = client.get(f"/v1/missions/{mid}/approvals", headers=headers).json()
    assert approvals[0]["status"] == "invalidated", approvals[0]
    assert client.post(f"/v1/plans/{v2['id']}/approve", headers=headers).status_code == 201
    verify = client.get(f"/v1/missions/{mid}/audit/verify", headers=headers).json()
    assert verify["valid"], verify
    print(f"Audit chain valid: {verify['length']} events, head {verify['head_hash'][:16]}")
    print(f"SMOKE OK mission={mid}")


def wait_jobs(client: httpx.Client, headers: dict, mission_id: str, timeout: float = 120) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        jobs = client.get(f"/v1/missions/{mission_id}/jobs", headers=headers).json()
        if jobs and all(job["status"] in {"succeeded", "failed"} for job in jobs):
            failed = [job for job in jobs if job["status"] == "failed"]
            assert not failed, failed
            return
        time.sleep(1)
    raise AssertionError("jobs did not finish")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8100")
