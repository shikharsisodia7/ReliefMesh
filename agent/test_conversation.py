"""Drive the agent's real answer() path against a running ReliefMesh API.

Usage: python test_conversation.py http://127.0.0.1:8100
Creates a coordinator + org + agent token, then runs an ASI:One-style conversation and
asserts each reply reflects persisted backend state. Only the agent-token API is used for
the conversation itself (seeding TEST suppliers and approving are human actions).
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

import httpx


async def main(base: str) -> None:
    http = httpx.Client(base_url=base, timeout=60)
    stamp = int(time.time())
    token = http.post("/v1/auth/register", json={"email": f"agent-owner-{stamp}@example.com",
                                                 "password": "correct horse battery staple",
                                                 "role": "coordinator"}).json()["access_token"]
    human = {"Authorization": f"Bearer {token}"}
    org = http.post("/v1/organizations", json={"name": f"Agent Test {stamp}"}, headers=human).json()
    agent_token = http.post(f"/v1/organizations/{org['id']}/agent-tokens", json={"name": "test"}, headers=human).json()
    os.environ["RELIEFMESH_API_URL"] = base
    os.environ["RELIEFMESH_AGENT_TOKEN"] = agent_token["token"]
    import reliefmesh_agent as agent_module  # read env at import

    async def say(text: str, sender: str = "agent1qjudge") -> str:
        reply = await agent_module.answer(text, None, sender)
        print(f"\n[{sender[-8:]}]> {text}\n{reply}")
        return reply

    events = await say("show wildfire events")
    assert "EONET" in events
    event_id = events.split("`")[1]
    created = await say(f"Create a mission for 100 blankets delivered to Oakland, CA within 48 hours under $5,000 for event {event_id}")
    assert "Created mission" in created
    mission_id = http.get(f"/v1/missions?organization_id={org['id']}", headers=human).json()[0]["id"]
    assert http.get(f"/v1/missions/{mission_id}", headers=human).json()["created_via"] == "agent"
    other = await say("status", sender="agent1qsomeoneelse")
    assert "no missions yet" in other  # a different ASI:One user cannot see this mission
    seeded = await say("seed test suppliers")
    assert "TEST" in seeded and "Pioneer Logistics Supply" in seeded
    for _ in range(90):
        jobs = http.get(f"/v1/missions/{mission_id}/jobs", headers=human).json()
        if jobs and all(j["status"] in {"succeeded", "failed"} for j in jobs):
            break
        time.sleep(1)
    evidence = await say("run evidence checks")
    assert "Pioneer Logistics Supply (TEST): **NEEDS_REVIEW**" in evidence
    plan = await say("optimize the plan")
    assert "Plan v1" in plan and "Withheld by policy: Pioneer Logistics Supply" in plan
    why = await say("why was Pioneer rejected?")
    assert "zero allocation" in why and "SANCTIONS_POTENTIAL_MATCH" in why

    # Continuity questions: every number in the reply must be the stored deterministic analysis's number.
    def continuity_view() -> dict:
        for _ in range(90):
            view = http.get(f"/v1/missions/{mission_id}/continuity", headers=human).json()
            if view["state"] == "COMPLETE":
                return view
            time.sleep(1)
        raise AssertionError("continuity analysis did not complete")

    analysis = continuity_view()["analysis"]
    n1 = analysis["metrics"]["n1_survivability"]
    spof = await say("which supplier is our biggest single point of failure?")
    assert f"N-1 survivability {n1['survives']}/{n1['tested']}" in spof and "HYPOTHETICAL" in spof
    allocated = analysis["n1_scenarios"][0]
    survive = await say(f"can this plan survive losing {allocated['supplier']}?")
    assert allocated["supplier"] in survive and allocated["status"].lower() in survive.lower()
    resilient = await say("what's the cheapest resilient alternative?")
    alternative = analysis["resilient_alternative"]
    if n1["tested"] and n1["survives"] == n1["tested"]:
        assert "costs nothing extra" in resilient
    elif alternative["status"] == "AVAILABLE":
        total = f"{float(alternative['total_cost']):,.2f}"
        assert total in resilient, (total, resilient)
    else:
        assert "no" in resilient.lower()
    approve = http.post(f"/v1/plans/{http.get(f'/v1/missions/{mission_id}/plans', headers=human).json()[0]['id']}/approve",
                        headers=human)
    assert approve.status_code == 201
    simulated = await say("simulate Bayside withdrawing")
    assert "withdrew its quote" in simulated
    blocked = await say("simulate Golden Gate cutting inventory", sender="agent1qsomeoneelse")
    assert "no missions yet" in blocked
    for _ in range(60):
        if len(http.get(f"/v1/missions/{mission_id}/plans", headers=human).json()) >= 2:
            break
        time.sleep(1)
    changed = await say("what changed after the disruption?")
    assert "withdrew" in changed and "v1 → v2" in changed and "invalidated" in changed
    between = await say("what changed between plan v1 and v2?")
    assert "Plan v1 → v2" in between
    fragile = await say("which mission is most fragile?")
    assert "Ranked by deterministic fragility" in fragile or "None of your missions" in fragile
    status = await say("status")
    assert "Latest plan v2" in status
    print("\nCONVERSATION OK")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8100"))
