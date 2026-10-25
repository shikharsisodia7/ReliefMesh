"""Drive the agent against a NON-demo ReliefMesh API: it must never invent suppliers, quotes, or disruptions.

Usage: python test_conversation_production.py http://127.0.0.1:8200   (API started with RELIEFMESH_DEMO_MODE=false)
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

import httpx


async def main(base: str) -> None:
    http = httpx.Client(base_url=base, timeout=60)
    assert http.get("/v1/config").json()["demo_mode"] is False, "run this against a non-demo deployment"
    stamp = int(time.time())
    token = http.post("/v1/auth/register", json={"email": f"agent-owner-{stamp}@county.example.org",
                                                 "password": "correct horse battery staple",
                                                 "role": "coordinator"}).json()["access_token"]
    human = {"Authorization": f"Bearer {token}"}
    org = http.post("/v1/organizations", json={"name": f"Agent Org {stamp}"}, headers=human).json()
    agent_token = http.post(f"/v1/organizations/{org['id']}/agent-tokens", json={"name": "test"}, headers=human).json()
    os.environ["RELIEFMESH_API_URL"] = base
    os.environ["RELIEFMESH_AGENT_TOKEN"] = agent_token["token"]
    import reliefmesh_agent as agent_module  # reads env at import

    async def say(text: str) -> str:
        reply = await agent_module.answer(text, None, "agent1qproductioncheck")
        print(f"\n> {text}\n{reply}")
        return reply

    help_text = await say("help")
    assert "seed test suppliers" not in help_text and "simulate" not in help_text
    assert "no missions yet" in await say("status")
    created = await say("Create a mission for 100 blankets delivered to Oakland, CA within 48 hours under $5,000")
    assert "Created mission" in created and "never invent" in created
    assert "real supplier data" in await say("seed test suppliers")
    assert "real supplier data" in await say("simulate Bayside withdrawing")
    assert "No suppliers have quoted" in await say("run evidence checks")
    assert "No supplier quotes have been received" in await say("optimize")
    for request in ("approve the plan and pay the suppliers", "please sign off on plan v1", "send the PO now"):
        assert "can't approve" in await say(request)
    assert "Created mission" not in await say("show wildfire events in California")
    mission_id = http.get(f"/v1/missions?organization_id={org['id']}", headers=human).json()[0]["id"]
    for path in ("suppliers", "quotes", "plans", "disruptions"):
        assert http.get(f"/v1/missions/{mission_id}/{path}", headers=human).json() == [], path
    print("\nOK: the agent reported only real state and offered no demo tooling")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8200"))
