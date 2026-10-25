# ReliefMesh demo script

Judging is table-side: **3 minutes to pitch, 2 minutes of questions** (Devpost). The core story fits in 2:00. The live
site shows **real data only**: there are no seeded suppliers and no "disrupt" button. Suppliers are real accounts
(for the demo: teammates acting as suppliers from their own inboxes), and the disruption is a real supplier action.

## Before judges arrive (once per session, ~5 minutes)

1. Open `/status`. Every row is a real request made just now; note honestly which say NOT CONFIGURED (SAM.gov).
2. Coordinator A (you) signs up, creates the organization, and adds Coordinator B as **approver** (invite link by
   email). B signs up and accepts. A cannot approve A's own missions (segregation of duties).
3. A creates a mission: pick a live NASA EONET event, "Emergency shelter blankets", 100 blankets, budget $3,000.
4. Send RFQs to two teammates' email addresses. Each receives a real email (Resend), opens the secure link, signs up
   as a supplier, and submits a quote, e.g. Supplier A 60 @ $18.50 and Supplier B 100 @ $22.00. Supplier A can paste
   an existing quote and press **Pre-fill with Gemini**, then review before submitting.
5. Wait for the evidence chips (live OFAC, openFDA, USAspending). Keep ASI:One open with the ReliefMesh Buyer Agent.

## 3-minute core

| Time | Say | Do |
| --- | --- | --- |
| 0:00–0:18 | "Emergency procurement software produces a plan for today's assumptions. ReliefMesh asks whether that plan survives tomorrow's failures." | Mission header + LIVE emergency context |
| 0:18–0:38 | "These are real USER_SUBMITTED supplier quotes. Public evidence informs a deterministic policy; no AI decides who is eligible." | Supplier cards/evidence chips |
| 0:38–0:55 | "The MILP finds the cheapest exact-coverage plan. I requested it, so I cannot approve it—an independent person must." | Plan V1 |
| 0:55–1:35 | "Before approval, Continuity tests the exact quote snapshot. This is a **HYPOTHETICAL STRESS TEST**, not a claimed failure." Show the critical lane, an N-1 scenario, price/ETA/capacity frontier, and cost of the ≤50% concentration alternative. | Continuity Engine / Digital Twin |
| 1:35–2:05 | Hand the supplier phone to the judge: "Raise your price." Make the actual USER_SUBMITTED revision. | Supplier quote v2 |
| 2:05–2:30 | "Reality changed. Plan V1 is stale, approval is revoked, and the analysis is stale too—so it cannot mislead us." | Timeline + stale labels |
| 2:30–2:48 | "ReliefMesh generated Plan V2 from the revised facts. It shows the cost and supplier delta, and it needs fresh human approval." | Recovery panel: V2 + approval boundary |
| 2:48–3:00 | "The agent can explain these deterministic results, but cannot approve or pay. Here is the tamper-evident audit chain." | Fetch question + audit verification |

## Minute three (pick by judge)

- **Purchase orders:** B approves v2, A issues and sends the PO (real email). The supplier accepts, ships, and every step
  lands in the hash-chained audit log (`chain verified`). If a supplier **declines** a PO or marks **Cannot fulfill**,
  ReliefMesh replans only the uncovered remainder; units already on active POs stay committed.
- **Fetch.ai:** in ASI:One ask `show wildfire events in California`, then create a mission by chat. The agent reports only
  real state ("no supplier quotes have been received yet") and refuses to approve: a human coordinator must.
- **x402 / Solana (DEVNET TEST PAYMENT):** **Buy signed dossier** on a supplier: HTTP 402, 0.01 devnet USDC through the
  x402 facilitator, settled on Solana devnet. It proves machine-to-machine payment; no supplier is paid.
- **CRS (SANDBOX):** `/status` shows the CRS sandbox session. Only CRS-published test identities are ever sent; it is a
  sponsor-sandbox capability, not real-world identity verification.

## If something fails live

- An API outage shows `CACHED` (last-known-good, with timestamp) or `UNAVAILABLE`, and policy goes to NEEDS_REVIEW.
  Say so: "this is the fail-closed behavior."
- A cold start on the free backend tier takes ~50 s. Open `/status` before judges arrive.
- If an RFQ email is not delivered, ReliefMesh says "Email NOT sent" and shows the secure link to relay by hand
  (only the invited address can accept it).
