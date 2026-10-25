# Cal Hacks 13.0 track eligibility audit

Audited on 2026-10-24 against the [current Cal Hacks 13.0 Devpost](https://cal-hacks-13-0.devpost.com/), the
[Fetch event page](https://www.fetch.ai/events/calhacks-13-0), and the checked-in implementation. Devpost requires
an accepted/check-in participant, a 2–4 person college-student team, a GitHub repository, project image, work done
during the event, a three-minute pitch, and a live or prerecorded demo. Those are human/team facts, so this document
does **not** mark any submission fully eligible until the owner supplies the requested submission evidence.

Legend: `✅ VERIFIED ELIGIBLE` means meaningful, judge-visible provider use and normal submission action remain.
`🟢 IMPLEMENTED — SUBMISSION ACTION NEEDED` means deployment proof should be re-recorded for this release.
`🟡 PARTIAL` means a meaningful prerequisite is missing or unverified. `⚫` means the fit is forced or ineligible.
“Proof” is a path for a judge to inspect, not an assertion that this audit reran a paid or production action.

## Core categories

| Track / prize | Exact requirement / technology | ReliefMesh use / live evidence | Missing / risk | Status, submission + demo action |
| --- | --- | --- | --- | --- |
| First Overall — $3,600 | Working, original, useful project; normal submission rules | Continuity Engine: disaster → user-submitted quote → deterministic plan → N-1/failure frontier → human recovery. | Team check-in, Devpost image/video, final live smoke. | 🟢 Submit as primary story; demo the cost-vs-resilience decision. |
| Second / Third Overall | Same core judging criteria | Same as First Overall. | Same. | 🟢 Same submission. |
| Most Creative | Distinct, intentional experience | Procurement Digital Twin + supplier stress-test lanes make “what breaks this plan?” visible. | Browser/demo proof after deployment. | 🟢 Show concentration lanes + failure frontier. |
| Most Technically Complex | Sound engineering depth | MILP, counterfactual re-optimization, pinned inputs, stale analysis, policy, jobs, approvals, audit chain. | Clean full test/build proof. | 🟢 Explain no LLM controls the result. |
| People-First Social Impact | Feasible benefit for people | Emergency coordinator workflow, designed to reduce procurement disruption. | Do not claim outcomes not measured. | 🟢 Show protected units, resilience cost, human authority. |
| Planet-First Social Impact | Environmental benefit | Disaster context exists, but product has no measured planet outcome. | Weak/forced fit. | ⚫ Skip. |
| Best Hardware | Hardware project | No hardware. | Ineligible. | ⚫ Skip. |
| Best Beginner | Beginner eligibility | Team experience is not audited. | Human-only eligibility. | ⚫ Skip unless organizer confirms. |
| Best Solo | Solo eligibility | Devpost requires 2–4 team members. | Team-incompatible. | ⚫ Skip. |
| Hacker's Choice | General submission | Coherent demo and public project. | Submission/video. | 🟢 Submit normally. |

## Sponsor categories

| Track / prize | Exact requirement / technology | ReliefMesh use / live evidence | Missing / risk | Status, submission + demo action |
| --- | --- | --- | --- | --- |
| Anthropic — Claude for Public Benefit ($4,998) | Public benefit plus meaningful Claude use if current rules require it | Public-benefit workflow only; Anthropic key is configuration, not verified runtime use. | No meaningful Claude call. | 🟡 Add only a structured Continuity Brief if credits/rules permit; otherwise skip. |
| MLH — Gemini API | Meaningful Gemini API feature | Grounded quote-draft; supplier reviews before USER_SUBMITTED quote. | Production quota/live call not rerun. | 🟢 Record a grounded draft; show AI has no policy/optimizer authority. |
| MLH — Solana | Meaningful Solana app/payment/supply-chain prototype | x402 evidence purchase settles test USDC on Solana devnet; receipt stored. | Must label DEVNET TEST PAYMENT; rerun proof. | 🟢 Trigger devnet evidence purchase and open receipt. |
| MLH — Tiger Data | Meaningful Tiger Data | MongoDB only. | No integration. | ⚫ Skip. |
| MLH — Vultr | Meaningful Vultr | Deployment provider not verified as Vultr. | No provider proof. | ⚫ Skip. |
| MLH — Commit Fellowship | Working prototype, real problem, opt-in + supplemental form | Working emergency-procurement use case. | Owner must opt in and complete form. | 🟡 Owner action only. |
| MLH — Snowflake API | Meaningful Snowflake REST/API use | No Snowflake flow. | No integration. | ⚫ Skip. |
| MLH — GoDaddy Registry domain | Register/use a GoDaddy Registry domain | `reliefmesh.us` is canonical public domain in code/docs. | Registrar/program provenance unverified. | 🟡 Verify registration, HTTPS, Devpost link. |
| Hyphenate — Autonomous Systems for Finance ($16,000) | Autonomous finance; exact hackpack rules apply | Natural: deterministic policy, hash-bound approvals, invalidation, audit, devnet machine payment. | No verified Hyphenate product requirement/proof. | 🟡 Enter only if confirmed rules allow; demo “autonomous finance without autonomous authority.” |
| Visa — Reimagining Shopping ($5,000) | Eligible shopping/purchasing experience | Institutional emergency purchasing under uncertainty is plausible. | No Visa tech; rules unverified. | 🟡 Narrative possibility; do not claim eligibility. |
| Fetch.ai — Best Use of Fetch.ai | Meaningful Fetch/ASI:One use | Agentverse/ASI:One buyer agent uses real API, isolates conversations, and now answers deterministic continuity queries. | Active mailbox/session + video need recheck. | 🟢 Ask “single point of failure?” and show refusal to approve. |
| Microsoft — Built for the Real World / Customer Impact | Real-world usefulness and customer impact | Multi-tenant workflow, operational degradation, human authority, auditability. | Sponsor form/rules unverified. | 🟢 Submit continuity story, deployment evidence, security posture. |
| Meta — Bringing People Closer Together with AI | AI that connects people | Supplier/coordinator collaboration exists but not a natural social product. | Forced fit. | ⚫ Skip. |
| Factory — Droid SDK ($2,000) | Meaningful runtime Factory Droid SDK | No runtime Factory SDK. | No integration. | ⚫ Skip. |
| Armadin — Best Security Hack ($996) | Security innovation | Agent authority, tenant isolation, stale-approval/replay protections, tamper-evident audit. | Need sponsor rules + judge-visible attack matrix. | 🟡 Add/demo attack matrix before entering. |
| Cartesia — Best Use of Cartesia ($1,516) | Meaningful Cartesia product | No voice workflow. | No integration. | ⚫ Skip. |
| Convex — Best Use of Convex ($5,000) | Real Convex database/functions/workflows/sync/search | MongoDB architecture. | No integration. | ⚫ Skip. |
| Apify — Best Use of Apify ($4,600) | Meaningful Apify use | `compass/crawler-google-places`; stores run/dataset IDs as leads only. | Repeat final live actor run. | 🟢 Show run ID and lead/quote boundary. |
| Apify — Best Actor ($400) | Meaningful custom Actor | Existing actor only. | No custom Actor. | ⚫ Skip unless a real Emergency Supplier Intelligence Actor is published and used. |
| CREAO — AI-First Disruptor / One-Person / Team Empowerment | Meaningful CREAO use | No CREAO product evidence. | One-person conflicts with team rule. | ⚫ Skip. |
| Bitdeer AI Model Studio | Meaningful Bitdeer use | None. | No integration. | ⚫ Skip. |
| Elastic — Agent Builder on Serverless | Real Elastic Agent Builder + serverless | No runtime implementation. | Optional settings are not use. | ⚫ Skip. |
| Capital One — Nessie | Meaningful Nessie API | Optional config only. | No API flow. | ⚫ Skip. |
| CRS — Best Use of CRS API ($3,000) | Meaningful CRS API | CRS/TruValidate sandbox signer check gates policy; SANDBOX personas only. | Fresh sandbox proof needed. | 🟢 Show P01/P12 capability and fail-closed policy. |
| Moss — Best Use of Moss | Meaningful Moss use | None. | No integration. | ⚫ Skip. |
| SpaceXSI — Make it Legendary | Built with Cursor; real space data | NASA EONET/FIRMS context only. | Cursor provenance and space-centric story absent. | ⚫ Skip. |
| Figma — workflow / agent / design | Current Figma artifact and linked rules | No linked Figma file/prototype. | No required artifact. | ⚫ Skip until real artifact/rules exist. |
| Coinbase — x402 ($4,000) | Meaningful x402 use | HTTP 402 evidence paywall → facilitator → devnet receipt; never supplier settlement. | Rerun within spend/rate cap. | 🟢 Demo evidence unlock + receipt. |
| Notability | Meaningful Notability integration | None. | No integration. | ⚫ Skip. |
| Spacetime | Meaningful SpacetimeDB | No SpacetimeDB. | No integration. | ⚫ Skip. |
| Mana | Meaningful Mana use | None. | No integration. | ⚫ Skip. |
| Bright Data — Public Web Data | Meaningful Bright Data public-web product | Apify is not Bright Data. | No Bright Data integration. | ⚫ Skip; do not duplicate Apify just for eligibility. |
| Atlassian — Best Agent / Security Solution for Agents | Select track; linked sponsor rules apply | Fetch agent has capability restrictions and isolation. | No Atlassian product use confirmed; attack evidence needed. | 🟡 Consider Security Solution only after rules + tests are satisfied. |

## Judge-visible evidence paths

| Integration | Evidence path | Truth boundary |
| --- | --- | --- |
| Continuity Engine | Mission → **Continuity Engine** → input hash, N-1 rows, failure frontier, resilient proposal | `HYPOTHETICAL STRESS TEST`; never mutates quote/plan/approval. |
| Fetch.ai | ASI:One → Buyer Agent → “which supplier is the biggest single point of failure?” | Agent explains deterministic result; cannot approve/pay. |
| Apify | Supplier discovery → run/dataset ID → leads | Public leads only; never inventory or submitted quote evidence. |
| CRS | Supplier evidence → signer record | `SANDBOX`; test personas only, no real identity claim. |
| Coinbase x402 / Solana | Evidence dossier → HTTP 402 → devnet explorer receipt | `DEVNET TEST PAYMENT`; no supplier is paid. |
| Gemini | Supplier RFQ → grounded draft → supplier review/submission | AI only drafts values from supplied text. |
| Security | Timeline/audit + authority matrix | Audit is tamper-evident, not immutable. |

## Submission gate

Before selecting any `🟢` row, capture a dated screen/video of the stated path, confirm the current sponsor hackpack/form,
and upgrade it to `✅ VERIFIED ELIGIBLE` only when the team and provider requirements are genuinely met. An SDK,
environment variable, old receipt, or mocked call is never eligibility proof.
