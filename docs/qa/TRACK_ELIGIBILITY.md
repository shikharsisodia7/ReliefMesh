# Cal Hacks 13.0 track eligibility audit

Audited 2026-10-25 against the **official live prize list** (`hive.hackberkeley.org/api/live/prizes`, 58 categories;
first fetched 05:25 UTC, re-fetched 08:20 UTC with no category added or removed) and the sponsor documents it links
(Coinbase PDF, Atlassian doc, CRS and Hyphenate text). Evidence is limited to what was actually observed on production
(`https://reliefmesh.us`, API `reliefmesh-api.onrender.com`) or in provider dashboards. An installed SDK, an env
variable, an adapter, a README line or a mock never counts. Every one of the 58 categories appears below exactly once,
either in the matrix or in the skip table.

**Final release:** `release/final @ 9bbe49d`, deployed to all three production components (Vercel web, Render API,
Render Fetch agent; Render auto-deploy is off and every deploy is manual).

**Continuity Engine: in production on `9bbe49d`.** Deterministic N-1 supplier-loss analysis, exact price / delay /
capacity failure frontiers, a resilient alternative under a 50% supplier-concentration guardrail with the cost of
resilience, STALE handling the moment any bound input changes, an actual-vs-hypothetical comparison, and Fetch agent
continuity answers. Every result is labeled `HYPOTHETICAL STRESS TEST`; a real supplier revision is labeled
`ACTUAL USER-SUBMITTED CHANGE` and compared with the `PREDICTED COUNTERFACTUAL`.

**Release test state (`9bbe49d`):** backend 145/145 (continuity 38/38, 0 skipped), Ruff clean, Playwright on the
affected flows 5/5, Semgrep 0 findings, secret scan of all commits clean. The frontend and agent are byte-identical to
`ccb6bca`, where the agent continuity answers (9/9), the demo and production-mode agent conversations, frontend unit
tests, TypeScript, ESLint, the production build, the real-Gemini Playwright spec, pip-audit and npm audit all passed.

Status legend: ✅ VERIFIED ELIGIBLE · 🟢 IMPLEMENTED — SUBMISSION ACTION NEEDED · 🟡 PARTIAL · 🔴 BLOCKED ·
⚫ NOT ELIGIBLE / FORCED FIT — SKIP. No row is ✅ yet only because the Devpost submission and the demo video are owner
actions that have not happened; 🟢 means the technology is real and live on production.

## Final matrix

