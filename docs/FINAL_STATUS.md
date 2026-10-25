# ReliefMesh final status (2026-10-24)

Live: web https://reliefmesh-calhacks.vercel.app · API https://reliefmesh-api.onrender.com ·
status https://reliefmesh-calhacks.vercel.app/status · Fetch.ai agent
`agent1qwsexvyvdavc0pjys60fgh7mev3d6xccnqfjg9famyqvnxrw4eajsxs243x`.

## Production data-integrity audit

Checked against the production MongoDB and the live site after the final deploy.

| Check | Result |
| --- | --- |
| Fake suppliers in production | **0** (0 supplier records) |
| Fake quotes in production | **0** (0 quotes) |
| Synthetic emergency data in production | **0** (EONET/NWS/FIRMS/FEMA are fetched live; fixtures exist only in `backend/tests`) |
| Silent mock API fallbacks | **0** (a failed call returns `UNAVAILABLE`, or `CACHED` real data with its original timestamp) |
| Demo buttons visible in production | **0** (no Seed / Disrupt / demo-org controls; demo endpoints return 404; production refuses to start with `RELIEFMESH_DEMO_MODE=true`) |
| Real RFQ email | **VERIFIED**: Resend, sender "ReliefMesh Procurement" on a temporarily verified domain (env `RELIEFMESH_EMAIL_FROM`), delivered events recorded with message IDs |
| SAM.gov | **LIVE** (owner's SAM.gov public API key; registration-only evidence; the status probe runs at most every 12 h and lookups are cached a day because a personal key allows ~10 requests/day) |
| CRS | **SANDBOX labeled**: only CRS-published test identities are sent; not real-world verification |
| Solana / x402 | **DEVNET / TEST PAYMENT labeled**: proves machine-to-machine payment; no supplier is paid |
| Apify | **LIVE** (authenticated; discovery runs return leads only) |
| OFAC | **LIVE** (39,663 SDN/ALT names) |
| openFDA | **LIVE** |
| USAspending | **LIVE** |
| Gemini (quote-draft assistant) | **LIVE** free tier; drafts are grounded in the pasted text and never stored or submitted |

## Real workflow verified on production

Fresh coordinator → organization → independent approver (email invite) → mission linked to a live EONET event (starts
with 0 suppliers / 0 quotes / 0 plans) → two RFQs emailed through Resend (delivered) → suppliers accepted via the
emailed links and submitted `USER_SUBMITTED` quotes → live evidence → Plan v1 $2,070 → requester's self-approval
refused, independent approval → supplier raised its price **in the supplier portal** → Plan v1 stale, approval
invalidated, autonomous Plan v2 $2,240 (+$170, reason shown) → v2 approved → PO emailed → supplier accepted and
shipped → 22-event audit chain verified. The verification accounts and data were then moved to a separate archive
database, so production holds no test records.

Found and fixed during verification: the supplier portal's "Save revision" never submitted (Base UI buttons default to
`type="button"`), and the mission email log omitted PO emails.

## Later hardening (same day)

- Codex QA findings fixed: REL-003 (agent plan read skipped conversation isolation) and REL-004 (replayable RFQ
  acceptance); their strict-xfail regressions now pass. Pending org invites no longer leak to non-admins.
- Status page: live CRS sandbox proof on CRS-published test identities (P01 verified, P12 flagged, labeled SANDBOX);
  read-only Resend key check; forced refreshes are floored and locked so the public page cannot amplify upstream calls;
  no account usernames shown.
- Keepalive cron verified in production runtime logs (API and Fetch agent warm every 10 minutes).
- Sender branded "ReliefMesh Procurement"; the sending domain lives only in deployment env (see EMAIL_DOMAIN.md).
- Tests: 105 backend, 4 Playwright E2E, deployed QA smoke check; secret-value scan clean across all branches.
- Judge-triggerable x402 proof on `/status`: a signed-in user runs a real HTTP 402 payment from the server's devnet
  test wallet (once per 10 minutes, 10 a day, audited, replayed settlements rejected). First production run settled
  [`jbsGqZmk…`](https://explorer.solana.com/tx/jbsGqZmkgwVUrm9w4CLTwVVWRMVdrPvYc2sZvs99z5x3rCqLt6K2rWJiSHdAuWiMxpjCqZa9iSgSW7jofLophfv?cluster=devnet)
  (0.01 devnet USDC buyer → treasury, confirmed on devnet RPC).
- SAM.gov connected with the owner's key; the status page shows the live registration the probe returned.
- Mission operations panel: notifications for channels an organization never connected (Gmail, Calendar, Drive,
  Slack) collapse into one "not connected" line instead of drowning out real sends; they stay retryable.

## Known limits

- RFQ emails are delivered (Resend "Delivered"), but inbox placement can suffer until ReliefMesh sends from its own
  domain with DMARC and matching link domain. The switch is env + DNS only: see [EMAIL_DOMAIN.md](EMAIL_DOMAIN.md).
- The SAM.gov key is a personal non-federal key: about 10 requests a day, and it expires about 2027-01-20 (renew it
  under SAM.gov Workspace → Profile → Account Details). Past the quota, new lookups show `UNAVAILABLE` and the
  supplier gets a WARN, never a pass.
- The Gemini quote assistant runs on the free tier: about 20 drafts a day, reset at midnight Pacific. When the limit
  is hit, suppliers see `GEMINI_RATE_LIMITED` and fill the form manually, and `/status` shows Gemini as degraded
  until a draft succeeds again.
- Gmail, Google Calendar, Google Drive and Slack show NOT_CONFIGURED in production until Google Cloud and Slack OAuth
  app credentials are configured.
