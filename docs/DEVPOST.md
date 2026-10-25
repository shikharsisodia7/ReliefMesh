# Devpost submission: ReliefMesh (final)

Every claim below was verified on production (`https://reliefmesh.us`, release `9bbe49d`) on 2026-10-25. Fields
marked **OWNER** need information only the team has; nothing has been invented for them.

## Basics

- **Project name:** ReliefMesh
- **Tagline:** Emergency procurement that proves whether its plan can break, and rebuilds the plan when reality changes.
- **Elevator pitch:** ReliefMesh buys emergency relief supplies from real supplier quotes for disaster response.
  Before anyone signs off, its Continuity Engine stress-tests the exact plan against losing each supplier, price
  shocks, delays and capacity cuts, names the single point of failure, and prices a resilient alternative. When a
  supplier really changes its quote, the plan goes stale, the approval is revoked, and a new plan is computed for a
  fresh human approval.
- **Live app:** https://reliefmesh.us · **Judge guide:** https://reliefmesh.us/judge ·
  **Live integration status:** https://reliefmesh.us/status
- **Code:** https://github.com/shikharsisodia7/calhacks (default branch `release/final`)
- **Fetch.ai agent:** `reliefmesh-buyer-agent` ·
  `agent1qwsexvyvdavc0pjys60fgh7mev3d6xccnqfjg9famyqvnxrw4eajsxs243x`
- **OWNER:** team name, table number, teammates on Devpost, demo video URL (YouTube/Vimeo, unlisted is fine),
  gallery image.

## Inspiration

When a disaster is declared, a relief organization has to buy blankets, tarps and hygiene kits within hours, often
from suppliers it has never used, under a fixed budget and federal documentation rules. The plan that gets approved
is the cheapest one on paper, and nobody checks whether it survives the first supplier who sells out or raises a
price. By the time that happens, the approval still points at a plan that no longer exists.

We wanted two things: a plan that says up front how it can break, and an approval that dies the moment the facts
under it change.

**OWNER (optional):** add one or two sentences of your own experience if you have one. Do not invent one.

## What it does

1. **A mission from a live disaster.** The coordinator links the mission to an open NASA EONET event and sees NWS
   alerts, NASA FIRMS fire detections and OpenFEMA declarations for that location.
2. **Real suppliers, real quotes.** Apify finds public supplier leads (leads only, never trusted as inventory).
   Suppliers get an RFQ email with a single-use link, sign up, and submit their own binding quote. Gemini can draft
   the quote from pasted text; every value is cited from that text and the supplier reviews it before submitting.
3. **Evidence and deterministic policy.** Every supplier is screened against the Treasury OFAC SDN list, SAM.gov
   registration, USAspending awards and openFDA enforcement reports. A rule engine (no LLM) decides PASS / WARN /
   NEEDS_REVIEW / BLOCK, and missing evidence is never a pass.
4. **Optimization.** A mixed-integer program (PuLP/CBC) picks the cheapest plan that covers every unit within budget,
   inventory, deadline and concentration limits.
5. **Continuity Engine.** For that exact plan, ReliefMesh removes each allocated supplier in turn and re-solves (N-1),
   binary-searches the exact price, delay and capacity shock that breaks the plan, and computes a resilient
   alternative with no supplier above 50% of the order, along with what that resilience costs. Every result is
   labeled **HYPOTHETICAL STRESS TEST** and never changes a quote, plan, approval or order.
6. **Independent human approval.** An approver who is not the requester approves the exact plan version. The
   approval is bound to the plan hash, expires and works once.
7. **Autonomous recovery.** When a supplier revises or withdraws its quote, the plan goes STALE, the approval is
   revoked, the old stress test goes STALE, and a background job builds the next plan version. The UI shows the old
   plan beside the new one with the reason, cost delta and supplier changes, and compares the earlier
   **PREDICTED COUNTERFACTUAL** with the **ACTUAL USER-SUBMITTED CHANGE**.
8. **Purchase orders and fulfillment.** POs are generated idempotently, sent only after explicit confirmation, with a
   PDF, and then accepted, shipped and delivered by the supplier.
9. **Tamper-evident audit.** Every step lands in a per-mission SHA-256 hash chain with an HMAC-signed head, which
   the app verifies.
