# ReliefMesh Telegram bot

ReliefMesh suppliers can use Telegram as their working interface. There is no phone number or SMS carrier involved. Buyers still create missions, issue RFQs, and approve plans in the buyer portal.

## Create the Telegram bot

In Telegram, open **@BotFather**, send `/newbot`, choose a display name and a unique username, and copy the bot token it returns. Keep the token private. Set the username without the leading `@` as `RELIEFMESH_TELEGRAM_BOT_USERNAME`.

## Configure the backend

Set these environment variables in the backend deployment's secret store:

```dotenv
RELIEFMESH_TELEGRAM_BOT_TOKEN=...
RELIEFMESH_TELEGRAM_WEBHOOK_SECRET=<random secret, 32+ characters>
RELIEFMESH_TELEGRAM_BOT_USERNAME=your_bot_username
RELIEFMESH_PUBLIC_API_URL=https://reliefmesh-api.onrender.com
```

Generate the webhook secret locally with `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`. Do not commit the bot token or webhook secret. The public API must be deployed with the Telegram route before registering the webhook.

After deployment, from the `backend` directory run:

```bash
python scripts/set_telegram_webhook.py
```

The script registers `POST {RELIEFMESH_PUBLIC_API_URL}/v1/webhooks/telegram` with Telegram and uses the webhook secret to authenticate incoming updates.

For a local demo, set `RELIEFMESH_TELEGRAM_POLLING_ENABLED=true` in the ignored `backend/.env` file and run the API from the `backend` directory. The backend will long-poll Telegram directly, so a public tunnel is not required. The bot cannot long-poll while a Telegram webhook is registered; remove the webhook when switching to local polling. Keep polling disabled on hosted deployments; use the webhook setup above there. Stop the local API to stop bot replies.

## Supplier flow without the portal

When a buyer sends an RFQ invitation, the email includes **Accept and respond in Telegram**. The supplier opens that one-time, email-bound invitation link in Telegram, sends their registered legal business name, and replies `ACCEPT` or `DECLINE`. After acceptance, they can stay in Telegram to:

- `/rfqs` and `/accept <code>` to handle additional requests sent to the invited email.
- `/quote [code]` to enter shipping and item prices, quantities, and delivery dates. The bot shows a preview and requires `SUBMIT` before it stores the offer; `CANCEL` discards the draft.
- `STATUS` and `PRICE <exact item> <new unit price>` to view or revise an existing offer. A revision requires `CONFIRM <code>`.
- `/orders`, `ACCEPT <PO number>`, `DECLINE <PO number> [reason]`, `/ship <PO number> <note>`, `/delivered <PO number> <note>`, and `CANNOT-FULFILL <PO number> <note>` for purchase order and fulfillment updates.
- `/help` for the command list and `/stop` to pause bot replies.

Existing portal suppliers can still link with **Supplier** → **Connect Telegram** → **Generate secure link**. This one-time link expires after 10 minutes.

## Data and safety

Messages are accepted only from private Telegram chats. The bot token stays in deployment secrets. RFQ links use the same high-entropy, expiring invitation token sent to the supplier's email. Portal link codes are stored as hashes and expire after 10 minutes. Price confirmation codes expire after five minutes and bind to the quote version that was reviewed. Confirming a change uses the existing quote versioning, invalidation, and recovery-replan workflow; a human coordinator must still approve the resulting plan.

Telegram-originating message text is parsed with fixed commands and is not sent to an external AI model. This follows Telegram's [API Terms of Service](https://core.telegram.org/api/terms), which restrict using Telegram data to develop, enhance, or deploy AI/ML models.
