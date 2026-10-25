# Cal Hacks track eligibility

> **Production SHA: a1fc478** (web on Vercel, API on Render; the Fetch.ai agent code is unchanged since 9bbe49d).
>
> Every track below is submitted. Each row says what ReliefMesh actually uses, and the labels in "Evidence
> boundaries" still apply to every claim.

## Submission status vocabulary

- **SUBMIT**: ReliefMesh is submitted to this track with the usage described.
- **SKIP**: there is no meaningful fit, so it is not submitted.

## Submitted tracks

| Track / sponsor | Status | ReliefMesh usage | What to show |
| --- | --- | --- | --- |
| Hyphenate: autonomous systems for finance | **SUBMIT** | Procurement recovery automatically invalidates stale authorization and rebuilds plans; a human controls financial approval. | V1 → supplier change → stale → V2 → fresh approval. |
| Microsoft: real-world / customer impact | **SUBMIT** | Operational emergency-procurement system with deterministic and human-authority boundaries. | Live workflow, truthful data labels, and impact story. |
| Fetch.ai: best use of Fetch.ai | **SUBMIT** | Fetch.ai / uAgents agent surfaced through Agentverse / ASI:One for scoped operational questions. | Agent conversation and refusal to approve, order, or pay. |
| Apify: best use of Apify | **SUBMIT** | Public supplier-lead discovery. Results stay leads, not trusted quotes or inventory. | Discovery result and provenance boundary. |
| Gemini / GenAI | **SUBMIT** | Grounded supplier quote drafting with supplier review before submission. | Pasted quote → cited draft → supplier review. |
| Solana | **SUBMIT** | x402 evidence settlement on Solana devnet. | Explorer evidence labeled `DEVNET TEST PAYMENT`. |
| MongoDB Atlas | **SUBMIT** | Production system of record for organization-scoped procurement state. | Architecture and audit / operational records. |
| GoDaddy Registry | **SUBMIT** | `reliefmesh.us`. | Working domain. |
| CRS Financial Intelligence | **SUBMIT** | CRS / TransUnion TruValidate sandbox signer identity and fraud checks with CRS-published test identities. | The CRS rows on `/status`, labeled `SANDBOX`. |
| Coinbase x402 / Payment Agents | **SUBMIT** | x402 machine payments for evidence dossiers, settled in test USDC on Solana devnet. | A devnet x402 payment and its explorer link. Coinbase Payments MCP is not used, so it is not claimed. |
| Armadin: security | **SUBMIT** | Approvals bound to an exact plan version and hash, replay-safe purchase orders, serialized approve / issue / send, tenant isolation, and a tamper-evident audit chain. | Stale-approval revocation, duplicate-click safety, and the verified hash chain. |
| Figma in the Workflow | **SUBMIT** | The redesign was specified as a design system, page specs, and approved mockups (`design/`) and built from them. | The design handoff and the before/after screens; attach the Figma file link on Devpost. |
| Bright Data | **SUBMIT** | Web Unlocker retrieves a lead's public website so the coordinator reviews it before inviting the lead. | A lead's public-page snapshot with its source URL and retrieval time. |
| Anthropic / Claude | **SUBMIT** | Claude writes an evidence-bounded explanation of a recovery plan, citing the plan records it used. It cannot change policy, plans, or approvals. | A recovery explanation with its cited sources. |
| Telegram | **SUBMIT** | Suppliers link Telegram from the portal and handle RFQs, quotes, and orders in the bot; Telegram cannot approve purchases. | Portal link → `/start` in @ReliefMeshSupplierBot → `/rfqs` and a quote. |
| Twilio | **SUBMIT** | Opt-in supplier SMS channel through a Twilio webhook, with fixed commands and validated intents. | The SMS flow from `docs/TWILIO_SMS_SETUP.md`. |

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

- [x] Reconcile the exact deployed SHA for web, API, and agent (web and API a1fc478; agent 9bbe49d, unchanged).
- [ ] Confirm the final run still has the verified 2 total / 2 delivered POs, 32 audit events, and zero duplicate
      replay outcome.
- [ ] Add the final redacted screenshots and demo video.
- [ ] Attach the Figma file link on Devpost.
- [x] Submit every track marked **SUBMIT**.