| Track | Status | Real integration | Live proof | Submission ready | Blocker |
| --- | --- | --- | --- | --- | --- |
| Cal Hacks First/Second/Third Overall | 🟢 | Whole product | Full production E2E on mission HENDERSON (see below) | No | Devpost + demo video (owner) |
| Cal Hacks Most Technically Complex | 🟢 | MILP optimizer + Continuity Engine (N-1 MILP re-solves, binary-searched failure frontiers, constrained resilient alternative), hash-chained audit with HMAC-signed heads, durable jobs, deterministic policy | Continuity analysis computed live for Plan V1 and V2 on prod; 145 backend tests | No | Devpost + video |
| Cal Hacks Most Creative | 🟢 | Continuity Engine: proves whether the plan can break, what breaks it, and what resilience costs | Mission → Continuity on prod, labeled HYPOTHETICAL STRESS TEST | No | Devpost + video |
| Cal Hacks Best People-First | 🟢 | Emergency relief procurement for county OES buyers | Live EONET/NWS/FEMA context on missions | No | Devpost framing + video |
| Cal Hacks Hacker's Choice | 🟢 | Whole product | reliefmesh.us | No | Devpost |
| Hyphenate — Autonomous Systems for Finance | 🟢 | Autonomous procurement with limited authority, audit record, human approval, predicted failure before it happens | Real supplier revision → V1 STALE, approval revoked → automatic V2 → fresh independent approval → PO (HENDERSON run) | No | Video must open with "the moment" |
| Microsoft Grand Prize: Built for the Real World | 🟢 | Production-minded agent in a high-impact domain (no MS product required) | Prod + Fetch agent | No | Devpost + video |
| Microsoft Customer Impact Award | 🟢 | Same submission as the Grand Prize | Same | No | Devpost + video |
| Fetch.ai — Best Use of Fetch.ai | 🟢 | uAgents mailbox agent, Agent Chat Protocol, ASI:One; continuity answers from stored deterministic results | Real ASI:One session created a mission and refused spend; agent on `9bbe49d` | No | 3–5 min video |
| CRS Financial Intelligence Challenge | 🟢 | TruValidate identity check of supplier signers gates allocation | `/status` CRS sandbox proof (P01 verified, P12 flagged), labeled SANDBOX | No | Show live in demo |
| Coinbase — Best Use of x402 (Payment Agents) | 🟡 | Official x402 SDK, HTTP 402 → Solana devnet USDC settlement | Settled devnet tx from the HENDERSON mission | No | **Coinbase MCP for Agents is not implemented** (the track names it); verified Coinbase account per member; builder-feedback write-up |
| Apify — Best use of Apify | 🟢 | `compass/crawler-google-places` supplier discovery (leads only) | Newest prod run `UzUWPV9bx3pecTERA` / dataset `QvXc5W61SgngKrC4i` (historical: `6LFVdn73xb0TMjtrW`) | No | Show discovery in demo |
| MLH Best Use of Gemini API | 🟢 | Grounded, schema-constrained quote-draft assistant | Real Gemini draft in the HENDERSON run + e2e test with real Gemini | No | Free tier ~20 drafts/day; MLH form |
| MLH Best Use of Gen AI | 🟢 | Same Gemini feature | Same | No | Not on the Devpost prize list (only on Hive); ask MLH |
| MLH Best Use of Solana | 🟢 | x402 settlement in USDC on Solana devnet | Newest devnet tx `3xYUqjWe…Crddq` (HENDERSON dossier; historical: `jbsGqZmk…`) | No | MLH form; label DEVNET |
| MLH Best Use of MongoDB Atlas | 🟢 | Production system of record (M0) | Prod API `storage: mongo` | No | Not on the Devpost prize list (only on Hive); ask MLH |
| MLH Best Domain Name from GoDaddy Registry | 🟢 | `reliefmesh.us` via the MLH × GoDaddy Registry cart (code MLHCH2681) | `https://reliefmesh.us` live, Let's Encrypt cert | No | MLH form |
| Armadin — Best Security Hack | 🟡 | Tenant break-in suite, signed audit heads, agent authority limits | Tests + prod | No | Criteria still "Coming soon!" in the official list (re-checked 08:20 UTC) |
| Anthropic | ⚫ | Product does not use Claude at runtime | — | — | Requires thoughtful use of Claude |
| Atlassian — Agentic Workforce | ⚫ | No Forge/Jira/Confluence app | — | — | Requires a Forge app |
| Bright Data | ⚫ | Not integrated | — | — | Bright Data must be essential |
| Visa — Reimagining Shopping | ⚫ | B2B emergency procurement, not shopping | — | — | Forced fit |
| All other categories (listed below) | ⚫ | Not integrated | — | — | — |

## Devpost prize list cross-check

Submissions opt into prizes on Devpost (`cal-hacks-13-0.devpost.com`, checked 2026-10-25 08:50 UTC), and its list
differs from the Hive live list in the following ways. The mapping is below; the full submission text, with the exact
Devpost names to tick, is in `docs/DEVPOST.md`.

| Devpost name | Same as (Hive) | Note |
| --- | --- | --- |
| [Anthropic] Claude for Public Benefit | Anthropic | Still ⚫: the product does not use Claude at runtime |
| [Microsoft] Built for the Real World (1st), Customer Impact Award (2nd) | Microsoft Grand Prize + Customer Impact | One Devpost entry for both |
| [CRS] Best Use of CRS API (1st $2,000, 2nd $1,000) | CRS Financial Intelligence Challenge | Devpost lists two cash places |
| [Elastic] Best use of the Elastic Agent Builder on a Serverless Instance | Elastic | ⚫ |
| [Figma] Best Figma Workflow Hack | Figma in the Workflow | ⚫ |
| [SpaceXSI] Make it Legendary with SpaceXSI | SpaceXAI | ⚫ |
| Not on Devpost | MLH Best Use of MongoDB Atlas, MLH Best Use of Gen AI | 🟢 technically, but not selectable on Devpost; ask MLH |
| Not on Devpost | MLH ElevenLabs, Presage, Backboard, DigitalOcean, Auth0, .Tech; AfterQuery; Annapurna Labs | ⚫ either way |

