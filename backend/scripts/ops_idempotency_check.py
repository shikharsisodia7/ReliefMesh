"""Idempotency against REAL providers, using the running deployment's configuration and database.

    python scripts/ops_idempotency_check.py <mission_id>

1. Re-emits the mission's already-delivered approval/replan events: no new deliveries may appear.
2. Replays an already-SENT calendar delivery for real: Google answers 409 on the fixed event id,
   ReliefMesh updates in place, and the slot still maps to exactly one Google event.
3. Re-attempts an already-SENT Gmail delivery: it must be a no-op (no second email).
"""

from __future__ import annotations

import asyncio
import sys

from app.integrations import google_auth, google_calendar
from app.main import create_app


async def main(mission_id: str) -> int:
    app = create_app()
    services = app.state.services
    store, ops = services.store, services.ops
    mission = await store.get("missions", mission_id)
    failures = 0

    before = len(await store.find("ops_deliveries", mission_id=mission_id))
    for event in await store.find("ops_events", mission_id=mission_id):
        if event["type"] in {"approval_required", "plan_replanned", "plan_approved", "purchase_order_sent"}:
            await ops.emit(event["type"], mission, subject_id=event["subject_id"], version=event["version"],
                           data=event["data"])
    after = len(await store.find("ops_deliveries", mission_id=mission_id))
    print(f"1. duplicate application events: deliveries {before} -> {after}", "OK" if after == before else "FAIL")
    failures += after != before

    calendar_rows = [r for r in await store.find("ops_deliveries", mission_id=mission_id, channel="calendar",
                                                  status="SENT") if r["target"] == "approval"]
    latest = max(calendar_rows, key=lambda r: r["sequence"])
    latest.update(status="PENDING")
    await store.replace("ops_deliveries", latest["id"], latest)
    await ops.attempt(latest["id"])
    replayed = await store.get("ops_deliveries", latest["id"])
    async with services.hub.client(timeout=20) as client:
        token, connection = await google_auth.access_token(store, services.vault, services.settings, client,
                                                           mission["organization_id"], "calendar")
        event = await google_calendar.get_event(client, token, connection["calendar_id"],
                                                latest["payload"]["event_id"])
    print(f"2. replayed calendar upsert ({latest['event_type']}): {replayed['status']}; Google event "
          f"{event['id']} status={event['status']} summary={event['summary']!r}")
    failures += replayed["status"] != "SENT" or event["id"] != latest["payload"]["event_id"]

    gmail = next(r for r in await store.find("ops_deliveries", mission_id=mission_id, channel="gmail", status="SENT"))
    attempts = gmail["attempts"]
    await ops.attempt(gmail["id"])
    again = await store.get("ops_deliveries", gmail["id"])
    print(f"3. re-attempt of SENT Gmail delivery: attempts {attempts} -> {again['attempts']}",
          "OK" if again["attempts"] == attempts else "FAIL")
    failures += again["attempts"] != attempts
    await asyncio.gather(*services.jobs, return_exceptions=True)
    return failures


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1])))
