# ReliefMesh Devpost submission kit

## Title

ReliefMesh — Procurement Continuity Engine

## Tagline

Know whether an emergency purchasing plan survives disruption before it fails.

## One-sentence pitch

ReliefMesh turns real supplier quotes into a deterministic purchasing plan, mathematically stress-tests that plan
against supplier loss, price shocks, delays, and capacity reductions, and automatically rebuilds it after a real
supplier change—while human approvers retain all financial authority.

## Problem and solution

An emergency coordinator can select a low-cost plan and still learn too late that the supplier covering most of a
critical item has increased its price, slipped delivery, or withdrawn. Normal procurement tools help choose a plan;
they do not answer whether it survives reality.

ReliefMesh is a procurement continuity engine. It uses real user-submitted supplier quotes, public evidence, and a
deterministic policy engine to construct an exact-coverage MILP plan. For every feasible plan, it runs counterfactual
optimization over a pinned snapshot to show:

- N-1 supplier survivability and the exact recovery allocation;
- minimum price, delay, and proportional-capacity shocks that make the plan infeasible;
- a transparent cost-versus-resilience option with a 50% supplier-concentration guardrail; and
- a Procurement Digital Twin that traces mission → requirements → suppliers/quotes → plan → approval → PO.

If a real supplier revises a quote, withdraws, declines, or fails fulfillment, ReliefMesh marks the plan stale,
invalidates the approval, voids unsent drafts, and queues a new plan. It never silently carries approval forward.

## Technical architecture

- FastAPI + MongoDB persistence; Next.js client; PuLP/CBC mixed-integer optimization.
- Deterministic PASS/WARN/NEEDS_REVIEW/BLOCK policy; free-text and LLM output never decide eligibility.
- Durable jobs with retries, recovery, and mission-level replan coalescing.
- Continuity input binding: mission ID, plan ID/version/hash, quote versions, policy/evidence/optimizer fingerprints,
  timestamp, and cache key.
- Multi-tenant authorization, per-agent conversation isolation, hash-chained tamper-evident audit, idempotent PO
  creation, approval hash binding, segregation of duties, and stale approval invalidation.

## What is live, sandbox, and hypothetical

| Kind | Disclosure |
| --- | --- |
| `LIVE` / `CACHED` | Public emergency and evidence providers, with source and retrieval time. |
| `USER_SUBMITTED` | Real supplier accounts and quote terms in production. A new production mission has zero suppliers and quotes. |
| `SANDBOX` | CRS test personas only; no real supplier identity is represented as verified. |
| `DEVNET TEST PAYMENT` | Coinbase x402/Solana test settlement for an evidence dossier; never supplier payment or real procurement funds. |
| `HYPOTHETICAL STRESS TEST` | Continuity scenarios use copies of persisted quote snapshots; they never mutate real data or claim a failure occurred. |

## What uses AI—and what does not

AI may provide the Gemini quote-draft assistant or route an ASI:One agent to safe API tools. It may extract,
summarize, or explain deterministic results. It does **not** change supplier eligibility, optimizer constraints,
approve a plan, issue a PO, move money, or alter a continuity result.

## Sponsor use (only enter rows with current proof)

- Fetch.ai: Agentverse/ASI:One buyer agent asks the production API and explains stored continuity analysis; its token
  cannot approve, order, pay, block, or cross conversation boundaries.
- Apify: Google Places supplier discovery produces leads with run/dataset IDs; leads are never shown as inventory.
- Gemini: Grounded supplier quote pre-fill, reviewed before submission.
- CRS: Clearly labeled sandbox capability proof with sponsor test personas.
- Coinbase x402 + Solana: HTTP 402 evidence unlock with a devnet receipt, not supplier payment.

See [the current evidence matrix](qa/TRACK_ELIGIBILITY.md) before entering any sponsor category.

## Three-minute demo

1. **0:00–0:20:** “We need emergency blankets by tomorrow. A normal system tells us the cheapest plan; ReliefMesh
   tells us whether it survives tomorrow.” Show LIVE emergency context and USER_SUBMITTED quotes.
2. **0:20–0:50:** Show Plan V1 and deterministic policy. Explain that the requester cannot self-approve.
3. **0:50–1:30:** Open Continuity. Point to a CRITICAL supplier lane, its N-1 outcome, failure frontier, and the
   incremental cost of the constrained resilient alternative. State “HYPOTHETICAL STRESS TEST.”
4. **1:30–2:10:** As a supplier, make a real USER_SUBMITTED quote revision/withdrawal. Show Plan V1 stale and
   approval revoked—not an animation.
5. **2:10–2:40:** Show automatic Plan V2, cost/supplier delta, and fresh independent approval required.
6. **2:40–3:00:** Show audit verification and one sponsor proof path (Fetch, Apify, CRS SANDBOX, or x402 DEVNET).

## Submission checklist

- [ ] public GitHub repository URL
- [ ] production URL and dated status/health recording
- [ ] project image
- [ ] 3-minute video/live recording
- [ ] selected sponsor track evidence path
- [ ] explicit live/sandbox/hypothetical disclosure
- [ ] final `TRACK_ELIGIBILITY.md` review
