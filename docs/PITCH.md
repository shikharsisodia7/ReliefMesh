# ReliefMesh three-minute pitch

> Production SHA: **TO BE RECONCILED**. Do not add hosted-feature claims until their merge and deployment are
> confirmed.

## 0:00–0:20 — The problem

Emergency procurement plans fail when suppliers change. A supplier sells out, changes its price, misses a deadline,
or becomes ineligible—but the approval still points at the old plan. Most systems help create that plan. ReliefMesh
keeps it working when the facts change.

## 0:20–0:45 — The plan

A coordinator tells ReliefMesh what people need, where it must go, when it must arrive, and the budget. Suppliers
submit their own quotes. ReliefMesh collects public evidence, applies deterministic eligibility rules, and uses a
math optimizer to find the best valid purchasing plan.

## 0:45–1:20 — The Continuity Engine

Before reality breaks the plan, ReliefMesh stress-tests it:

- **N-1:** What if we lose each allocated supplier?
- **Failure frontier:** What price increase, delay, or capacity reduction breaks the plan?
- **Resilient alternative:** What does a lower-concentration plan cost?

This is deterministic and labeled **HYPOTHETICAL STRESS TEST**. It does not edit a quote or pretend that a
counterfactual is a real supplier change.

## 1:20–2:05 — The moment that matters

In the verified recovery story, a supplier changed price after V1 had been approved. ReliefMesh immediately marked
V1 stale, revoked the old approval, rebuilt V2, and reran Continuity. The next plan could not move forward until a
human approved that exact new version.

That produces an auditable chain:

```text
V1 approved → supplier change → V1 stale → approval revoked → V2 → fresh approval → purchase orders
```

## 2:05–2:30 — Human authority

The requester cannot self-approve. The Fetch.ai agent can ask operational questions and explain stored results, but
it cannot approve, issue a purchase order, or pay. Eligibility is a deterministic policy decision, and every
financial commitment remains human-authorized.

## 2:30–3:00 — Proof

The latest verified run completed two purchase orders, both delivered. Its 32-event tamper-evident audit chain
verified. Replaying 29 delivery jobs preserved 29 unique idempotency keys and created zero duplicate Gmail, Slack,
Calendar, Drive, PO, or x402 records.

ReliefMesh uses real operational pieces—supplier accounts, RFQs, public disaster and evidence data, Gmail,
Fetch.ai, and Solana devnet x402—while clearly labeling what is live, sandboxed, user-submitted, and hypothetical.

**ReliefMesh finds the optimized way to get relief to people—and keeps that plan alive when the real world changes.**

## Demonstration cues

1. Open a mission and point to the need, deadline, budget, and disaster context.
2. Show a supplier quote as `USER_SUBMITTED` and an evidence / policy decision.
3. Open Continuity and show N-1, a breakpoint, and the resilient alternative.
4. Show V1 beside V2: stale state and revoked approval are the key moment.
5. Show the new approval, purchase orders, and the audit verification.
6. If time permits, show Fetch.ai / ASI:One and state its authority limits.