## Viable tracks in detail

### Hyphenate — The Hyphenated Enterprise: Autonomous Systems for Finance
- **PRIZE:** $8,000 / $5,000 / $3,000; expedited interviews for the top 5.
- **EXACT REQUIREMENT:** Judged on: real enough (realistic data, messy problem, proof it works); would you hire it
  (limited access, clean record of its work, knowing when to ask); something new; "the moment" (catches what others
  missed, recovers from something going wrong, defends a decision). Video opens with the moment; live demo (judges may
  run their own scenario); one line on the seats it fills; proof of what is real vs simulated.
- **REQUIRED TECHNOLOGY:** None mandated.
- **WHAT RELIEFMESH CURRENTLY USES:** Autonomous RFQ → evidence → policy → MILP plan → **human** approval → PO; the agent
  can never approve, order or pay; every step lands in a per-mission hash chain with an HMAC-signed head.
- **LIVE EVIDENCE:** Production run on mission HENDERSON (`0f8cd92e`): the Continuity Engine flagged supplier Sisodia
  as the single point of failure on Plan V1 (N-1 0/1) and priced a resilient alternative; the supplier then revised its
  real quote in the portal ($32 → $38) → Plan V1 STALE, its active approval revoked, the V1 analysis STALE → Plan V2
  computed automatically with the reason and cost delta → V2 analysed on `9bbe49d` → fresh independent approval → PO.
- **MISSING REQUIREMENT:** The video and the one-line "seats" statement.
- **IMPLEMENTATION VALUE:** Highest-value track for this product; the Continuity Engine (predicting the break before it
  happens) is exactly "catches what others missed", and it is live in production.
- **ESTIMATED RISK:** Medium (strong field). **ELIGIBLE?** 🟢
- **SUBMISSION ACTION:** Seats: "emergency procurement analyst — sources, screens and re-plans; never approves or pays."
- **DEMO ACTION:** Open on the supplier backing out mid-mission and the plan rebuilding itself; then show the
  LIVE / SANDBOX / DEVNET / HYPOTHETICAL labels as the "what's real" proof.

### Microsoft — Grand Prize: Built for the Real World (and Customer Impact Award)
- **PRIZE:** Surface laptop per member + FDE tech talk + mentorship (Customer Impact: talk + mentorship).
- **EXACT REQUIREMENT:** Production-minded AI agent for a meaningful problem in a high-impact domain; judged on
  customer understanding, measurable usefulness, path to production, responsible design, end-to-end functionality.
- **REQUIRED TECHNOLOGY:** No Microsoft product required (confirmed in the event channel).
- **WHAT RELIEFMESH CURRENTLY USES:** Deployed agent + web app on a real domain, real email, tenant isolation, audit,
  failure-mode handling (every external dependency down is tested).
- **LIVE EVIDENCE:** `https://reliefmesh.us`, `/status` 18/18 live checks, real RFQ delivered with DKIM/SPF/DMARC pass.
- **MISSING REQUIREMENT:** Submission + video. **RISK:** Medium. **ELIGIBLE?** 🟢
- **DEMO ACTION:** Show the responsible-design boundary: the agent drafts and recommends, humans approve.

### Fetch.ai — Best Use of Fetch.ai
- **PRIZE:** $1,500 / $1,000 / $500.
- **EXACT REQUIREMENT (HackPack):** Agentverse registration, Agent Chat Protocol, ASI:One discoverable and directly
  usable, meaningful tools, primary workflow completable in ASI:One, public repo with agent name/address, 3–5 min video.
- **WHAT RELIEFMESH CURRENTLY USES:** Mailbox agent `agent1qwsexvyvdavc0pjys60fgh7mev3d6xccnqfjg9famyqvnxrw4eajsxs243x`,
  ACP manifest, scoped org token with per-conversation isolation.
