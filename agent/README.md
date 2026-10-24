# ReliefMesh Buyer Agent

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

**Emergency procurement you can run from a chat.** The ReliefMesh Buyer Agent operates a real
ReliefMesh procurement workspace through the Agent Chat Protocol, so the whole buyer workflow
(emergency → mission → supplier screening → optimization → disruption recovery) happens inside an
ASI:One conversation.

## What it does (real tool execution)

| Say | The agent calls | What comes back |
| --- | --- | --- |
| `show wildfire events in California` | `GET /v1/emergency-events` (live NASA EONET) | open events with IDs, categories, coordinates |
| `create a mission for 300 blankets delivered to Oakland, CA within 24 hours under $8,000` | `POST /v1/agent/missions` | a persisted mission, optionally linked to an EONET event |
| `run evidence checks` | `POST /v1/missions/{id}/evidence/refresh` | live OFAC / SAM.gov / openFDA / USAspending results per supplier |
| `find suppliers for N95 masks` | `POST /v1/missions/{id}/discovery` (Apify actor run) | supplier **leads**, never binding quotes |
| `optimize` | `POST /v1/missions/{id}/optimize` | the policy-gated mixed-integer allocation |
| `why was Pioneer rejected?` | `GET /v1/missions/{id}/explain` | the deterministic policy decisions and evidence IDs behind the allocation |
| `what changed after the disruption?` | `GET /v1/missions/{id}/brief` | old plan → new plan, cost delta, approval invalidation |

## What it can never do

The agent holds an organization-scoped ReliefMesh agent token. ReliefMesh rejects agent tokens on
plan approval, purchase-order creation/sending, and payments. Policy (sanctions, recalls, deadlines,
budget) is deterministic code in ReliefMesh; neither this agent nor any language model can clear a
finding or change an allocation.

## Configuration

| Variable | Purpose |
| --- | --- |
| `RELIEFMESH_API_URL` | ReliefMesh API base URL |
| `RELIEFMESH_APP_URL` | ReliefMesh web app URL (for links) |
| `RELIEFMESH_AGENT_TOKEN` | org-scoped agent token (`POST /v1/organizations/{id}/agent-tokens`) |
| `ASI1_API_KEY` | optional: ASI:One LLM selects the tool; otherwise a deterministic parser does |
| `AGENT_SEED` | local mailbox mode only |

## Agent

- Name: `reliefmesh-buyer-agent`
- Address: see the repository root README (published after registration)
- Protocol: AgentChatProtocol v0.3.0 (manifest published)
