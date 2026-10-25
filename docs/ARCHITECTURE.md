# ReliefMesh architecture

ReliefMesh is a procurement continuity engine for emergency response: it buys from real supplier quotes,
screens suppliers against public records, decides eligibility with deterministic policy, allocates with integer
optimization, stress-tests a persisted plan on counterfactual copies, rebuilds after real supply-chain changes,
and leaves financial authority with a human.

```
                 NASA EONET · NWS · NASA FIRMS · OpenFEMA        (emergency context, read-only)
                                   │
 Coordinator (Next.js) ──REST──▶ FastAPI ◀──REST── ReliefMesh Buyer Agent (Fetch.ai uAgent, ASI:One chat)
 Supplier portal      ──REST──▶   │
                                   ├─ evidence service ── OFAC SDN (Treasury CSV) · SAM.gov · openFDA · USAspending
                                   │                      · CRS sandbox (identity/fraud) · x402 paid dossiers
                                   ├─ policy engine (pure function) ─▶ eligible quotes only
                                   ├─ optimizer (PuLP / CBC MILP)
                                   ├─ Continuity Engine (N-1 + breakpoints + resilient MILP, HYPOTHETICAL only)
                                   ├─ jobs (replan / evidence / discovery) with retries + recovery
                                   ├─ approvals (plan-hash bound, expiring, single-use) → purchase orders
                                   ├─ audit chain (SHA-256 linked events) + notifications
                                   └─ MongoDB (all state)            Apify actor → supplier LEADS only
```

## Layers and where they live

| Concern | Code | Notes |
| --- | --- | --- |
| HTTP API + wiring | `backend/app/main.py`, `backend/app/routes/*` | every Codex-era endpoint preserved |
| Shared services, auth, audit chain | `backend/app/core.py` | user JWTs and org-scoped agent tokens |
| Integration hub | `backend/app/integrations/http.py` | timeout, transient-only retry, per-provider breaker, last-known-good cache labeled `CACHED`, `BLOCKED_EXTERNAL` for missing keys |
| Emergency context | `backend/app/integrations/emergency.py`, `routes/intel.py` | EONET snapshot stored on the mission at creation |
| Supplier evidence | `backend/app/evidence/service.py`, `integrations/{ofac,entity}.py` | append-only typed records with provenance and expiry |
| Policy | `backend/app/policy/engine.py` | PASS / WARN / NEEDS_REVIEW / BLOCK; no LLM, no free-text interpretation |
| Optimization | `backend/app/optimizer.py` | Codex's MILP, now fed only policy-eligible quotes |
| Planning, diff, invalidation | `backend/app/planning.py` | plan hash + policy fingerprint; before/after supplier delta and reasons |
| Continuity Engine | `backend/app/continuity.py`, `routes/continuity.py` | persisted, input-hash-bound N-1/failure-frontier/resilience results; no mutation of supplier data |
| Background jobs | `backend/app/jobs.py`, `backend/app/workflows.py` | coalescing, attempts/backoff, stuck-job recovery |
| Demo tooling (dev/test only) | `backend/app/routes/demo.py` | 404 unless `RELIEFMESH_DEMO_MODE=true`; production refuses to start with it |
| Agent API | `backend/app/routes/agent.py` | scoped tokens; cannot approve, order, or move procurement money |
| x402 payments | `backend/app/payments/x402_exchange.py`, `routes/payments.py` | official Coinbase x402 SDK, Solana devnet |
| Fetch.ai agent | `agent/reliefmesh_agent.py` | Agent Chat Protocol, ASI:One routing, hosted or mailbox |
| Web app | `frontend/src/components/mission/*`, `frontend/src/app/*` | Mission Control theme (open-design) |

## Decision flow for one plan

1. Load mission, all quotes, supplier records, the latest evidence per type, and human review actions.
2. `policy.evaluate()` returns a decision per rule per supplier and quote, a status per quote, the eligible quote
   set, and a SHA-256 fingerprint of (quote versions, statuses).
