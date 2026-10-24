# Sponsor eligibility audit

Evidence-based matrix (updated 2026-10-24 after deployment). "Live proof" means a deployed, judge-accessible
demonstration or provider artifact that was actually observed. Production shows real data only, so sandbox and devnet
proofs are labeled as such and never presented as real-world verification or payment.

Live: web https://reliefmesh-calhacks.vercel.app · API https://reliefmesh-api.onrender.com · status
https://reliefmesh-calhacks.vercel.app/status

| Track | Exact evidence observed | Live proof | Missing requirement | Verdict |
| --- | --- | --- | --- | --- |
| Cal Hacks core | Public repo; deployed web + API; real workflow verified on production (RFQ email → quotes → evidence → plan → independent approval → supplier revision → replan → PO → fulfillment) | Yes | Devpost submission, project image, demo video (owner) | CONDITIONAL |
| Fetch.ai / ASI:One | Mailbox agent `agent1qwsexvyvdavc0pjys60fgh7mev3d6xccnqfjg9famyqvnxrw4eajsxs243x` registered on Agentverse (Active, ASI Available), AgentChatProtocol manifest published, address + badges in README; Agentverse chat-protocol test run answered with live NASA EONET data and refused demo actions | Partial | One end-to-end ASI:One chat session from the owner's account (needs ASI:One onboarding), 3–5 min video | CONDITIONAL |
| Apify | `compass/crawler-google-places` runs from the deployed API, e.g. run `6LFVdn73xb0TMjtrW` / dataset `pGX4l3tGzAlGYLba9`; results stored as leads only | Yes | Custom Actor for "Best Actor" | ELIGIBLE (Best Actor: SKIP) |
| CRS | Live sandbox login + TransUnion TruValidate calls with CRS test identities (P01 verified; P12 flagged 2201/2202/2101); `/status` shows the sandbox session | Yes (sandbox) | Labeled SANDBOX; only test identities are ever sent, so it is a capability proof, not real-world verification | ELIGIBLE (sandbox) |
| Coinbase x402 | Official x402 SDK, HTTP 402 → signed payment → facilitator settlement from the deployed API; receipts stored | Yes (devnet) | Labeled DEVNET TEST PAYMENT; requires a supplier on a mission to buy a dossier | ELIGIBLE (devnet) |
| Solana | Settled devnet USDC transactions, e.g. `3bd8HVQjv5eqGCDsMUKreueZe9YygUXHxbrqBmQztrro1amRN1g9EdeVN76chKSwNfgyuUmNeP6Q7EKq45sc87Es` (explorer link in README) | Yes (devnet) | Never presented as supplier settlement | ELIGIBLE (devnet) |
| Gemini | Grounded quote-draft assistant in the supplier RFQ form (free tier, schema-constrained, every value cited from the pasted text); real-Gemini E2E test passes | Yes | Track-specific submission form (owner) | ELIGIBLE |
| Moss | No integration | No | Retrieval/memory implementation | SKIP |
| Elastic | No indexing/query implementation | No | Real indexed evidence query | SKIP |
| Convex | No integration | No | Reactive backend | SKIP |
| Factory | No runtime Factory Droid work | No | Meaningful runtime use | SKIP |
| Cartesia | No voice feature | No | Core voice workflow | SKIP |
| Creao | No agent ID or run-share link | No | Core CREAO agent proof | SKIP |
| Snowflake | No integration | No | Real Snowflake query | SKIP |
| Figma | No Figma file/prototype links | No | Design artifacts and recording | SKIP unless created |
| Bright Data | No integration | No | Public-web data feature | SKIP |
| Capital One Nessie | Environment fields only | No | Real sandbox workflow | SKIP |

The Fetch HackPack requires Agentverse registration, ACP, ASI:One discovery and direct usability, meaningful tools,
completion of the primary workflow in ASI:One, a public repository with agent name/address, and a 3–5 minute demo
video. Everything except the owner-account ASI:One session and the video is in place. See the
[Fetch CalHacks HackPack](https://www.fetch.ai/events/hackathons/calhacks-13-0/hackpack) and
[Cal Hacks Devpost](https://cal-hacks-13-0.devpost.com/).
