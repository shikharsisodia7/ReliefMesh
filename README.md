# ReliefMesh

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

**ReliefMesh is a procurement continuity engine for emergency response.** Instead of only finding the cheapest
purchasing plan, it mathematically stress-tests that exact plan against supplier loss, price shocks, delays, and
capacity reductions; calculates a constrained resilient alternative; and automatically invalidates and rebuilds the
plan when a real supplier change occurs. Coordinators buy from real supplier quotes, deterministic policy decides
eligibility, and independent humans retain financial authority.

| | |
| --- | --- |
| Web app | https://reliefmesh.us |
| API | https://reliefmesh-api.onrender.com ([/health](https://reliefmesh-api.onrender.com/health), [/docs](https://reliefmesh-api.onrender.com/docs)) |
| Live integration status | https://reliefmesh.us/status |
| Fetch.ai agent | `reliefmesh-buyer-agent` · `agent1qwsexvyvdavc0pjys60fgh7mev3d6xccnqfjg9famyqvnxrw4eajsxs243x` · [Agentverse](https://agentverse.ai/agents/details/agent1qwsexvyvdavc0pjys60fgh7mev3d6xccnqfjg9famyqvnxrw4eajsxs243x/profile) · [Chat on ASI:One](https://asi1.ai/ai/agent1qwsexvyvdavc0pjys60fgh7mev3d6xccnqfjg9famyqvnxrw4eajsxs243x) |

## Why ReliefMesh is different

Procurement software produces a plan for today's assumptions. ReliefMesh asks whether that plan will survive
tomorrow's disruption. For every feasible plan, the **Continuity Engine** queues a bounded, background, deterministic
analysis that persists an exact input binding (mission, plan version/hash, quote versions, policy fingerprint,
evidence fingerprint, optimizer inputs, timestamp). It runs the same MILP on copies of the saved quote snapshot:

```text
CHEAPEST PLAN → N-1 SUPPLIER SHOCKS → FAILURE FRONTIER → RESILIENT ALTERNATIVE
       │                │                    │                     │
       └── real quote change ──> plan stale / approval revoked ──> automatic Plan V2
```

The results are always labeled **HYPOTHETICAL STRESS TEST**. They never mutate a real quote, supplier, policy,
approval, or purchase order; any material input change marks the result **STALE**. The resilient proposal applies a
transparent 50% supplier-concentration guardrail and still requires the normal independent human approval.

## What happens, end to end

1. A coordinator links a mission to a **live NASA EONET event** and sees live NWS alerts, NASA FIRMS fire
   detections, and OpenFEMA declarations for that location.
2. Suppliers are discovered (**Apify** Google Maps actor → leads only) and invited by **real RFQ email** (Resend) with a
   single-use secure link. Each supplier signs up and submits its own **binding quote** mapped to stable requirement IDs
   (optionally pre-filled by **Gemini** from a pasted quote, every value grounded in the pasted text and reviewed).
3. Every supplier's legal name is screened against the **Treasury OFAC SDN list**, **openFDA** enforcement
   reports, **USAspending** awards, and **SAM.gov**. Its authorized signer is identity-checked through the
   **CRS sandbox** (TransUnion TruValidate). Every evidence record shows provenance and retrieval time.
4. A **deterministic policy engine** (no LLM) decides PASS / WARN / NEEDS_REVIEW / BLOCK. Missing or failed
   screening is never a pass, and a fuzzy sanctions match always goes to a human.
5. A **PuLP/CBC mixed-integer optimizer** allocates across eligible quotes only, under budget, inventory, deadline,
   and concentration constraints.
6. An **independent approver** approves the exact plan version. The requester cannot self-approve. Approvals are
   bound to the plan hash, expire, and work once.
7. When a supplier revises or withdraws its quote, declines a PO, cancels fulfillment, or gets blocked, the plan goes
   **stale**, the approval is **revoked**, unsent PO drafts are voided, and a background job **replans**. The UI
   shows old vs new plan, why it changed, cost delta, and supplier delta. A new approval is required.
8. Purchase orders are issued idempotently, sent only after explicit confirmation, and accepted and fulfilled by
   suppliers. Every step lands in a **SHA-256 hash-chained audit log** with a verification endpoint.
9. Premium evidence can be bought machine-to-machine over **HTTP 402 with Coinbase x402**, settled in USDC on
   **Solana devnet**. Receipts include the on-chain signature.
10. The whole buyer workflow is also available from an **ASI:One** conversation through the **Fetch.ai** agent. It
    can never approve spending.

## What is real, sandbox, and test

| Data | Provenance |
| --- | --- |
| NASA EONET, NWS, NASA FIRMS, OpenFEMA, OFAC SDN/ALT, openFDA, USAspending, Apify results | `LIVE` (or `CACHED` last-known-good with its original timestamp) |
| CRS identity verification | sponsor `SANDBOX`: CRS-published test identities only, never real supplier data; not real-world verification |
| x402 payments | **DEVNET TEST PAYMENT** (`SANDBOX`): proves machine-to-machine payment; no real money, no supplier is paid. Any signed-in user can run one from `/status` |
| Suppliers and quotes | real accounts only (`USER_SUBMITTED`); a new mission starts with 0 suppliers and 0 quotes |
| Demo tooling (seeded TEST suppliers, simulated disruptions) | local/test only with `RELIEFMESH_DEMO_MODE=true`; production refuses to start with it |
| Supplier-entered quotes | `USER_SUBMITTED` |
| SAM.gov | `LIVE` registration lookup (registration only: not inventory, quality, or capacity). A personal key allows ~10 requests/day, so lookups are cached a day per name; past the quota a supplier shows `UNAVAILABLE`, never a fake pass |

## Sponsor integrations (verified against live services)

- **Fetch.ai**: uAgents mailbox agent on Agentverse, Agent Chat Protocol (manifest published), usable from ASI:One.
  Real tool execution against the API ([agent/](agent/README.md)). Per-conversation isolation; it can't approve, order,
  or block.
- **CRS**: TransUnion TruValidate identity checks of supplier signers ([integrations/crs.py](backend/app/integrations/crs.py)).
  A failed check holds a supplier for review even after its sanctions false-positive is cleared.
- **Apify**: supplier discovery via `compass/crawler-google-places`, storing actor, run, and dataset IDs ([integrations/apify.py](backend/app/integrations/apify.py)).
- **Coinbase x402 + Solana**: official x402 Python SDK. Exact scheme on `solana:EtWTRABZaYq6iMfeYKouRu166VU2xqa1`
  through the x402.org facilitator ([payments/x402_exchange.py](backend/app/payments/x402_exchange.py)). Example settled tx:
  [`3bd8HVQj…c87Es`](https://explorer.solana.com/tx/3bd8HVQjv5eqGCDsMUKreueZe9YygUXHxbrqBmQztrro1amRN1g9EdeVN76chKSwNfgyuUmNeP6Q7EKq45sc87Es?cluster=devnet).
- **Google Gemini** (free tier): grounded quote-draft assistant; drafts are never stored or submitted without review.
- **Resend**: RFQ and purchase-order email with provider message IDs recorded per delivery.
- **MongoDB Atlas**: production system of record (M0, us-west-2).
- **Operations integrations** ([docs/OPERATIONS_INTEGRATIONS.md](docs/OPERATIONS_INTEGRATIONS.md)): each organization
  connects its own Gmail (RFQs, approval requests, disruption alerts, POs with PDF), Google Calendar (deadline,
  approval window, supplier ETA), Google Drive (plan/PO/audit archive) and Slack (informational alerts, never
  approvals). Gmail, Calendar, Drive and Slack are verified with real calls; deliveries are idempotent and never block procurement.

## Run locally

```bash
# API (memory store, no credentials needed; live public data still works)
cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # or bin/ on macOS/Linux
RELIEFMESH_APP_ENV=test RELIEFMESH_EXPOSE_INVITATION_LINKS=true .venv/Scripts/python -m uvicorn app.main:app --port 8000

# Web
cd frontend && npm install && NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run dev

# Agent (optional; needs an org agent token from POST /v1/organizations/{id}/agent-tokens)
cd agent && pip install -r requirements.txt && RELIEFMESH_API_URL=http://localhost:8000 RELIEFMESH_AGENT_TOKEN=... python reliefmesh_agent.py
```

Copy `backend/.env.example` for optional keys (FIRMS, SAM.gov, CRS sandbox, Apify, x402 devnet wallets).

## Tests

```bash
cd backend && python -m pytest            # 105 tests: policy, evidence, SoD, isolation break-in, failure modes, x402 + SAM.gov quota guards, audit chain
cd frontend && npm test && npm run lint && npm run build
cd frontend && npx playwright test        # two-supplier flow with an independent approver + live-data judge scenario
python backend/scripts/smoke.py http://127.0.0.1:8000                 # demo deployments only (RELIEFMESH_DEMO_MODE=true)
python agent/test_conversation_production.py http://127.0.0.1:8000     # agent against a non-demo API: no invented data
python agent/test_conversation.py http://localhost:8000                # agent conversation against a running API
```

Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
