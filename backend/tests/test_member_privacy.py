"""Pending org invites are visible to admins only, whatever order memberships are stored in."""

from __future__ import annotations

import httpx
import pytest

from conftest import auth, register


@pytest.mark.anyio
async def test_non_admin_never_sees_pending_invites_even_when_an_admin_row_is_last(client: httpx.AsyncClient) -> None:
    owner = await register(client, "owner@county.example.org", "coordinator")
    org = (await client.post("/v1/organizations", json={"name": "County OES"}, headers=auth(owner))).json()

    async def join(email: str, role: str) -> str:
        invite = (await client.post(f"/v1/organizations/{org['id']}/members", headers=auth(owner),
                                    json={"email": email, "role": role})).json()
        member = await register(client, email, "coordinator")
        accepted = await client.post(f"/v1/org-invites/{invite['invite_url'].rsplit('/', 1)[1]}/accept",
                                     headers=auth(member))
        assert accepted.status_code == 200, accepted.text
        return member

    viewer = await join("viewer@county.example.org", "coordinator")
    await join("second-admin@county.example.org", "admin")  # an admin membership stored after the viewer's
    await client.post(f"/v1/organizations/{org['id']}/members", headers=auth(owner),
                      json={"email": "pending@county.example.org", "role": "approver"})

    as_viewer = (await client.get(f"/v1/organizations/{org['id']}/members", headers=auth(viewer))).json()
    assert as_viewer["pending"] == []
    as_owner = (await client.get(f"/v1/organizations/{org['id']}/members", headers=auth(owner))).json()
    assert [row["email"] for row in as_owner["pending"]] == ["pending@county.example.org"]
