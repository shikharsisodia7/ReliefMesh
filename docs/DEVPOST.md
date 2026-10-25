# Devpost submission: ReliefMesh

> Production SHA: **TO BE RECONCILED**. Hosted-feature claims are **PENDING MERGE** unless the release
> reconciliation confirms them. This copy is ready to paste after those fields are resolved.

## Project name

ReliefMesh

## Tagline

The procurement continuity engine for emergency relief.

## Inspiration

Emergency procurement plans are written against facts that can change in minutes: a supplier sells out, raises a
price, misses a delivery window, or becomes ineligible. Most tools help make a plan; they do not prove whether that
plan survives the first failure or revoke an approval when its inputs are no longer true.

We built ReliefMesh to make emergency purchasing resilient. It finds the best valid plan from supplier-submitted
quotes, tells a coordinator how that plan can fail, and rebuilds it when the real world changes—without letting an
agent or requester authorize spending.

## What it does

1. A coordinator enters the need, destination, deadline, budget, and disaster context.
2. ReliefMesh discovers public supplier leads, sends RFQs, and accepts supplier-submitted binding quotes.
3. It evaluates public evidence and applies a deterministic eligibility policy.
4. PuLP/CBC solves the constrained procurement problem: coverage, inventory, deadline, budget, and concentration.
5. The Continuity Engine re-runs that same deterministic model under supplier loss, price, delay, and capacity
   shocks. Its output is always labeled **HYPOTHETICAL STRESS TEST**.
6. An authorized human approves the exact plan version. The requester and agent cannot self-approve.
7. A real supplier quote change makes the plan stale, revokes its approval, and queues an automatic replan.
8. A new plan requires a new human approval before purchase orders are issued.

## Why it matters

ReliefMesh treats a procurement plan as a living decision, not a static spreadsheet. In the latest verified recovery
run, V1 was approved, a supplier changed price, V1 became stale, approval was revoked, and V2 was built
automatically. Continuity ran again, a fresh approval was required, and two purchase orders completed. The
tamper-evident audit chain verified, and replaying delivery work created zero duplicates.

Verified run totals: **2 total POs, 2 delivered POs, 32 audit events, 29 / 29 idempotency keys before and after
replay, and zero duplicate Gmail, Slack, Calendar, Drive, PO, or x402 records.**

## How we built it

- **Web:** Next.js, React, TypeScript, Tailwind, TanStack Query, React Hook Form, and Zod.
- **API:** FastAPI, Python, Pydantic, MongoDB Atlas, ReportLab, and durable background jobs.
- **Decision system:** a deterministic policy engine plus PuLP/CBC mixed-integer optimization.
- **Continuity:** snapshot-bound N-1, price, delay, and capacity stress tests plus a constrained resilient
  alternative. Real changes invalidate stale results instead of overwriting history.
- **Evidence and disaster context:** NASA EONET, NASA FIRMS, NWS, OpenFEMA, OFAC, SAM.gov, openFDA, and
  USAspending. Failed providers are surfaced as `CACHED` or `UNAVAILABLE`, never invented as healthy data.
- **Operations:** Gmail, Google Calendar, Google Drive, Slack, and Resend. Deliveries are idempotent and do not
  grant approval authority.
- **Agent and AI:** Fetch.ai / uAgents / Agentverse / ASI:One for operational questions; Gemini for
  supplier-reviewable quote drafting. Claude: **PENDING MERGE**.
- **Payments:** Coinbase x402 with Solana devnet test USDC for machine-paid evidence only; no supplier is paid.
- **Deploy:** Vercel, Render, MongoDB Atlas, and `reliefmesh.us`.

## Challenges we ran into

- We had to separate useful autonomy from financial authority. The system can invalidate, explain, and replan, but
  only a human can approve a plan or commit a purchase order.
- A continuity result is only useful if it is bound to the same quotes, policy, evidence, and plan version that a
  human sees. We added explicit input bindings and stale-state handling instead of presenting a plausible but old
  answer.
- Real integrations need truthful failure behavior. We use provenance, caching, retries, and fail-closed policy
  rather than replacing unavailable data with mock success.

## Accomplishments that we're proud of

- A procurement plan can be stress-tested before an emergency supplier fails.
- A real input change automatically invalidates the old financial authorization.
- The complete recovery loop is auditable: V1 → change → stale → V2 → new approval → POs.
- Replayed operational delivery jobs produce no duplicate notifications, files, orders, or receipts.
- AI assistance stays on the assistive side of a firm human and deterministic boundary.

## What we learned

Trust is a product feature. Showing whether data is live, cached, user-submitted, sandboxed, or hypothetical is as
important as computing a recommendation. We also learned that a resilient plan is not necessarily the cheapest plan,
and a correct answer must include the cost of that resilience.

## What's next

- Reconcile the final deployment SHA and hosted-feature branch before submission.
- Add final redacted production screenshots and a Figma artifact link.
- Continue validating the workflow with emergency-response partners and policy owners.
- Expand supplier participation while preserving the same evidence, approval, and audit boundaries.

## Built with

Next.js, React, FastAPI, Python, MongoDB Atlas, PuLP, CBC, Vercel, Render, Fetch.ai, uAgents, Agentverse, ASI:One,
Gemini, Apify, CRS / TransUnion TruValidate sandbox, OFAC, SAM.gov, openFDA, USAspending, NASA EONET, NASA FIRMS,
NWS, OpenFEMA, Coinbase x402, Solana devnet, Gmail, Google Calendar, Google Drive, Slack, and Resend.

## Live demo

https://reliefmesh.us

## GitHub

https://github.com/shikharsisodia7/calhacks

## Judge guide

https://reliefmesh.us/judge

## Figma

**PENDING** — add the final artifact URL only after it exists.

## Demo video

**PENDING** — add the final YouTube or Vimeo URL.

## Sponsor track notes

| Track / sponsor | Submission note |
| --- | --- |
| Hyphenate | Autonomous procurement recovery with human financial authority. |
| Microsoft | A deployed operational workflow with responsible-AI boundaries. |
| Fetch.ai | Agentverse / ASI:One procurement agent that explains stored results without spending authority. |
| CRS | Sandbox signer identity and fraud verification; label `SANDBOX`. |
| Apify | Public supplier-lead discovery; leads are not quotes or inventory. |
| Gemini | Grounded supplier quote drafting with review before submission. |
| Solana | Devnet settlement; label `DEVNET TEST PAYMENT`. |
| GoDaddy | `reliefmesh.us`. |
| Armadin | Authority boundaries, replay protection, and tamper-evident audit. |
| Coinbase x402 | Machine-paid evidence over x402; eligibility remains conditional. |
| Figma | **PENDING** final artifact. |
| Bright Data | **PENDING MERGE**; do not claim until reconciled and live. |

For submission eligibility, use [the conservative track audit](qa/TRACK_ELIGIBILITY.md), not this summary table.
