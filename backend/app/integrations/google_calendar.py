"""Google Calendar adapter (``calendar.app.created``): a dedicated ReliefMesh calendar.

Event IDs are deterministic (base32hex of a hash of org/mission/slot), so a retried or
duplicated application event can only ever update the one Google event for that slot.
ReliefMesh stays authoritative: these events are reminders that mirror its state.
"""

from __future__ import annotations

import base64
import hashlib
from typing import Any
from urllib.parse import quote

import httpx

from .connections import IntegrationError
from .google_auth import raise_for_google

API = "https://www.googleapis.com/calendar/v3"
CALENDAR_NAME = "ReliefMesh Operations"


def event_id(organization_id: str, mission_id: str, slot: str) -> str:
    digest = hashlib.sha256(f"{organization_id}|{mission_id}|{slot}".encode()).digest()[:20]
    # Google allows a-v and 0-9 (base32hex), 5-1024 chars.
    return "rm" + base64.b32hexencode(digest).decode().lower().rstrip("=")


async def _call(client: httpx.AsyncClient, token: str, method: str, path: str, action: str,
                json: dict[str, Any] | None = None) -> httpx.Response:
    try:
        return await client.request(method, f"{API}{path}", headers={"Authorization": f"Bearer {token}"}, json=json)
    except httpx.HTTPError as exc:
        raise IntegrationError(f"{action}: Google Calendar unreachable ({type(exc).__name__})", retryable=True) from exc


async def ensure_calendar(client: httpx.AsyncClient, token: str, calendar_id: str | None) -> dict[str, Any]:
    """Return the ReliefMesh calendar, creating it once. A deleted calendar is recreated."""

    if calendar_id:
        response = await _call(client, token, "GET", f"/calendars/{quote(calendar_id)}", "Calendar lookup")
        if response.status_code == 200:
            return response.json()
        if response.status_code not in {403, 404, 410}:
            raise_for_google(response, "Calendar lookup")
    response = await _call(client, token, "POST", "/calendars", "Calendar create", json={
        "summary": CALENDAR_NAME,
        "description": "Delivery deadlines, approval windows, and supplier ETAs from ReliefMesh. "
                       "ReliefMesh is the system of record; edits here are not read back.",
        "timeZone": "UTC",
    })
    raise_for_google(response, "Calendar create")
    return response.json()


async def upsert_event(client: httpx.AsyncClient, token: str, calendar_id: str, event: str,
                       body: dict[str, Any]) -> dict[str, Any]:
    """Insert with a fixed id; if the id exists (even cancelled), overwrite and re-confirm it."""

    payload = {**body, "id": event, "status": body.get("status", "confirmed")}
    path = f"/calendars/{quote(calendar_id)}/events"
    response = await _call(client, token, "POST", path, "Calendar insert", json=payload)
    if response.status_code == 409:
        response = await _call(client, token, "PUT", f"{path}/{event}", "Calendar update", json=payload)
    raise_for_google(response, "Calendar upsert")
    return response.json()


async def cancel_event(client: httpx.AsyncClient, token: str, calendar_id: str, event: str) -> bool:
    """Delete an event; an already-deleted or never-created event counts as cancelled."""

    response = await _call(client, token, "DELETE", f"/calendars/{quote(calendar_id)}/events/{event}",
                           "Calendar delete")
    if response.status_code in {200, 204, 404, 410}:
        return response.status_code in {200, 204}
    raise_for_google(response, "Calendar delete")
    return False


async def get_event(client: httpx.AsyncClient, token: str, calendar_id: str, event: str) -> dict[str, Any] | None:
    response = await _call(client, token, "GET", f"/calendars/{quote(calendar_id)}/events/{event}", "Calendar get")
    if response.status_code == 404:
        return None
    raise_for_google(response, "Calendar get")
    return response.json()
