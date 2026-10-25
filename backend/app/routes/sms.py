"""Inbound Twilio SMS for supplier quote updates."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qsl
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pymongo.errors import DuplicateKeyError

from ..core import Services, audit, get_services, new_id, now_iso, secret
from ..integrations.openrouter_sms import parse_sms_intent
from ..workflows import apply_quote_change

router = APIRouter(tags=["supplier-sms"])
E164_DIGITS = re.compile(r"^\+?[1-9]\d{7,14}$")
STRICT_PRICE = re.compile(r"^(?:PRICE|UPDATE)\s+(.+?)\s+(?:TO\s+)?\$?([0-9]+(?:\.[0-9]{1,2})?)$", re.I)
CONFIRM = re.compile(r"^CONFIRM\s+(\d{6})$", re.I)


def normalize_phone(value: str) -> str | None:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 10:
        digits = "1" + digits
    phone = "+" + digits
    return phone if E164_DIGITS.fullmatch(phone) else None


def twilio_signature(url: str, params: dict[str, str], token: str) -> str:
    payload = url + "".join(key + params[key] for key in sorted(params))
    import base64

    return base64.b64encode(hmac.new(token.encode(), payload.encode(), hashlib.sha1).digest()).decode()


def twiml(message: str) -> Response:
    xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escape(message)}</Message></Response>'
    return Response(xml, media_type="application/xml")


async def verify_twilio(request: Request, body: bytes, services: Services) -> dict[str, str]:
    token = secret(services.settings.twilio_auth_token)
    if not token or not services.settings.twilio_account_sid:
        raise HTTPException(status_code=503, detail="Twilio webhook is not configured")
    signature = request.headers.get("X-Twilio-Signature", "")
    if not signature:
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/x-www-form-urlencoded":
        raise HTTPException(status_code=415, detail="Expected a Twilio form request")
    params = dict(parse_qsl(body.decode("utf-8"), keep_blank_values=True))
    # Twilio signs the externally visible URL, so deployments must configure their canonical public API URL.
    url = services.settings.public_api_url.rstrip("/") + request.url.path
    if request.url.query:
        url += "?" + request.url.query
    expected = twilio_signature(url, params, token)
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")
    if not params.get("MessageSid") or not params.get("From") or not params.get("To"):
        raise HTTPException(status_code=400, detail="Missing required Twilio message fields")
    if params.get("AccountSid") and not hmac.compare_digest(params["AccountSid"], services.settings.twilio_account_sid):
        raise HTTPException(status_code=403, detail="Message belongs to an unconfigured Twilio account")
    return params


def latest_quote_line(quote: dict, item: str) -> tuple[int, dict] | None:
    normalized = " ".join(item.casefold().split())
    matches = [(index, line) for index, line in enumerate(quote.get("lines", []))
               if " ".join(str(line.get("item", "")).casefold().split()) == normalized]
    return matches[0] if len(matches) == 1 else None


async def supplier_status(services: Services, supplier_id: str) -> str:
    quotes = [q for q in await services.store.find("quotes", supplier_id=supplier_id)
              if q.get("status") == "submitted"]
    if not quotes:
        return "You have no active submitted quotes."
    summaries = []
    for quote in quotes[:3]:
        mission = await services.store.get("missions", quote["mission_id"])
        summaries.append(f"{(mission or {}).get('name', 'mission')}: "
                         f"{len(quote.get('lines', []))} item(s), version {quote.get('version', 1)}")
    return "Active quotes: " + "; ".join(summaries)


async def reply_for_message(services: Services, phone: str, body: str) -> str:
    subscription = await services.store.get("sms_subscriptions", phone)
    command = body.strip()

    if command.upper() == "STOP":
        supplier_id = subscription.get("supplier_id") if subscription else None
        await services.store.upsert("sms_subscriptions", {"id": phone, "phone": phone,
                                     "supplier_id": supplier_id, "active": False, "updated_at": now_iso()})
        return "ReliefMesh SMS updates stopped. Reply START to opt in again."
    if command.upper() == "HELP":
        return "ReliefMesh supplier SMS: STATUS; PRICE <exact item name> <new unit price>; CONFIRM <6-digit code>; STOP to opt out. Text START after your supplier phone is linked to opt in."

    suppliers = [row for row in await services.store.find("suppliers")
                 if normalize_phone(row.get("contact_phone", "")) == phone]
    if len(suppliers) != 1:
        return "This phone is not linked to a unique ReliefMesh supplier profile. Update your profile phone, then text START."
    supplier = suppliers[0]
    if command.upper() == "START":
        await services.store.upsert("sms_subscriptions", {"id": phone, "phone": phone,
                                     "supplier_id": supplier["id"], "active": True, "updated_at": now_iso()})
        return "You are opted in to ReliefMesh supplier SMS. Text HELP for commands."
    if not subscription or not subscription.get("active"):
        return "To use ReliefMesh supplier SMS, reply START to opt in. Reply STOP any time to opt out."

    confirm = CONFIRM.fullmatch(command)
    if confirm:
        code_hash = hashlib.sha256(confirm.group(1).encode()).hexdigest()
        pending = [row for row in await services.store.find("sms_pending_actions", phone=phone, status="pending")
                   if row.get("code_hash") == code_hash and row.get("expires_at", "") > now_iso()]
        if len(pending) != 1:
            return "That confirmation code is invalid or expired. Send the price change again to start a new request."
        action = pending[0]
        quote = await services.store.get("quotes", action["quote_id"])
        mission = await services.store.get("missions", action["mission_id"])
        if not quote or not mission or quote.get("supplier_id") != supplier["id"] or quote.get("version") != action["quote_version"]:
            action.update(status="expired", updated_at=now_iso())
            await services.store.replace("sms_pending_actions", action["id"], action)
            return "The quote changed while this request was pending. Please send the price update again."
        if quote.get("status") != "submitted":
            return "This quote is no longer active, so it cannot be changed by SMS."
        index = action["line_index"]
        if index >= len(quote.get("lines", [])) or quote["lines"][index].get("item") != action["item"]:
            return "The quote line changed; please send the price update again."
        updated_lines = [dict(line) for line in quote["lines"]]
        updated_lines[index]["unit_price"] = action["unit_price"]
        supplier_label = supplier.get("legal_name") or "Supplier"
        quote, job = await apply_quote_change(services, quote, mission, supplier["id"], kind="updated",
                                              summary=f"{supplier_label} revised {action['item']} price via SMS",
                                              updates={"lines": updated_lines})
        await audit("quote.updated.via_sms", supplier["id"], quote["organization_id"], quote["mission_id"],
                    "quote", quote["id"], services, {"job_id": job["id"], "line_item": action["item"]})
        action.update(status="confirmed", updated_at=now_iso())
        await services.store.replace("sms_pending_actions", action["id"], action)
        return f"Quote updated to ${action['unit_price']} per unit. ReliefMesh has queued a recovery replan; coordinator approval is still required."

    if command.upper() == "STATUS":
        return await supplier_status(services, supplier["id"])

    intent = await parse_sms_intent(services, command)
    if intent["intent"] == "status":
        return await supplier_status(services, supplier["id"])
    if intent["intent"] != "price_change":
        match = STRICT_PRICE.fullmatch(command)
        if not match:
            return "I couldn't read that request. Text STATUS or PRICE <exact item name> <new unit price>. Text HELP for examples."
        item, price = match.group(1).strip(), match.group(2)
    else:
        item, price = intent["item"], intent["unit_price"]
    try:
        amount = Decimal(str(price))
        if not amount.is_finite() or amount <= 0 or amount > Decimal("999999999999.99"):
            raise InvalidOperation
        amount_str = f"{amount:.2f}"
    except (InvalidOperation, ValueError):
        return "Please provide a positive unit price, for example: PRICE bottled water 2.50."

    quotes = [q for q in await services.store.find("quotes", supplier_id=supplier["id"], status="submitted")]
    matches = [(quote, latest_quote_line(quote, item)) for quote in quotes]
    matches = [(quote, line) for quote, line in matches if line]
    if len(matches) != 1:
        if len(matches) > 1:
            return "That item appears in multiple active quotes; use the portal so you can select the mission safely."
        return "I couldn't find that exact item in one of your active submitted quotes. Check the item name in the supplier portal."
    quote, line_match = matches[0]
    line_index, line = line_match
    mission = await services.store.get("missions", quote["mission_id"])
    if not mission:
        return "The quote's mission is unavailable. Please contact the coordinator."
    code = f"{secrets.randbelow(1_000_000):06d}"
    action = {"id": new_id(), "phone": phone, "supplier_id": supplier["id"], "quote_id": quote["id"],
              "mission_id": mission["id"], "quote_version": quote.get("version", 1), "line_index": line_index,
              "item": line["item"], "old_unit_price": str(line["unit_price"]), "unit_price": amount_str,
              "code_hash": hashlib.sha256(code.encode()).hexdigest(), "status": "pending",
              "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(), "created_at": now_iso()}
    await services.store.insert("sms_pending_actions", action)
    return f"Confirm {line['item']}: ${line['unit_price']} → ${amount_str} per unit? Reply CONFIRM {code} within 5 minutes. No change is made until confirmed."


@router.post("/v1/webhooks/twilio/sms")
async def receive_twilio_sms(request: Request, services: Services = Depends(get_services)) -> Response:
    body = await request.body()
    params = await verify_twilio(request, body, services)
    sid = params["MessageSid"]
    from_phone = normalize_phone(params["From"])
    to_phone = normalize_phone(params["To"])
    if not from_phone or not to_phone:
        raise HTTPException(status_code=400, detail="Invalid phone number")
    configured_number = normalize_phone(services.settings.twilio_phone_number or "")
    if not configured_number or to_phone != configured_number:
        raise HTTPException(status_code=403, detail="Message was sent to an unconfigured Twilio number")
    async with services.sms_locks[from_phone]:
        existing = await services.store.get("twilio_messages", sid)
        if existing:
            return twiml(existing.get("reply") or "ReliefMesh is processing this message. Please check your portal before retrying.")
        message = {"id": sid, "message_sid": sid, "from": from_phone, "to": to_phone,
                   "body": params.get("Body", "")[:1200], "reply": None, "status": "processing",
                   "created_at": now_iso()}
        try:
            # Reserve the provider SID before applying any quote mutation. The unique Mongo index prevents a
            # duplicate webhook delivered to another API worker from applying the same confirmation twice.
            await services.store.insert("twilio_messages", message)
        except (DuplicateKeyError, ValueError):
            existing = await services.store.get("twilio_messages", sid)
            if existing:
                return twiml(existing.get("reply") or "ReliefMesh is processing this message. Please check your portal before retrying.")
            raise
        try:
            reply = await reply_for_message(services, from_phone, params.get("Body", "")[:1200])
        except Exception:
            # Keep Twilio responses useful without echoing internal exceptions or credentials.
            reply = "ReliefMesh couldn't process that message right now. Please retry or use the supplier portal."
        message.update(reply=reply, status="processed", processed_at=now_iso())
        await services.store.replace("twilio_messages", sid, message)
        return twiml(reply)
