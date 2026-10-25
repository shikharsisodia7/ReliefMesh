# Cal Hacks 13.0 track eligibility audit

Audited 2026-10-25 against the **official live prize list** (`hive.hackberkeley.org/api/live/prizes`, 58 categories,
fetched 05:25 UTC) and the sponsor documents it links (Coinbase PDF, Atlassian doc, CRS and Hyphenate text). Evidence
is limited to what was actually observed on production (`https://reliefmesh.us`, API `reliefmesh-api.onrender.com`) or
in provider dashboards. An installed SDK, an env variable, an adapter, a README line or a mock never counts.

**Continuity Engine note:** the N-1 / failure-frontier / resilient-alternative work lives on `feat/continuity-engine`
(+ the guarantee suite on `feat/continuity-engine-verify`) and is **not in production yet**. Rows that depend on it say
so; they become VERIFIED only after it ships and is shown live.

Status legend: ✅ VERIFIED ELIGIBLE · 🟢 IMPLEMENTED — SUBMISSION ACTION NEEDED · 🟡 PARTIAL · 🔴 BLOCKED ·
⚫ NOT ELIGIBLE / FORCED FIT — SKIP

## Final matrix

| Track | Status | Real integration | Live proof | Submission ready | Blocker |
| --- | --- | --- | --- | --- | --- |
| Cal Hacks First/Second/Third Overall | 🟢 | Whole product | reliefmesh.us, real RFQ→PO workflow verified on prod | No | Devpost + demo video (owner) |
| Cal Hacks Most Technically Complex | 🟡 | MILP optimizer, signed audit chain, durable jobs, policy engine; Continuity Engine on branch | Prod workflow + 105 backend tests | No | Continuity Engine not yet deployed; video |
| Cal Hacks Most Creative | 🟡 | Continuity Engine ("this plan can break") | Branch only | No | Continuity Engine not yet deployed |
| Cal Hacks Best People-First | 🟢 | Emergency relief procurement for county OES buyers | Live EONET/NWS/FEMA context on missions | No | Devpost framing + video |
| Cal Hacks Hacker's Choice | 🟢 | Whole product | reliefmesh.us | No | Devpost |
| Hyphenate — Autonomous Systems for Finance | 🟢 | Autonomous procurement with limited authority, audit record, human approval | Disruption → stale → replan → re-approval verified on prod | No | Video must open with "the moment" |
| Microsoft Grand Prize / Customer Impact | 🟢 | Production-minded agent in a high-impact domain (no MS product required) | Prod + Fetch agent | No | Devpost + video |
| Fetch.ai — Best Use of Fetch.ai | 🟢 | uAgents mailbox agent, Agent Chat Protocol, ASI:One | Real ASI:One session created a mission and refused spend | No | 3–5 min video; continuity questions ship with the engine |
| CRS Financial Intelligence Challenge | 🟢 | TruValidate identity check of supplier signers gates allocation | `/status` CRS sandbox proof (P01 verified, P12 flagged) | No | Show live in demo |
| Coinbase — Best Use of x402 (Payment Agents) | 🟡 | Official x402 SDK, HTTP 402 → Solana devnet USDC settlement | Settled devnet tx from prod `/status` | No | Coinbase MCP for Agents not used; verified Coinbase account per member; builder-feedback write-up |
| Apify — Best use of Apify | 🟢 | `compass/crawler-google-places` supplier discovery (leads only) | Prod run `6LFVdn73xb0TMjtrW` | No | Show discovery in demo |
| MLH Best Use of Gemini API | 🟢 | Grounded, schema-constrained quote-draft assistant | Prod + e2e test with real Gemini | No | Free tier ~20 drafts/day; MLH form |
| MLH Best Use of Gen AI | 🟢 | Same Gemini feature | Same | No | MLH form |
| MLH Best Use of Solana | 🟢 | x402 settlement in USDC on Solana devnet | Devnet tx `jbsGqZmk…` (RPC-confirmed) | No | MLH form; label DEVNET |
| MLH Best Use of MongoDB Atlas | 🟢 | Production system of record (M0) | Prod API `storage: mongo` | No | MLH form |
| MLH Best Domain Name from GoDaddy Registry | 🟢 | `reliefmesh.us` via the MLH × GoDaddy Registry cart (code MLHCH2681) | `https://reliefmesh.us` live, Let's Encrypt cert | No | MLH form |
| Armadin — Best Security Hack | 🟡 | Tenant break-in suite, signed audit heads, agent authority limits | Tests + prod | No | Criteria still "Coming soon" |
| Anthropic | ⚫ | Product does not use Claude | — | — | Requires thoughtful use of Claude |
| Atlassian — Agentic Workforce | ⚫ | No Forge/Jira/Confluence app | — | — | Requires a Forge app |
| Bright Data | ⚫ | Not integrated | — | — | Bright Data must be essential |
| Visa — Reimagining Shopping | ⚫ | B2B emergency procurement, not shopping | — | — | Forced fit |
| All other categories (listed below) | ⚫ | Not integrated | — | — | — |

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
- **LIVE EVIDENCE:** Production run: supplier revised its quote in the portal → plan V1 marked STALE, approval
  invalidated → V2 computed with the reason and cost delta shown → independent re-approval → PO emailed and accepted.