3. `optimizer.solve()` runs on eligible quotes only. Withheld quotes are listed in `rejected_quotes` with the rule IDs
   and explanations, so "why did Supplier B get zero?" is answered from stored data.
4. The plan stores constraints, allocations, the policy snapshot, a `difference` against the prior version, and a
   `plan_hash` over its material contents.
5. Approval re-evaluates policy. If the fingerprint changed, approval is refused. The approval binds the plan version,
   hash, amount, and spending ceiling, expires (default 4 h), and is consumed by the first PO issuance.

## Continuity Engine

After each feasible plan, a durable `continuity_analysis` job runs off the request path. The analysis has no authority
to alter policy, quotes, plans, approvals, or purchase orders. It records `HYPOTHETICAL` provenance and a SHA-256
input hash over the mission/plan binding, plan hash, quote versions, policy fingerprint, evidence fingerprint,
optimizer-input fingerprint, and active purchase-order commitment fingerprint. It then:

1. Removes each allocated supplier in turn and reruns the same policy-eligible MILP (N-1 survivability).
2. Computes the smallest monotonic per-supplier price, ETA, and proportional-capacity stress that makes the current
   quote snapshot infeasible.
3. Solves a second transparent candidate with a ≤50% supplier concentration guardrail, then publishes its actual N-1
   outcome and incremental cost.

Results are cached by `(mission, plan, input_hash)`, run in a retryable background job, and are marked `STALE` when
the plan is invalidated. The read API repeats the input-hash check, so a race cannot display outdated analysis as
current. If a plan has active purchase orders, their lines and consumed quote capacity are fixed: the analysis scopes
itself to the uncommitted remainder and labels that scope. If no requirement remains uncommitted, it records that no
future procurement can truthfully be reallocated instead of inventing a recovery. The Procurement Digital Twin graph
is composed only from persisted mission, requirements, quotes, plan, approval, purchase-order, emergency, and
continuity records.

## What triggers recovery

Any material change calls `invalidate_for_change(reason)`: plans become `stale`, approvals `invalidated` (reason
recorded), unsent PO drafts `void`, notifications are written, and a coalesced `replan` job is queued. Triggers:
supplier quote revision or withdrawal, a declined PO or cancelled fulfillment (replans keep units already on active POs),
human review decisions that change a supplier's status, and evidence refreshes that change policy inputs.

## Trust boundaries

- **Missing evidence is never a pass.** No OFAC screening, a failed one, or a stale one means NEEDS_REVIEW.
- **Fuzzy sanctions matches go to a human.** Exact name matches BLOCK pending review. Clearances bind to the exact
  evidence ID reviewed, so new evidence requires a fresh review.
- **LLMs have no authority.** The only model in the loop (optional ASI:One routing) picks which API tool the agent
  calls. The API validates everything, and agent tokens cannot approve, order, block suppliers, or clear findings.
- **Agent conversations are isolated.** Each ASI:One sender only reaches missions it created (`X-Agent-Sender`,
  enforced in the API). Credit-spending actions are deny-by-default for agent senders.
- **Production is real data only.** No seeded suppliers, simulated disruptions, or demo organizations: those exist only
  with `RELIEFMESH_DEMO_MODE=true` in local/test deployments, where they carry TEST/SYNTHETIC badges.
- **Audit is tamper-evident, not immutable.** Each event hashes its predecessor. `/audit/verify` recomputes the chain.

## Provenance vocabulary

`LIVE` fetched now from the public source · `CACHED` last-known-good copy with its original retrieval time ·
`SANDBOX` sponsor sandbox or devnet · `USER_SUBMITTED` entered by a supplier · `SYNTHETIC` / `TEST` demo fixtures ·
`BLOCKED_EXTERNAL` credential not configured (never faked) · `UNAVAILABLE` call failed with no cache.
