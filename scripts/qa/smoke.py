"""Safe authenticated smoke check for an already-deployed ReliefMesh API.

It never creates data, sends email, runs optimization, or triggers external integrations.
"""

from __future__ import annotations

import json
import os
from urllib.parse import urlencode

import httpx


def fail(message: str) -> None:
    print(json.dumps({"status": "fail", "message": message}))
    raise SystemExit(1)


def main() -> None:
    base_url = os.environ.get("RELIEFMESH_API_URL", "").rstrip("/")
    email = os.environ.get("RELIEFMESH_TEST_EMAIL")
    password = os.environ.get("RELIEFMESH_TEST_PASSWORD")
    if not base_url:
        fail("RELIEFMESH_API_URL is required")

    with httpx.Client(base_url=base_url, timeout=15, follow_redirects=False) as client:
        health = client.get("/health")
        if health.status_code != 200:
            fail(f"health returned HTTP {health.status_code}")
        report: dict[str, object] = {"status": "pass", "health": health.json(), "checks": ["health"]}

        if not email or not password:
            report["auth"] = "skipped: set RELIEFMESH_TEST_EMAIL and RELIEFMESH_TEST_PASSWORD"
            print(json.dumps(report))
            return

        login = client.post("/v1/auth/login", json={"email": email, "password": password})
        if login.status_code != 200:
            fail(f"login returned HTTP {login.status_code}")
        token = login.json().get("access_token")
        if not token:
            fail("login response did not contain an access token")
        headers = {"Authorization": f"Bearer {token}"}
        me = client.get("/v1/me", headers=headers)
        organizations = client.get("/v1/organizations", headers=headers)
        if me.status_code != 200 or organizations.status_code != 200:
            fail(f"authenticated reachability failed: me={me.status_code}, organizations={organizations.status_code}")
        report["checks"] = ["health", "login", "me", "organizations"]

        rows = organizations.json()
        if rows:
            organization_id = rows[0]["id"]
            path = f"/v1/missions?{urlencode({'organization_id': organization_id})}"
            missions = client.get(path, headers=headers)
            if missions.status_code != 200:
                fail(f"mission API returned HTTP {missions.status_code}")
            report["checks"].append("missions")
            report["mission_count"] = len(missions.json())
        else:
            report["missions"] = "skipped: test user has no organization"
        print(json.dumps(report))


if __name__ == "__main__":
    main()