- **LIVE EVIDENCE:** Real ASI:One session: agent listed live EONET wildfires, created a mission on the production API,
  reported truthful empty states, refused "approve the plan and pay the suppliers".
- **CONTINUITY ANSWERS (live on `9bbe49d`):** "biggest single point of failure", "survive losing X", "cheapest N-1
  fix", "what changed V1→V2", "most fragile mission", answered from the stored deterministic analysis
  (`agent/continuity_answers.py`, 9 tests); with no current analysis the agent says so instead of guessing.
- **MISSING REQUIREMENT:** The video.
- **RISK:** Low. **ELIGIBLE?** 🟢
- **DEMO ACTION:** In ASI:One ask "Can this plan survive losing <supplier>?" and show the answer is the stored
  deterministic result (labelled HYPOTHETICAL), then ask it to pay and show the refusal.

### CRS Financial Intelligence Challenge
- **PRIZE:** Best Overall $1,000; Best Financial AI Agent $500; Identity/Fraud and Most Unexpected: FDE interviews.
- **EXACT REQUIREMENT:** Meaningful use of the CRS sandbox shown live; judged on how central CRS is (not a bolt-on),
  working live demo, usefulness, creativity. Test identities only.
- **WHAT RELIEFMESH CURRENTLY USES:** TransUnion TruValidate checks of a supplier's authorized signer; a failed or
  incomplete check holds the supplier at NEEDS_REVIEW so it cannot receive an allocation. Only signers bound to a
  CRS-published test persona are ever sent to CRS, so a real supplier's personal data never leaves ReliefMesh and CRS
  is never presented as verification of a real supplier's identity.
- **LIVE EVIDENCE:** `/status` runs P01 (verified) and P12 (flagged 2201/2202/2101) live against the sandbox, labelled
  SANDBOX. Production has no persona-bound suppliers (real data only), so the signer-gating of an allocation is shown
  in a local demo deployment (`RELIEFMESH_DEMO_MODE=true`, every supplier labeled TEST) and in the backend tests.
- **MISSING REQUIREMENT:** None technical. Best fit sub-prize: **Identity / Fraud Innovation** (supplier-signer fraud
  in emergency purchasing). Not a fit: Best Financial AI Agent (the agent does not call CRS).
- **RISK:** Low–medium. **ELIGIBLE?** 🟢  **DEMO ACTION:** Show the `/status` sandbox proof live, then a flagged TEST
  signer blocking allocation on a local demo deployment, labeled as such.

### Coinbase — Best Use of x402 (Payment Agents track)
- **PRIZE:** $500 USDC + recruiter call per eligible member (one winning team per track).
- **EXACT REQUIREMENT:** "Give an agent a way to pay for things… Use the Coinbase MCP for Agents and x402." Submit
  project summary, working example, architecture (components, controls, limitations) and builder feedback. Real money
  not required; label simulated actions. Each member needs a verified Coinbase account (18+, US/Canada resident).
- **WHAT RELIEFMESH CURRENTLY USES:** Official x402 Python SDK; HTTP 402 → signed USDC transfer → x402.org facilitator
  settlement on Solana devnet; per-org daily cap, replay rejection, audited receipts; agent purchases limited to
  privileged senders.
- **LIVE EVIDENCE:** Newest: the HENDERSON mission bought a supplier dossier over HTTP 402 for 0.01 devnet USDC, tx
  `3xYUqjWeXs8Yz8RgHzNm9CohygZDJJfRw2s2FWapfuJJ1jh9gRnFJNDsx5AJt1UPsvR3vhzYuskyTjZt3t5Crddq` (DEVNET TEST PAYMENT;
  the replan did not create a second payment). Historical: tx `jbsGqZmk…` from `/status` (buyer 19.98 → 19.97,
  treasury 20.02 → 20.03 USDC on devnet RPC). Signed-in users can trigger a devnet payment on `/status`.
