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

## 2-minute core

| Time | Say | Do |
| --- | --- | --- |
| 0:00–0:15 | "When a wildfire hits, emergency buyers source fast from suppliers they've never vetted. Then a supplier changes terms and the purchase plan breaks." | Mission header |
| 0:15–0:35 | "This mission is tied to a real, open NASA EONET event, with live NWS alerts, FIRMS fire detections, and FEMA declarations. They inform the buyer; they never decide what to buy." | Emergency panel, LIVE badges |
| 0:35–0:55 | "Two suppliers answered our emailed RFQ with binding quotes. Each was screened against the live Treasury sanctions list, openFDA, and USAspending. Missing evidence is never a pass, and no AI made the eligibility call." | Supplier cards, evidence chips, USER_SUBMITTED badges |
| 0:55–1:15 | "The integer optimizer splits the buy for $2,070. I requested this mission, so I can't approve it; my colleague does." | Run optimization → Plan v1 → B approves |
| 1:15–1:40 | Hand the supplier phone to the judge: "You're Supplier A. Raise your price." **Revise price → $25 → Save revision**. | Supplier portal shows Quote v2 |
| 1:40–2:00 | "That persisted change made Plan v1 stale and invalidated its approval. ReliefMesh replanned by itself: all 100 from Supplier B, $2,240, +$170, and it says why. A human must approve the new plan before anything is bought." | Recovery panel: STALE → v2, INVALIDATED, reasons |

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