- **MISSING REQUIREMENT:** The video and the one-line "seats" statement.
- **IMPLEMENTATION VALUE:** Highest-value track for this product; the Continuity Engine (predicting the break before it
  happens) is exactly "catches what others missed".
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
- **MISSING REQUIREMENT:** The video. Continuity questions ("biggest single point of failure", "survive losing X",
  "cheapest N-1 fix", "what changed V1→V2", "most fragile mission") are implemented and tested in
  `agent/continuity_answers.py` and go live with the engine.
- **RISK:** Low. **ELIGIBLE?** 🟢
- **DEMO ACTION:** In ASI:One ask "Can this plan survive losing <supplier>?" and show the answer is the stored
  deterministic result (labelled HYPOTHETICAL), then ask it to pay and show the refusal.

### CRS Financial Intelligence Challenge
- **PRIZE:** Best Overall $1,000; Best Financial AI Agent $500; Identity/Fraud and Most Unexpected: FDE interviews.
- **EXACT REQUIREMENT:** Meaningful use of the CRS sandbox shown live; judged on how central CRS is (not a bolt-on),
  working live demo, usefulness, creativity. Test identities only.
- **WHAT RELIEFMESH CURRENTLY USES:** TransUnion TruValidate checks of each supplier's authorized signer; a failed or
  incomplete check holds the supplier at NEEDS_REVIEW so it cannot receive an allocation.
- **LIVE EVIDENCE:** `/status` runs P01 (verified) and P12 (flagged 2201/2202/2101) live against the sandbox, labelled
  SANDBOX.
- **MISSING REQUIREMENT:** None technical. Best fit sub-prize: **Identity / Fraud Innovation** (supplier-signer fraud
  in emergency purchasing). Not a fit: Best Financial AI Agent (the agent does not call CRS).
- **RISK:** Low–medium. **ELIGIBLE?** 🟢  **DEMO ACTION:** Show a flagged signer blocking allocation in the plan.

### Coinbase — Best Use of x402 (Payment Agents track)
- **PRIZE:** $500 USDC + recruiter call per eligible member (one winning team per track).
- **EXACT REQUIREMENT:** "Give an agent a way to pay for things… Use the Coinbase MCP for Agents and x402." Submit
  project summary, working example, architecture (components, controls, limitations) and builder feedback. Real money
  not required; label simulated actions. Each member needs a verified Coinbase account (18+, US/Canada resident).
- **WHAT RELIEFMESH CURRENTLY USES:** Official x402 Python SDK; HTTP 402 → signed USDC transfer → x402.org facilitator
  settlement on Solana devnet; per-org daily cap, replay rejection, audited receipts; agent purchases limited to
  privileged senders.
- **LIVE EVIDENCE:** Signed-in users can trigger a devnet payment on `/status`; tx `jbsGqZmk…` settled (buyer 19.98 →
  19.97, treasury 20.02 → 20.03 USDC on devnet RPC).
- **MISSING REQUIREMENT:** Coinbase MCP for Agents is not used; verified Coinbase accounts; architecture + builder
  feedback in the submission.
- **RISK:** Medium–high (track names the MCP). **ELIGIBLE?** 🟡
- **SUBMISSION ACTION:** Each member: create and verify a Coinbase account; submit under Payment Agents with the
  architecture note and builder feedback (blocker: Coinbase Payments MCP does not pay x402 on Base Sepolia).

### Apify — Best use of Apify
- **PRIZE:** $2,000 / $1,000 / $800 / $400 / $400 (Best Actor $400 is separate).
- **EXACT REQUIREMENT:** Use Apify in a meaningful way; project quality judged.
- **WHAT RELIEFMESH CURRENTLY USES:** Supplier discovery through `compass/crawler-google-places`; results stored as
  leads only (never auto-trusted), with actor, run and dataset IDs recorded.
- **LIVE EVIDENCE:** Production run `6LFVdn73xb0TMjtrW` / dataset `pGX4l3tGzAlGYLba9`.
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
