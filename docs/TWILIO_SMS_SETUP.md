# ReliefMesh supplier SMS setup

ReliefMesh accepts inbound supplier messages through Twilio and replies in the same webhook response. The OpenRouter model is an optional parser for natural language; the webhook also accepts deterministic `PRICE` commands.

## Configure secrets

Set these values in the backend deployment's secret manager (or in `backend/.env` for local development). Never commit the values:

```dotenv
RELIEFMESH_TWILIO_ACCOUNT_SID=AC...
RELIEFMESH_TWILIO_AUTH_TOKEN=...
RELIEFMESH_TWILIO_PHONE_NUMBER=+1...
RELIEFMESH_PUBLIC_API_URL=https://your-public-api.example
RELIEFMESH_OPENROUTER_API_KEY=...
RELIEFMESH_OPENROUTER_MODEL=openrouter/free
RELIEFMESH_OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

`RELIEFMESH_PUBLIC_API_URL` must be the externally visible API origin used to reach the FastAPI service. Twilio signature verification depends on it matching the configured webhook URL exactly. Do not put a trailing slash in the origin.

`RELIEFMESH_TWILIO_AUTH_TOKEN` is the account Auth Token from **Account details & security**. An API key's client secret is a different credential and cannot validate Twilio's `X-Twilio-Signature`. If an API key secret has been shared in a screenshot or chat, revoke it in Twilio and create a replacement before using the account.

## Point Twilio at ReliefMesh

In the Twilio Console, open the phone number's **Messaging Configuration** and set **A message comes in** to:

```text
POST https://your-public-api.example/v1/webhooks/twilio/sms
```

Save the number configuration and deploy/restart the backend with the secrets above. The webhook verifies `X-Twilio-Signature` before processing a message.

## Link and opt in the supplier

The supplier must have the same E.164 phone number saved in their ReliefMesh supplier profile (`/v1/supplier/profile`, `contact_phone`). Then the supplier sends `START` to the Twilio number. ReliefMesh only replies to an inbound message, and honors `STOP` to opt out.

## Commands

- `HELP` lists supported commands.
- `STATUS` returns the sender's active submitted quote count, mission labels, and versions.
- `PRICE <exact item name> <new unit price>` starts a quote edit. Example: `PRICE bottled water 2.50`.
- `CONFIRM <6-digit code>` applies the proposed edit for five minutes after it was requested.
- `STOP` opts out; `START` opts back in.

After confirmation ReliefMesh records the quote version, invalidates dependent approval, and queues a recovery replan using the existing quote-change workflow. SMS cannot approve a plan, create an order, authorize spending, or alter another supplier's quote. If the OpenRouter key is missing or its free route is unavailable, strict `PRICE` and command messages continue to work; free model availability and limits are controlled by OpenRouter.

## Live demo prerequisites

Twilio credentials, a configured Twilio SMS number, a public HTTPS API deployment, and a supplier profile linked to a demo phone are required for a live phone demo. Twilio trial accounts may restrict recipients and display trial messaging; check the current limits in the Twilio Console for the account before the demo.