10. **Agents, safely.** The Fetch.ai agent runs the buyer workflow from ASI:One and answers continuity questions from
    the stored analysis. Its token is rejected on approval and purchase-order endpoints, and it may buy paid evidence
    only from an allow-listed conversation; production allows none. Premium evidence can be bought
    machine-to-machine over HTTP 402 (Coinbase x402) and settled in test USDC on Solana devnet.

## The production run judges can inspect

Mission "San Diego HENDERSON fire shelter blankets" on `reliefmesh.us`, with real accounts and nothing seeded:

- Two suppliers quoted 100 blankets at $32 and 80 at $35. **Plan V1 cost $3,200**, all from one supplier.
- The Continuity Engine flagged that supplier as the **single point of failure** (N-1 0/1) and showed the plan
  breaks at a +243.76% price rise, a 30 h delay or an 81-unit capacity cut. It priced a resilient alternative at
  $3,350 (+$150).
- An independent approver approved V1. The supplier then **really raised its price** in the supplier portal
  ($32 → $38). V1 went stale, its approval was revoked, and **Plan V2 ($3,560, +$360)** was rebuilt automatically,
  splitting the order 80/20.
- The V2 stress test shows that losing the larger supplier is recoverable and losing the smaller one is not (N-1 1/2).
  The earlier prediction and the actual change are shown side by side: "Outcome matches the earlier stress test".
- A fresh approval issued two POs ($760 + $2,800) through the organization's Gmail with PDFs. The first supplier
  accepted, shipped and delivered its order.
- The audit chain verifies (29 events). Replaying every application event and delivery job twice created zero
  duplicate emails, Slack posts, Calendar events or Drive files, and the PO and payment counts did not change.

## How we built it

- **Backend:** Python, FastAPI, Pydantic v2, MongoDB Atlas, PuLP + COIN-OR CBC, an httpx integration hub (timeouts,
  retries, caching, LIVE / CACHED / UNAVAILABLE provenance), ReportLab PDFs, durable background jobs.
- **Continuity Engine:** the same MILP re-run on deep copies of the saved quote snapshot, with binary-searched
  breakpoints and an input hash that binds each analysis to the exact plan, quote versions, policy and evidence.
- **Frontend:** Next.js, TypeScript, Tailwind, TanStack Query, React Hook Form + Zod.
- **Agent:** Fetch.ai uAgents with the Agent Chat Protocol, mailbox on Agentverse, usable in ASI:One.
- **Operations integrations:** each organization connects its own Gmail, Google Calendar, Google Drive and Slack.
  Deliveries are idempotent and never block procurement. Resend sends from `procurement@reliefmesh.us` for
  organizations without Gmail.
- **Deploy:** Vercel (web), Render (API and agent, manual deploys), MongoDB Atlas, domain `reliefmesh.us`.
- **Testing:** 145 backend tests (38 continuity guarantees), agent tests, Vitest, Playwright end to end, Semgrep and a
  secret scan of the full history.
- **Tooling:** built with Claude Code and Codex as coding agents.

## What is real, sandbox and hypothetical

| Data | Label |
| --- | --- |
| Disasters (EONET, NWS, FIRMS, OpenFEMA) and screening (OFAC, SAM.gov, USAspending, openFDA) | `LIVE`, or truthful `CACHED` / `UNAVAILABLE` |
| Suppliers, quotes and quote changes | `USER_SUBMITTED` by real supplier accounts |
| Apify results | Public leads only |
| CRS identity checks | `SANDBOX`, CRS test identities only |
| x402 / Solana payments | `DEVNET TEST PAYMENT`; no real money, no supplier is paid |
| Continuity results | `HYPOTHETICAL STRESS TEST` |

## Challenges we ran into

- **Our own production test caught an engine bug.** The resilient alternative showed 0/2 survivable supplier losses
  when the correct answer was 1/2, because its scenarios were judged under stricter rules than the current plan's.
  We fixed it, added a regression test, redeployed, and re-ran the same production mission to confirm 1/2.
- **Time zones in AI-drafted quotes.** A delivery time with no zone was being shifted to UTC; it now keeps the
  supplier's wall-clock time, with tests on both sides.
