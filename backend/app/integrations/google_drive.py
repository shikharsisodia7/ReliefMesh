"""Google Drive adapter (``drive.file``): archive copies of procurement documents.

Drive only ever holds copies. ReliefMesh's database and hash-chained audit log remain the
record; a Drive file's id/URL is stored back on the delivery so the archive is traceable.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx

from .connections import IntegrationError
from .google_auth import raise_for_google

API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
FOLDER = "application/vnd.google-apps.folder"
FIELDS = "id,name,webViewLink,mimeType,trashed"


async def _request(client: httpx.AsyncClient, token: str, method: str, url: str, action: str,
                   **kwargs: Any) -> httpx.Response:
    headers = {"Authorization": f"Bearer {token}", **kwargs.pop("headers", {})}
    try:
        return await client.request(method, url, headers=headers, **kwargs)
    except httpx.HTTPError as exc:
        raise IntegrationError(f"{action}: Google Drive unreachable ({type(exc).__name__})", retryable=True) from exc


async def get_file(client: httpx.AsyncClient, token: str, file_id: str) -> dict[str, Any] | None:
    response = await _request(client, token, "GET", f"{API}/files/{file_id}", "Drive lookup",
                              params={"fields": FIELDS})
    if response.status_code == 404:
        return None
    raise_for_google(response, "Drive lookup")
    body = response.json()
    return None if body.get("trashed") else body


async def ensure_folder(client: httpx.AsyncClient, token: str, name: str, parent: str | None,
                        known_id: str | None) -> dict[str, Any]:
    if known_id and (existing := await get_file(client, token, known_id)):
        return existing
    metadata: dict[str, Any] = {"name": name, "mimeType": FOLDER}
    if parent:
        metadata["parents"] = [parent]
    response = await _request(client, token, "POST", f"{API}/files", "Drive folder", params={"fields": FIELDS},
                              json=metadata)
    raise_for_google(response, "Drive folder")
    return response.json()


async def upload(client: httpx.AsyncClient, token: str, name: str, content: bytes, mime_type: str,
                 parent: str, existing_id: str | None = None) -> dict[str, Any]:
    """Create a file, or replace the content of the file this archive slot already owns."""

    boundary = f"reliefmesh-{uuid.uuid4().hex}"
    metadata: dict[str, Any] = {"name": name} if existing_id else {"name": name, "mimeType": mime_type,
                                                                  "parents": [parent]}
    body = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(metadata)}\r\n"
        f"--{boundary}\r\nContent-Type: {mime_type}\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--".encode()
    method, url = ("PATCH", f"{UPLOAD}/{existing_id}") if existing_id else ("POST", UPLOAD)
    response = await _request(client, token, method, url, "Drive upload", content=body,
                              params={"uploadType": "multipart", "fields": FIELDS},
                              headers={"Content-Type": f"multipart/related; boundary={boundary}"})
    if existing_id and response.status_code == 404:
        return await upload(client, token, name, content, mime_type, parent)
    raise_for_google(response, "Drive upload")
    return response.json()
