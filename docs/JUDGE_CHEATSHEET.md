# ReliefMesh judge cheat sheet

> Release / production SHA: **a1fc478** (web and API).

## What makes this different from ChatGPT?

ReliefMesh is not a chat answer about purchasing. It stores supplier-submitted quotes, applies deterministic policy,
solves a constrained procurement model, binds approvals to a version and hash, and automatically invalidates a plan
when material facts change. Chat can help explain; it does not authorize or decide procurement.

## What is AI?

Gemini can draft quote fields from supplier-pasted text, subject to supplier review. Fetch.ai provides an agent
interface for operational questions. Claude writes cited explanations of a recovery plan for a human to review.

## What is deterministic?

Supplier eligibility policy, PuLP/CBC optimization, Continuity N-1 and breakpoint testing, plan invalidation,
approval validation, purchase-order creation, idempotency, and audit verification are deterministic.

## Are suppliers fake?

Production suppliers and quotes are `USER_SUBMITTED`. Apify provides public leads only; leads are not inventory,
quotes, delivery commitments, or verified suppliers. Test fixtures are labeled and belong only in local/demo modes.

## Is the disaster data real?

NASA EONET, NASA FIRMS, NWS, and OpenFEMA are queried as real sources. The UI distinguishes `LIVE`, `CACHED`, and
`UNAVAILABLE`; it does not invent a successful result when a provider is down.

## Does real money move?

No supplier is paid through the demo payment path. x402 / Solana activity is **DEVNET TEST PAYMENT** using test USDC
for machine-paid evidence.

## What happens when a supplier fails?

The current plan becomes stale, its approval is revoked, unsent drafts are voided as appropriate, and the system
queues a replan. The replacement plan needs a fresh human approval.

## Can the requester approve?

No. The requester cannot self-approve the plan they requested. Approval is tied to the exact plan version, hash, and
current policy state.

## Can the agent pay?

No. The Fetch.ai agent cannot approve, issue purchase orders, alter policy, or pay. It can only use its scoped,
validated operational interface.

## Why MongoDB?

MongoDB Atlas stores organization-scoped operational records: missions, supplier quotes, evidence, plans,
approvals, purchase orders, delivery work, and audit events. Those records provide the immutable inputs for a
reproducible analysis snapshot; the audit chain itself is tamper-evident, not immutable.

## Why Solana / x402?

x402 allows a machine to pay for a small evidence request over HTTP. Solana devnet supplies the test settlement rail.
The result is an auditable **DEVNET TEST PAYMENT**, not a supplier payment or a claim of real-world settlement.

## Why CRS?

CRS / TransUnion TruValidate is used as `SANDBOX` signer identity and fraud evidence with CRS-published test
identities. It is not a real-world supplier identity assertion.

## Why Apify?

Apify discovers public supplier leads. ReliefMesh deliberately treats those results as leads—never as trusted price,
inventory, capacity, or supplier verification.

## How is it secure?

The system separates roles, scopes organizations, binds approvals to exact plan state, makes operational delivery
idempotent, validates OAuth and invitation flows, restricts outbound webhook destinations, and keeps LLM text from
granting authority. The audit chain is hash-linked and verifiable.

## What happens when APIs fail?

The integration layer retries transient errors and can serve a timestamped last-known-good result as `CACHED`. If no
truthful result exists, it reports `UNAVAILABLE`; policy does not silently upgrade missing evidence to a pass.

## Is the audit immutable?

No. It is **tamper-evident**: each event links to the previous hash, and verification recomputes the chain.

## How does this get aid to people faster?

It reduces the time between a broken supplier assumption and a valid replacement plan. Instead of restarting the
procurement process manually, teams see why the plan changed, what the new tradeoff costs, and exactly what needs a
fresh approval.

## What proof is available?

The latest verified recovery run completed two purchase orders, both delivered; verified a 32-event audit chain;
and replayed 29 delivery jobs without creating duplicates. The deployed release is a1fc478; review screenshots are in
`design/final-review/`.