- **Real data only.** We refused to seed production with demo suppliers, so every production proof had to be a real
  two-party run with separate requester, approver and supplier accounts.
- **Exactly-once notifications.** Retries and replans could have sent duplicate emails or Slack posts, so every
  delivery carries an idempotency key and Calendar events update in place.
- **Deploy discipline.** An early auto-deploy pushed unreviewed code to production. We rolled back and switched to
  manual deploys of a single tested release commit.

## Accomplishments that we're proud of

- The plan tells you how it breaks before it breaks, and the prediction is checked against what actually happened.
- A real supplier change on production revoked an approval and rebuilt the plan with no human trigger.
- Every number on screen comes from a stored record or a live provider, with its provenance shown.

## What we learned

- In finance workflows the approval is the product: it has to point at one immutable plan, expire, and die when
  inputs change.
- Being honest about data (LIVE vs CACHED vs SANDBOX vs HYPOTHETICAL) is a feature judges and users can check.
- LLMs belong at the edges (drafting, explaining); eligibility, allocation and approval stay deterministic and human.

## What's next

- SAM.gov exclusions (2 CFR 180) and more regulated-goods checks.
- Multi-supplier failure scenarios (N-2) and delay or risk terms in the objective.
- Spending thresholds with multi-approver chains and ERP export.
- A pilot with a county emergency office or a regional relief NGO.

## Built with

`python` `fastapi` `pydantic` `pulp` `coin-or-cbc` `mongodb-atlas` `next.js` `typescript` `tailwindcss`
`tanstack-query` `zod` `reportlab` `playwright` `pytest` `vitest` `fetch.ai` `uagents` `asi-one` `apify` `gemini`
`coinbase-x402` `solana` `crs-credit-api` `gmail-api` `google-calendar-api` `google-drive-api` `slack-api` `resend`
`nasa-eonet` `nws` `nasa-firms` `openfema` `ofac` `sam-gov` `usaspending` `openfda` `vercel` `render`

## Prize tracks

Opt into (real and live, see `docs/qa/TRACK_ELIGIBILITY.md`):
- Cal Hacks Overall, Most Technically Complex, Most Creative, Best People-First, Hacker's Choice;
- Hyphenate: Autonomous Systems for Finance;
- Microsoft Grand Prize: Built for the Real World, and Microsoft Customer Impact Award;
- Best Use of Fetch.ai;
- CRS Financial Intelligence Challenge (Identity / Fraud Innovation);
- Best use of Apify;
- MLH: Best Use of Gemini API, Best Use of Gen AI, Best Use of Solana, Best Use of MongoDB Atlas, Best Domain Name
  from GoDaddy Registry.

Do **not** claim:
- **Coinbase x402** as fully eligible. The track asks for the Coinbase MCP for Agents, which ReliefMesh does not use.
  Enter it only as an honest partial, after each member has a verified Coinbase account.
- **Armadin** until its criteria are published.
- **Any category marked SKIP** in the audit.

## Track-specific fields

- **Hyphenate, "seats it fills":** ReliefMesh fills the emergency buyer and purchasing-clerk seats: it sources,
  screens, stress-tests and re-plans, and it never approves or pays.
- **Hyphenate, "the moment":** a real supplier raises its price after approval; the approval dies, the plan rebuilds
  itself, and the earlier stress test is checked against what actually happened.
- **Fetch.ai:** agent name and address above; Agentverse profile
  https://agentverse.ai/agents/details/agent1qwsexvyvdavc0pjys60fgh7mev3d6xccnqfjg9famyqvnxrw4eajsxs243x/profile.
  **OWNER:** ASI:One shared-chat URL and the 3–5 minute agent video; register the team in the ASI:One Submission
  agent with the Devpost URL.
- **Apify:** actor `compass/crawler-google-places` (https://apify.com/compass/crawler-google-places); production run
  `UzUWPV9bx3pecTERA`, dataset `QvXc5W61SgngKrC4i`.
- **CRS:** live sandbox proof at https://reliefmesh.us/status (test identity P01 verified, P12 flagged).
- **MLH GoDaddy Registry:** `reliefmesh.us`.
