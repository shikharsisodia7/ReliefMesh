# Hosted deployment

ReliefMesh is a web client plus a FastAPI service. People use the hosted web URL from their own computers; they do not need to clone the repository or run a local server.

## Vercel frontend

- Set the project root directory to `frontend` so Vercel finds `package.json` and `vercel.ts`.
- Set `NEXT_PUBLIC_API_BASE_URL` to the public API origin, for example `https://reliefmesh-api.onrender.com` (no trailing slash). This is a public URL, not a secret; Next.js embeds it in the built frontend.
- Attach the frontend domain in Vercel and redeploy after changing the API URL or domain.
- The optional `/api/keepalive` cron is configured for every 10 minutes. Vercel Hobby only allows daily cron execution, so this schedule requires a plan that supports frequent cron jobs. If using Hobby, remove/relax the cron and accept Render cold starts, or run the API on an always-on plan.
- If using the cron, set `CRON_SECRET` in Vercel's environment settings. It must match the `Authorization: Bearer ...` header Vercel sends.

## Render API

Deploy from the repository's `render.yaml` Blueprint. Keep production settings as `RELIEFMESH_APP_ENV=production`, `RELIEFMESH_STORAGE_MODE=mongo`, and `RELIEFMESH_DEMO_MODE=false`. Set the Blueprint's prompted values:

- `RELIEFMESH_MONGODB_URI`: persistent MongoDB Atlas connection string.
- `RELIEFMESH_FRONTEND_ORIGIN`: the exact public frontend origin, such as `https://app.example.com`.
- `RELIEFMESH_CORS_ORIGINS`: JSON array of allowed browser origins, such as `["https://app.example.com"]` (include the Vercel hostname too if it is used).
- `RELIEFMESH_PUBLIC_API_URL`: externally reachable HTTPS API origin used in Telegram, Twilio, and OAuth callbacks.

Render generates `RELIEFMESH_JWT_SECRET`. Add optional provider credentials only in Render's environment settings, never in source files. Telegram long polling is explicitly disabled in the hosted manifest.

## Telegram supplier bot

Telegram's local polling mode is only for development. For hosting, set `RELIEFMESH_TELEGRAM_BOT_TOKEN`, `RELIEFMESH_TELEGRAM_BOT_USERNAME`, and a random `RELIEFMESH_TELEGRAM_WEBHOOK_SECRET` in Render. Leave `RELIEFMESH_TELEGRAM_POLLING_ENABLED=false`, deploy the API, then from `backend/` run `python scripts/set_telegram_webhook.py` with those settings available in the shell or local ignored `.env`. The script registers the public `https://.../v1/webhooks/telegram` URL with Telegram. Keep the bot token and webhook secret out of GitHub.

For a free Render web service, the API can sleep after 15 minutes of inactivity and the next request may take about a minute to wake it. That affects browser and Telegram response time. Use an always-on API plan for predictable response times.

## Local development

`backend/.env` and `frontend/.env.local` are ignored by Git. Localhost defaults in the code are development fallbacks; hosted deployments must use the public environment values above. The repository's `.gitignore` excludes backend/frontend environment files and `.clodex/state.sqlite3`.
