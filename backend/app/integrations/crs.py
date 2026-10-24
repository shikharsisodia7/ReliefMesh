"""CRS Credit API sandbox integration (implemented once sandbox credentials are available)."""

from __future__ import annotations

from typing import Any, Awaitable, Callable


def crs_checker(services: Any) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]] | None:
    if not services.settings.crs_api_key:
        return None
    return None
