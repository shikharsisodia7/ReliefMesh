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
| SAM.gov | **NOT_CONFIGURED** (needs a SAM.gov account API key; never substituted) |
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

## Known limits

- RFQ emails are delivered (Resend "Delivered"), but inbox placement can suffer until ReliefMesh sends from its own
  domain with DMARC and matching link domain. The switch is env + DNS only: see [EMAIL_DOMAIN.md](EMAIL_DOMAIN.md).
- SAM.gov stays NOT_CONFIGURED without a SAM.gov API key.
- ASI:One chat from the owner's account needs the ASI:One onboarding completed; the agent itself is verified through
  Agentverse's chat-protocol test runner (live EONET answers, refusal of demo actions).
