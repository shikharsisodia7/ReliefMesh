# Cal Hacks track eligibility audit

> **Final production SHA: TO BE RECONCILED**
>
> This is a conservative submission checklist, not a promise of eligibility. Hosted work is **PENDING MERGE** unless
> final reconciliation proves it is in the deployed release. A sponsor logo, SDK dependency, or repository branch
> alone is not evidence for a track.

## Submission status vocabulary

- **SUBMIT** — ReliefMesh has a meaningful, documented use and the team should submit evidence.
- **CONDITIONAL** — a stated sponsor rule, account requirement, artifact, or final deployment check remains.
- **SKIP** — there is no truthful, meaningful fit.

## Priority submission matrix

| Track / sponsor | Status | ReliefMesh usage | What must be shown |
| --- | --- | --- | --- |
| Hyphenate — autonomous systems for finance | **SUBMIT** | Procurement recovery automatically invalidates stale authorization and rebuilds plans; a human controls financial approval. | V1 → supplier change → stale → V2 → fresh approval. |
| Microsoft — real-world / customer impact | **SUBMIT** | Operational emergency-procurement system with deterministic and human-authority boundaries. | Live workflow, truthful data labels, and impact story. |
| Fetch.ai — best use of Fetch.ai | **SUBMIT** | Fetch.ai / uAgents agent surfaced through Agentverse / ASI:One for scoped operational questions. | Agent conversation and refusal to approve, order, or pay. |
| Apify — best use of Apify | **SUBMIT** | Public supplier-lead discovery. Results stay leads, not trusted quotes or inventory. | Discovery result and provenance boundary. |
| Gemini / GenAI | **SUBMIT** | Grounded supplier quote drafting with supplier review before submission. | Pasted quote → cited draft → supplier review. |
| Solana | **SUBMIT** | x402 evidence settlement on Solana devnet. | Explorer evidence labeled `DEVNET TEST PAYMENT`. |
| MongoDB Atlas | **SUBMIT** | Production system of record for organization-scoped procurement state. | Architecture and audit / operational records. |
| GoDaddy Registry | **SUBMIT** | `reliefmesh.us`. | Working domain and registration evidence as allowed. |

## Conditional tracks

| Track / sponsor | Status | Current boundary |
| --- | --- | --- |
| CRS Financial Intelligence | **CONDITIONAL** | Real CRS sandbox use with test identities; submit only with the requested sponsor evidence and correct `SANDBOX` language. |
| Coinbase x402 / Payment Agents | **CONDITIONAL** | x402 and Solana devnet are real, but do not claim any required Coinbase MCP capability unless final reconciliation proves it. |
| Armadin — security | **CONDITIONAL** | Authority boundaries, replay protection, tenant controls, and a tamper-evident audit are relevant; verify final prize requirements. |
| Figma in the Workflow | **CONDITIONAL** | **PENDING** actual Figma artifact. Do not submit as complete until a final artifact exists. |
| Bright Data | **CONDITIONAL** | **PENDING MERGE**. Do not claim use or track eligibility until it is merged, deployed, and materially used. |
| Anthropic / Claude | **CONDITIONAL** | **PENDING MERGE**. Do not claim runtime Claude use until it is merged and live. |
| Telegram | **CONDITIONAL** | **PENDING MERGE**. |
| Twilio | **CONDITIONAL** | **PENDING MERGE**. |

## Tracks to skip

| Track category | Status | Reason |
| --- | --- | --- |
| Hardware | **SKIP** | No hardware product. |
| Planet-first / climate-only | **SKIP** | Emergency relief is people-first, not a climate solution claim. |
| Consumer shopping | **SKIP** | ReliefMesh is emergency procurement, not consumer commerce. |
| Voice-first | **SKIP** | Voice is not core to the product. |
| Custom Apify Actor | **SKIP** | ReliefMesh uses an existing actor; it does not publish a custom actor. |
| Forge / Jira / Confluence workforce tracks | **SKIP** | No meaningful Forge integration. |
| Convex, SpacetimeDB, Mana, Nessie, Creator-agent-specific tracks | **SKIP** | Not part of the shipped architecture. |

## Evidence boundaries for every submission

| Claim | Required wording |
| --- | --- |
| Supplier quotes | `USER_SUBMITTED` |
| Supplier change | `ACTUAL USER-SUBMITTED CHANGE` |
| Continuity | `HYPOTHETICAL STRESS TEST` |
| Disaster / evidence APIs | `LIVE`, `CACHED`, or `UNAVAILABLE` |
| CRS | `SANDBOX` |
| x402 / Solana | `DEVNET TEST PAYMENT` |
| Audit | Tamper-evident, not immutable |
| Agent authority | Can explain scoped operational results; cannot approve, order, or pay |

## Final owner checklist

- [ ] Reconcile the exact deployed SHA for web, API, and agent.
- [ ] Confirm the final run still has the verified 2 total / 2 delivered POs, 32 audit events, and zero duplicate
      replay outcome.
- [ ] Add the final redacted screenshots and demo video.
- [ ] Add the Figma link only after an actual artifact is complete.
- [ ] Verify every **CONDITIONAL** track against the current official prize text.
- [ ] Submit only tracks marked **SUBMIT** unless the relevant condition has been closed.
