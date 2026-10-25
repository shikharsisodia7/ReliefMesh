from __future__ import annotations

import asyncio
from urllib.parse import urlencode

import pytest

from app.routes import sms


def signed_sms(app, *, sid: str, body: str) -> tuple[str, dict[str, str]]:
    settings = app.state.services.settings
    settings.twilio_account_sid = "AC-test-account"
    settings.twilio_auth_token = "test-twilio-auth-token"
    settings.twilio_phone_number = "+15550001111"
    settings.public_api_url = "http://test"
    params = {
        "AccountSid": "AC-test-account",
        "MessageSid": sid,
        "From": "+15550002222",
        "To": "+15550001111",
        "Body": body,
    }
    signature = sms.twilio_signature("http://test/v1/webhooks/twilio/sms", params,
                                     "test-twilio-auth-token")
    return urlencode(params), {"X-Twilio-Signature": signature,
                               "Content-Type": "application/x-www-form-urlencoded"}


@pytest.mark.anyio
async def test_duplicate_twilio_delivery_is_processed_once(app_and_client, monkeypatch) -> None:
    app, client = app_and_client
    calls = 0

    async def handle_message(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.02)
        return "ReliefMesh test reply"

    monkeypatch.setattr(sms, "reply_for_message", handle_message)
    payload, headers = signed_sms(app, sid="SM-idempotent-test", body="HELP")

    responses = await asyncio.gather(*(
        client.post("/v1/webhooks/twilio/sms", content=payload, headers=headers) for _ in range(2)
    ))

    assert [response.status_code for response in responses] == [200, 200]
    assert responses[0].text == responses[1].text
    assert calls == 1
    rows = await app.state.services.store.find("twilio_messages", message_sid="SM-idempotent-test")
    assert len(rows) == 1
    assert rows[0]["status"] == "processed"
    assert rows[0]["reply"] == "ReliefMesh test reply"


@pytest.mark.anyio
async def test_twilio_rejects_invalid_signature(app_and_client) -> None:
    app, client = app_and_client
    payload, headers = signed_sms(app, sid="SM-invalid-signature", body="HELP")
    headers["X-Twilio-Signature"] = "invalid"

    response = await client.post("/v1/webhooks/twilio/sms", content=payload, headers=headers)

    assert response.status_code == 403
    assert await app.state.services.store.find("twilio_messages", message_sid="SM-invalid-signature") == []
