"""Register the Telegram bot webhook using backend environment settings."""

from __future__ import annotations

import asyncio

import httpx

from app.core import secret
from app.settings import get_settings


async def main() -> None:
    settings = get_settings()
    bot_token = secret(settings.telegram_bot_token)
    webhook_secret = secret(settings.telegram_webhook_secret)
    if not bot_token or not webhook_secret:
        raise SystemExit("Set RELIEFMESH_TELEGRAM_BOT_TOKEN and RELIEFMESH_TELEGRAM_WEBHOOK_SECRET first.")
    webhook_url = f"{settings.public_api_url.rstrip('/')}/v1/webhooks/telegram"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{bot_token}/setWebhook",
                json={"url": webhook_url, "secret_token": webhook_secret,
                      "allowed_updates": ["message", "edited_message"]},
            )
            response.raise_for_status()
            payload = response.json()
            if not payload.get("ok"):
                raise ValueError("Telegram rejected the webhook configuration")
    except (httpx.HTTPError, ValueError, TypeError):
        raise SystemExit("Telegram webhook registration failed. Check bot token and public API URL.") from None
    print(f"Telegram webhook registered: {webhook_url}")


if __name__ == "__main__":
    asyncio.run(main())
