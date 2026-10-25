# Operations integrations (Gmail, Google Calendar, Google Drive, Slack)

> **Historical channel-verification detail.** The run counts below document an earlier integration exercise; they are
> not the final presentation totals. Use [FINAL_STATUS.md](FINAL_STATUS.md) for the latest reconciled recovery proof
> (2 delivered POs, 32 audit events, 29 / 29 idempotency keys after replay, and zero duplicates). Production SHA:
> **a1fc478**.

ReliefMesh stays the system of record. These integrations carry procurement events into the tools an
emergency-management team already uses; none of them can approve, order, or pay.

## Verification status

| Integration | Status | Evidence |
|---|---|---|
| Gmail (`gmail.send`) | **Verified with real calls** | RFQ, Plan V1 approval request, disruption alert, Plan V2 approval request, and PO email (PDF attached) delivered through the organization's own Gmail; message ids recorded per send |
| Google Calendar (`calendar.app.created`) | **Verified with real calls** | Delivery deadline, approval window (V1 → stale → V2 → approved on one event id), supplier ETA, deadline change (event moved in place), cancellation (event removed) |
| Google Drive (`drive.file`) | **Verified with real calls** | `ReliefMesh/Missions/<mission>/` with `Plan-V1.pdf`, `Plan-V2.pdf`, PO PDF, `Audit-Export.json`; one file per artifact |
| Slack (`chat:write`, `chat:write.public`, `incoming-webhook`) | **Verified with real calls** | Installed through ReliefMesh's own OAuth flow into a dedicated single-member workspace; approval, disruption (old approval post struck through as STALE), Plan V2, PO issued and fulfillment posts delivered to `#relief-operations`; revoked-token failure recorded as FAILED/BLOCKED and recovered by retry |

### Production run (2026-10-24, https://reliefmesh.us)

All four were connected from the production Integrations page (production OAuth callbacks, tokens encrypted in
Atlas) and exercised by one real mission: Mendocino COOLEY wildfire (NASA EONET), RFQ by Gmail, a supplier quote
through the supplier portal, Plan V1 approved by an independent approver, the supplier's real price change
($32 → $38) making V1 stale and revoking its approval, Plan V2 rebuilt automatically and approved, PO with PDF
by Gmail, supplier acceptance and delivery.

- Gmail: RFQ, approval request V1, disruption alerts (coordinator + approver), Plan V2 approval request, PO with
  `RM-…pdf` attached.
- Calendar: exactly three events: deadline, one approval event updated in place (V1 → STALE → approved V2), and
  the supplier ETA updated to Delivered.
- Slack `#relief-operations`: approval V1 (rewritten as STALE), disruption, Plan V2 (+$600), PO issued, Delivered.
- Drive: mission folder with `Plan-V1.pdf`, `Plan-V2.pdf`, PO PDF and `Audit-Export.json`, one file each.
- Idempotency (production database, production code): replaying 9 application events created 0 deliveries
  (21 → 21); re-attempting all 21 SENT deliveries sent nothing twice; the calendar replay updated the same event.
- Controlled failure: a revoked Google token makes the Gmail check FAILED and `/status` BLOCKED while the API stays
  healthy (procurement email falls back to Resend); restore + retry → SENT and LIVE. Same for a revoked Slack token.

## How it works

- The procurement core emits application events (`mission_created`, `mission_updated`, `mission_cancelled`,
  `approval_required`, `plan_replanned`, `supplier_disrupted`, `plan_approved`, `purchase_order_sent`,
  `purchase_order_accepted`, `fulfillment_updated`) from small hooks; `backend/app/operations/` turns each into
  per-channel deliveries.
- RFQ and purchase-order emails go through the core's own send step (`record_email` → routed `EmailGateway`):
  the organization's connected Gmail first, Resend as fallback. A PO is marked sent only after the provider
  returns a message id.
- Each connection is per organization and made by an organization admin on `/settings/integrations`.

## Idempotency

A delivery's id is a hash of `event | mission | subject | version | channel | target`, so a retried endpoint or
a duplicated event cannot send a second email, Slack post, or Drive file. Calendar events use deterministic ids
per mission slot (`deadline`, `approval`, `eta:<po>`): an update replaces the one event, and an older update can
never overwrite a newer one (per-slot sequence). `backend/scripts/ops_idempotency_check.py` re-verifies this
against the real providers.

## Failure behavior

- Provider errors never propagate into procurement; the mission, RFQ, plan, approval, and PO still succeed.
- 429/5xx/network errors → `RETRYING` with exponential backoff (default 4 attempts), then `FAILED`.
- Revoked or expired authorization (`invalid_grant`, Slack `token_revoked`/`invalid_auth`) → `FAILED`
  immediately, the connection shows `BLOCKED` / `NEEDS_REAUTH`, and an admin can retry after reconnecting.
- Missing connection → `NOT_CONFIGURED`. `RELIEFMESH_EMAIL_MODE=disabled|test` → `DISABLED` / `TEST` (stored, never sent).
- States shown in the UI and on `/status` come from real provider calls: `LIVE` only after a call succeeded.

## OAuth requirements

- Google: one OAuth web client with redirect `{RELIEFMESH_PUBLIC_API_URL}/v1/integrations/google/callback`
  (PKCE, `access_type=offline`). Scopes are minimal: `gmail.send`, `calendar.app.created`, `drive.file`, `openid`,
  `email`. Capabilities follow the scopes Google actually granted. While the consent screen is in **Testing**,
  only listed test users can connect and refresh tokens expire after 7 days (reconnect from the settings page).
- Slack: an app with redirect `{RELIEFMESH_PUBLIC_API_URL}/v1/integrations/slack/callback` (HTTPS), or an admin
  can paste a bot token + channel or an incoming-webhook URL (validated to `https://hooks.slack.com/services/`,
  redirects disabled). ReliefMesh posts one real test message before saving.
- Tokens are Fernet-encrypted at rest (`RELIEFMESH_INTEGRATION_ENCRYPTION_KEY`); OAuth state is single-use and
  expires after 15 minutes.

## Production environment variables (names only)

`RELIEFMESH_EMAIL_MODE`, `RELIEFMESH_EMAIL_ALLOWED_RECIPIENTS` (optional), `RELIEFMESH_GOOGLE_OAUTH_CLIENT_ID`,
`RELIEFMESH_GOOGLE_OAUTH_CLIENT_SECRET`, `RELIEFMESH_GOOGLE_OAUTH_REDIRECT_URI` (optional),
`RELIEFMESH_SLACK_CLIENT_ID`, `RELIEFMESH_SLACK_CLIENT_SECRET`, `RELIEFMESH_SLACK_REDIRECT_URI` (optional),
`RELIEFMESH_INTEGRATION_ENCRYPTION_KEY`.

## Mission lifecycle hooks

`PATCH /v1/missions/{id}/deadline` (stales current plans, replans, moves the calendar deadline) and
`POST /v1/missions/{id}/cancel` (stales plans without replanning, removes future calendar events, keeps ETA
events of purchase orders already issued because those are supplier commitments).