- **MISSING REQUIREMENT:** **Coinbase MCP for Agents is not implemented.** x402 and the Solana devnet settlement are
  real and working, but the track asks for the MCP *and* x402, so ReliefMesh is PARTIAL and must not claim full
  Coinbase eligibility. Also: verified Coinbase accounts; architecture + builder feedback in the submission.
- **RISK:** Medium–high (track names the MCP). **ELIGIBLE?** 🟡 PARTIAL
- **SUBMISSION ACTION:** Each member: create and verify a Coinbase account; submit under Payment Agents with the
  architecture note and builder feedback (blocker: Coinbase Payments MCP does not pay x402 on Base Sepolia).

### Apify — Best use of Apify
- **PRIZE:** $2,000 / $1,000 / $800 / $400 / $400 (Best Actor $400 is separate).
- **EXACT REQUIREMENT:** Use Apify in a meaningful way; project quality judged.
- **WHAT RELIEFMESH CURRENTLY USES:** Supplier discovery through `compass/crawler-google-places`; results stored as
  leads only (never auto-trusted), with actor, run and dataset IDs recorded.
- **LIVE EVIDENCE:** Newest production run `UzUWPV9bx3pecTERA` / dataset `QvXc5W61SgngKrC4i`. Historical: run
  `6LFVdn73xb0TMjtrW` / dataset `pGX4l3tGzAlGYLba9`. Results are `LEADS` only: never inventory, price, a quote, a
  delivery commitment, willingness to sell, or a verified supplier.
- **MISSING REQUIREMENT:** None for Best use. **Best Actor: ⚫** (no custom Actor built). **RISK:** Medium. **ELIGIBLE?** 🟢

### MLH category prizes (Gemini, Gen AI, Solana, MongoDB Atlas, GoDaddy Registry)
- **Gemini / Gen AI 🟢:** grounded quote-draft assistant; every extracted value is cited from the pasted text,
  schema-constrained, never stored or submitted without supplier review; prompt injection in the quote is ignored
  (tested). Free tier allows ~20 drafts/day; a 429 surfaces as `GEMINI_RATE_LIMITED`.
- **Solana 🟢:** USDC settlement on Solana devnet through x402, labelled DEVNET TEST PAYMENT.
- **MongoDB Atlas 🟢:** production system of record.
- **GoDaddy Registry 🟢:** `reliefmesh.us` registered through the MLH × GoDaddy Registry cart and serving the app over
  HTTPS (www and the vercel.app fallbacks redirect to it).
- **.Tech Domain ⚫:** no .tech domain is used.
- **SUBMISSION ACTION:** opt into each MLH category on Devpost.

### Armadin — Best Security Hack
- **EXACT REQUIREMENT:** "Coming soon" in the official list (unpublished). **ELIGIBLE?** 🟡
- **WHAT RELIEFMESH HAS:** OpenAPI-enumerated cross-tenant break-in tests, HMAC-signed audit chain heads, agent tokens
  that can never reach approval/PO/payment endpoints, SSRF-safe outbound calls, prompt-injection tests.

## Production E2E evidence (release `9bbe49d`, 2026-10-25)

