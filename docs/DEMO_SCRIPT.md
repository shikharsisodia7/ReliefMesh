# ReliefMesh demo script

Judging is table-side: **3 minutes to pitch, 2 minutes of questions** (Devpost). The core story fits in 2:00; the
last minute is optional depth. Every number on screen is computed live. Nothing below is a recording or an animation.

## Before judges arrive (2 minutes, once per session)

1. Open `/status`: confirm MongoDB, EONET, NWS, FIRMS, OFAC, openFDA, USAspending, x402 are green (and note honestly
   which are "not configured").
2. Sign in as the coordinator. Create a mission: pick a live NASA EONET event, "Shelter blankets", Oakland, CA,
   deadline +4 days, budget $5,000, 100 blankets. Press **Seed TEST suppliers** and wait for the evidence chips.
3. Keep a second window on ASI:One with the ReliefMesh Buyer Agent open.

## 2-minute core

| Time | Say | Do |
| --- | --- | --- |
| 0:00–0:15 | "When a wildfire hits, emergency buyers have to source fast from suppliers they've never vetted. Then a supplier drops out and the whole purchase plan breaks." | Mission header |
| 0:15–0:35 | "This mission is tied to a real, open NASA EONET wildfire. ReliefMesh pulls live NWS alerts, NASA FIRMS satellite fire detections, and FEMA declarations. They inform the operator but never decide what to buy." | Emergency panel: LIVE badges, FIRMS hotspot count |
| 0:35–0:55 | "Four suppliers quoted. They're labeled TEST, but their names were screened against the live Treasury OFAC list, openFDA, and USAspending. The cheapest one, Pioneer Logistics Supply, fuzzy-matches an SDN entry, so deterministic policy holds it for human review. Missing evidence is never a pass, and no AI made this call." | Pioneer card: OFAC POTENTIAL_MATCH chip → open evidence drawer (SDN #17229) |
| 0:55–1:15 | "The integer optimizer only sees eligible quotes. It splits the buy across Bayside and Golden Gate for $3,271, under budget and on time. The coordinator approves exactly this plan version." | Run optimization → Plan v1 → Approve |
| 1:15–1:40 | "Now the judge breaks the supply chain." Hand the judge the mouse: **DISRUPT SUPPLY CHAIN → Bayside withdraws**. "That changed persisted state, the same path a real supplier edit takes." | Plan v1 goes STALE, approval INVALIDATED |
| 1:40–1:55 | "With no human in the loop, ReliefMesh replans: Golden Gate plus Sierra, $3,466, +$195, and it shows exactly why it changed. The old approval can't buy anything. A human has to approve the new plan." | Before→after panel, cost delta, supplier delta |
| 1:55–2:00 | "Approve, issue POs, and every step is in a hash-chained audit log." | Approve v2 → Generate POs → chain-verified badge |

## Minute three (pick by judge)

- **Fetch.ai / Hyphenate:** in ASI:One, type `simulate Golden Gate cutting inventory`, then `what changed?`. The agent
  mutates real state and reports the autonomous replan, and it refuses to approve: "a human coordinator must approve."
- **x402 / Solana / Coinbase:** press **Buy signed dossier** on Pioneer. The machine gets HTTP 402, pays 0.01 devnet
  USDC through the x402 facilitator, and unlocks a signed dossier. Click the Solana explorer link for the settled
  transaction.
- **Human judgment (Hyphenate "knowing when to ask"):** clear Pioneer's finding with a reason. The plan replans to
  Pioneer at $2,600. The clearance is audited and bound to that exact evidence ID.
- **CRS:** (once sandbox credentials are configured) show the CRS identity/fraud evidence chip on a TEST supplier
  contact.

## If something fails live

- An API outage shows `CACHED` (last-known-good, with timestamp) or `UNAVAILABLE`, and policy goes to NEEDS_REVIEW.
  Say so: "this is the fail-closed behavior."
- A cold start on the free backend tier takes ~50 s. Open `/status` before judges arrive.
- Backup: `backend/scripts/smoke.py <API_URL>` runs the full disruption-recovery flow headlessly on live data in
  about 12 s.
