# ReliefMesh final status ledger

> **Release / production SHA: a1fc478** (main = release/final). Web on Vercel and API on Render run a1fc478; the
> Fetch.ai agent runs 9bbe49d (agent code unchanged since). Claude, Bright Data, Telegram, and Twilio are merged and
> deployed.

## Live entry points

- Web: https://reliefmesh.us
- API: https://reliefmesh-api.onrender.com/health
- Judge guide: https://reliefmesh.us/judge
- System status: https://reliefmesh.us/status

## Latest verified recovery evidence

| Check | Verified result |
| --- | --- |
| Procurement outcome | 2 total purchase orders · 2 delivered |
| Audit | 32 events · tamper-evident chain verified |
| Delivery replay | 29 deliveries / 29 unique idempotency keys before replay · 29 / 29 after replay |
| Gmail replay | 4 → 4 |
| Slack replay | 9 → 9 |
| Calendar replay | 4 → 4 |
| Drive replay | 5 → 5 |
| PO replay | 2 → 2 |
| x402 replay | 1 → 1 |
| Duplicates | 0 |

## Recovery story

1. V1 was approved.
2. A supplier changed price.
3. V1 became stale and its approval was revoked.
4. ReliefMesh built V2 automatically and reran Continuity.
5. A human issued a fresh approval for the new version.
6. Two purchase orders completed and both were delivered.
7. The audit chain verified and replay created no duplicate operational records.

## Truth boundaries

| Claim | Required label or boundary |
| --- | --- |
| Supplier quote | `USER_SUBMITTED` |
| Supplier change | `ACTUAL USER-SUBMITTED CHANGE` |
| Continuity scenario | `HYPOTHETICAL STRESS TEST` |
| Disaster and public evidence | `LIVE`, `CACHED`, or `UNAVAILABLE` |
| CRS | `SANDBOX` |
| x402 / Solana | `DEVNET TEST PAYMENT` |
| Audit | Tamper-evident, not immutable |
| Financial authorization | Human only |

## Reconciliation checklist

- [x] Confirm the commit deployed to web, API, and agent.
- [ ] Confirm the matching production test evidence timestamp.
- [x] Confirm hosted Claude, Bright Data, Telegram, and Twilio work is merged and deployed.
- [ ] Add final, redacted production screenshots.
- [ ] Add the Figma file link.
- [ ] Refresh [track eligibility](qa/TRACK_ELIGIBILITY.md) immediately before Devpost submission.

## Known presentation limits

- Final screenshots are **PENDING**; no unverified image paths are used in the README.
- Design screens for review are in `design/final-review/`.
