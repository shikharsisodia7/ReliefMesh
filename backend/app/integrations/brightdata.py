"""Live public website snapshots for supplier leads via Bright Data Web Unlocker."""

from __future__ import annotations

import asyncio
import html
import ipaddress
import re
import socket
from urllib.parse import urlsplit, urlunsplit

from .http import AdapterResult, IntegrationHub

API_URL = "https://api.brightdata.com/request"


def public_https_url(value: str | None) -> str | None:
    """Accept a public HTTPS hostname only; do not let a lead turn this into an SSRF target."""
    if not value or len(value) > 2_000:
        return None
    try:
        parsed = urlsplit(value.strip())
        host = (parsed.hostname or "").rstrip(".").lower()
        if parsed.scheme.lower() != "https" or not host or parsed.username or parsed.password:
            return None
        if parsed.port not in (None, 443):
            return None
        if host in {"localhost", "metadata.google.internal"} or host.endswith((".localhost", ".local", ".internal")):
            return None
        try:
            ipaddress.ip_address(host)
            return None  # Require a domain name, not an IP literal.
        except ValueError:
            pass
        if "." not in host or any(not label or len(label) > 63 for label in host.split(".")):
            return None
        # The stored/source URL is deliberately query-free to avoid retaining accidental tokens.
        return urlunsplit(("https", host, parsed.path or "/", "", ""))
    except ValueError:
        return None


def _plain_text(source: str) -> str:
    value = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", source)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def _meta(source: str, name: str) -> str | None:
    pattern = re.compile(
        rf"(?is)<meta\b[^>]*(?:name|property)=[\"'](?:og:)?{re.escape(name)}[\"'][^>]*content=[\"']([^\"']*)[\"'][^>]*>"
    )
    match = pattern.search(source)
    return html.unescape(match.group(1)).strip()[:300] if match else None


async def fetch_public_page(hub: IntegrationHub, api_key: str | None, zone: str | None,
                            url: str) -> AdapterResult:
    safe_url = public_https_url(url)
    if not safe_url:
        return hub.blocked("bright_data", "Supplier website must be a public HTTPS domain", API_URL)
    if not api_key or not zone:
        return hub.blocked("bright_data", "Bright Data API key and Web Unlocker zone are required", API_URL)
    host = urlsplit(safe_url).hostname or ""
    try:
        addresses = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError:
        return AdapterResult("bright_data", "UNAVAILABLE", source_url=safe_url,
                             error="Supplier website domain could not be resolved")
    resolved = {entry[4][0] for entry in addresses}
    if not resolved or any(not ipaddress.ip_address(address).is_global for address in resolved):
        return hub.blocked("bright_data", "Supplier website resolves to a non-public address", safe_url)
    result = await hub.fetch(
        "bright_data", API_URL, method="POST", headers={"Authorization": f"Bearer {api_key}"},
        # "json" returns the {status_code, headers, body} envelope parsed below; "raw" would return the page itself.
        # The body stays HTML so the <title>/<meta> extraction below has something to match.
        json_body={"zone": zone, "url": safe_url, "format": "json"},
        timeout=45, retries=1, source_url=safe_url,
    )
    if not result.ok:
        return result
    response = result.data if isinstance(result.data, dict) else {}
    target_status = response.get("status_code")
    body = response.get("body")
    try:
        failed_target = target_status is not None and int(target_status) >= 400
    except (TypeError, ValueError):
        failed_target = True
    if not isinstance(body, str) or not body.strip() or failed_target:
        return AdapterResult("bright_data", "UNAVAILABLE", source_url=safe_url,
                             error=f"Public page returned no usable content (HTTP {target_status or 'unknown'})")
    title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", body)
    title = _plain_text(title_match.group(1))[:200] if title_match else None
    description = _meta(body, "description")
    text = _plain_text(body)[:2_000]
    if len(text) < 40:
        return AdapterResult("bright_data", "UNAVAILABLE", source_url=safe_url,
                             error="Public page loaded but contained too little readable text")
    result.data = {"page_title": title, "description": description, "excerpt": text,
                   "target_status": target_status or 200}
    result.source_url = safe_url
    return result