Mission **San Diego HENDERSON fire shelter blankets** (`0f8cd92e-dc3c-456e-9f5f-c85807d510c5`), organization
ReliefMesh Ops, run on `https://reliefmesh.us` with real production accounts (requester, independent approver and two
supplier accounts are the owner's plus-addressed test accounts, each supplier self-labeled "ReliefMesh production test
supplier"). Nothing was seeded; demo mode is off (`/v1/config`: `app_env=production`, `demo_mode=false`).

| Step | Evidence |
| --- | --- |
| Live disaster | Mission linked to a live NASA EONET wildfire event (`LIVE`) |
| Discovery | Apify run `UzUWPV9bx3pecTERA` / dataset `QvXc5W61SgngKrC4i`, stored as `lead` only |
| RFQs | Two RFQs sent through the organization's connected Gmail (messages `1a171c35ca9b90e6`, `1a171c396efc3378`) |
| Quotes | Supplier 1: 100 @ $32.00 (drafted by real Gemini, reviewed and submitted by the supplier); supplier 2: 80 @ $35.00; both `USER_SUBMITTED` |
| Evidence | OFAC, SAM.gov (one result honestly `CACHED`), USAspending, openFDA per supplier; x402 dossier bought for 0.01 devnet USDC |
| Plan V1 | $3,200.00 (Sisodia 100 @ $32), hash `d128518737f83b5d` |
| Continuity V1 | N-1 0/1, single point of failure Sisodia; price +243.76%, delay 30 h, capacity 81 units; resilient alternative $3,350 (+$150); `HYPOTHETICAL STRESS TEST` (computed before the `9bbe49d` fix) |
| Approval V1 | Independent approver (not the requester), `INDEPENDENT_APPROVER`, bound to the V1 hash, 4 h expiry |
| Real change | Supplier 1 revised its quote in the portal: $32.00 → $38.00 (+18.75%), quantity and dates unchanged, quote v1 → v2 |
| Invalidation | Plan V1 `stale`, V1 approval `invalidated` (revoked), V1 continuity `STALE`, replan queued and run automatically |
| Plan V2 | $3,560.00 (+$360): Harbor 0 → 80 @ $35, Sisodia 100 → 20 @ $38; trigger `supplier_disruption` |
| Continuity V2 (`9bbe49d`) | Current plan N-1 **1/2** (losing Harbor recoverable at $3,800; losing Sisodia infeasible); resilient alternative $3,650 (+$90), N-1 **1/2**; price +189.48%, delay 30 h, capacity 81 units; budget headroom $1,440; largest share 80% |
| Actual vs hypothetical | UI shows the V1 `PREDICTED COUNTERFACTUAL` (breaks at +243.76%) beside the `ACTUAL USER-SUBMITTED CHANGE` (+18.75% → V2 $3,560): "Outcome matches the earlier stress test" |
| Approval V2 | Fresh independent approval bound to V2 hash `5b596f88dcfeb7d7`; V1 approval stays invalidated |
| POs | `RM-20261025-2C35B2F1` (Sisodia, $760) and `RM-20261025-7ECE37BB` (Harbor, $2,800) = $3,560; sent after explicit confirmation through Gmail (messages `1a1722a79b0392ac`, `1a1722abc3801302`) with the PO PDF attached |
| Fulfillment | `RM-20261025-2C35B2F1`: sent → supplier_accepted → in_fulfillment → completed. `RM-20261025-7ECE37BB`: sent, awaiting supplier 2 |
| Audit | 29 events, hash chain verifies (tamper-evident; HMAC-signed head) |
| Gmail | Approval requests (V1, V2), disruption alerts, POs: real Gmail API sends from the connected account, not the Resend fallback |
| Calendar | 3 events on the "ReliefMesh Operations" calendar (deadline, approval window, supplier ETA), each updated in place; no duplicates |
| Drive | `Plan-V1.pdf`, `Plan-V2.pdf`, both PO PDFs, `Audit-Export.json` (updated in place) in the mission folder |
| Slack | 7 informational posts (approval required, disruption, V2 rebuilt, 2 × PO issued, 2 × fulfillment); no approval action exists in Slack |
| Replay | Two replays of every application event and every SENT delivery: 25 deliveries / 25 keys before and after both; 0 new Gmail, Slack, Calendar or Drive objects; POs 2 → 2; x402 payments 1 → 1 |

## Verified integrations that are not separate prize tracks

These are real, live parts of the product (judges see them; they strengthen the core and Hyphenate/Microsoft
submissions) but no Cal Hacks prize is specific to them.

| Integration | Live evidence | Truth boundary |
| --- | --- | --- |
| SAM.gov entity registration | `/status` probe returns a real registration (3M COMPANY, UEI W5ZFEL43MUZ3, Active until 2027-01-12); supplier evidence uses the same API | Registration only, not inventory or capacity; personal key ≈ 10 requests/day, cached a day per name |
| Gmail | Organization-connected Gmail sends RFQs, approval requests and POs; token refresh OK on `/status` | Per-organization OAuth; Resend (`procurement@reliefmesh.us`) is the fallback sender |
| Google Calendar | Deadline, approval window and supplier ETA events, updated in place on replans | Per-organization OAuth |
| Google Drive | Mission folder with plan PDFs, PO PDF and audit export | Per-organization OAuth |
| Slack | Informational alerts (approval needed, disruption, replan, PO, delivered); never approvals | Per-organization OAuth |
| Resend | RFQs from `procurement@reliefmesh.us` with DKIM, SPF and DMARC passing in Gmail | Sending-only key restricted to reliefmesh.us |

## Judge-visible evidence paths

| Integration | Where a judge sees it | Truth boundary |
| --- | --- | --- |
| Continuity Engine | Mission → Continuity: N-1 result, single point of failure, breakpoints, cost of resilience, actual vs earlier stress test | `HYPOTHETICAL STRESS TEST`; never mutates quotes, plans, approvals or POs; STALE when inputs change |
| Judge guide | `/judge`: the eleven-step loop checked against a real mission's stored records | Read-only; nothing pre-seeded |
| Fetch.ai | ASI:One → `reliefmesh-buyer-agent` → "which supplier is the biggest single point of failure?" | Explains stored deterministic results; cannot approve, order or pay |
| Apify | Supplier discovery → run and dataset IDs → leads | Public leads only, never inventory or quote evidence |
| CRS | Supplier evidence → signer check; `/status` sandbox proof | `SANDBOX`, CRS test identities only |
| Coinbase x402 / Solana | `/status` → run a devnet payment → explorer link | `DEVNET TEST PAYMENT`; no supplier is paid |
| Gemini | Supplier RFQ → paste quote → grounded draft → supplier reviews and submits | AI drafts only; the supplier owns every value |
| Security | Mission audit tab + `/audit/verify` | Tamper-evident hash chain, not immutable |

## Not eligible / forced fit (skip)

| Track | Reason |
| --- | --- |
| Best Planet-First Hack | People-first, not planet-first |
| Best Hardware Hack | No hardware |
| Best Beginner Hack | Beginner eligibility not established; organizer must confirm |
| Best Solo Hack | Devpost requires 2–4 team members, so a team project cannot enter |
| Anthropic | Requires thoughtful use of Claude in the product; ReliefMesh uses Gemini |
| Atlassian — Agentic Workforce (agents / security for agents) | Requires a Forge app on Jira/Confluence |
| Bright Data | Bright Data must be essential to the core experience |
| Visa — Reimagining Shopping | Consumer shopping; ReliefMesh is B2B emergency procurement |
| Meta — Bringing People Closer Together | Human-connection focus |
| Capital One Nessie | No Nessie workflow |
| Factory Droid SDK | Droid must do runtime work in the product |
| Creao AI (×3) | Requires a CREAO agent doing core work |
| Cartesia | Voice must be core |
| Bitdeer AI Model Studio | Not used |
| Figma in the Workflow | No Figma artifacts |
| Moss | Voice / personal agent / social examples; not used |
| SpaceXAI / MLH SpaceXSI A-Team | Cursor/Grok raffle; not used |
| Convex | Backend must be built on Convex |
| Elastic (Devpost: Agent Builder on Serverless) / AfterQuery / Annapurna Labs | No runtime integration; optional settings are not use |
| Mana.space | Requires building with Mana |
| Spacetime | Backend must be SpacetimeDB |
| Notability | Requires Notability notes of the build process |
| MLH ElevenLabs, Presage, Backboard, Vultr, DigitalOcean, Snowflake, Auth0, Tiger Data | Not used |
| MLH Commit Fellowship | Not a technology track: owner may opt in and complete MLH's supplemental form |
| Apify — Best Actor | Requires a published custom Actor; only an existing public actor is used |

## Submission actions (owner)

1. Devpost: opt into Hyphenate, Microsoft (Grand + Customer Impact), Fetch.ai, CRS (Identity/Fraud), Apify, the MLH
   categories above, and Coinbase Payment Agents only after verifying Coinbase accounts.
2. Demo video (3–5 min): open with the disruption-and-recovery moment (Hyphenate), show the Fetch agent in ASI:One,
   the CRS sandbox check, the x402 devnet payment, and the data-truth labels.
3. Do not claim any track marked 🟡 or ⚫ as eligible in the submission.
