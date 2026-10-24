# Release verdict

Audited implementation commit: `643a4c1` (`origin/feat/reliefmesh-finish`). QA changes are isolated on `codex/qa-release`.

## Remediated and independently verified

1. **REL-001 — stable requirement mapping.** Mission requirements now receive stable IDs, supplier quote lines are pinned to those IDs, and allocations retain both the mission item and the supplier's description. The independent QA regression suite verifies renamed descriptions, invalid/missing/duplicate mappings, and exact-name legacy pinning.
2. **REL-002 — segregation of duties.** A real-organization mission creator receives `403 SEGREGATION_OF_DUTIES`; a separately invited `approver` can approve the same plan. The narrow demo override is only permitted when demo controls are enabled and every allocated supplier is labeled TEST.

## Blocking defects

1. **REL-003 — cross-conversation Fetch agent plan leak (critical tenant-isolation failure).**
   - Reproduction: create an agent mission with `X-Agent-Sender: conversation-a`, optimize it, then use the same organization agent token with `X-Agent-Sender: conversation-b` on `GET /v1/plans/{plan_id}`. It returns the plan.
   - Expected: `403` because the plan's mission belongs to another sender.
   - Actual: `backend/app/routes/procurement.py:get_plan()` calls `require_org_member()` only. Other mission-scoped endpoints use `require_mission_access()` and enforce sender isolation.
   - Required fix: load the plan's mission and use `require_mission_access()` (or an equivalent sender-aware helper) for direct plan reads; audit every direct mission-derived object endpoint the same way.

## High-risk defects

- **REL-004 — supplier RFQ invitation acceptance is replayable.** `invitation_from_token()` checks existence and expiry but not accepted/consumed state; the same matching supplier can accept repeatedly. Organization-member invitation links are correctly single-use, but supplier RFQ acceptance needs the same state-transition protection or a documented idempotent response.
- **REL-005 — Render enables synthetic demo controls in production.** `render.yaml` sets `RELIEFMESH_DEMO_CONTROLS_ENABLED=true`, allowing an organization admin to seed TEST suppliers and mutate them in a production deployment. Default this to false for public deployments; enable only in a dedicated judge environment.
- **DEP-001 — pytest advisory.** `pytest 8.4.2` is affected by medium `PYSEC-2026-1845` / `CVE-2025-71176`; test the suite with pytest 9.0.3 or newer and remove the `<9.0` cap.

## Non-blocking issues

- Audit records are tamper-evident but not immutable; there is no externally anchored checkpoint.
- No production URLs or credentials were supplied, so deployment, persistence, delivery, and sponsor integrations remain unverified.
- x402 idempotency and receipt structure are well-covered locally, but no live devnet transaction/RPC confirmation was observed.
- Sponsor tracks have code-level support only where shown in `TRACK_ELIGIBILITY.md`; no live eligibility claim is justified yet.

## Control summary

| Control | Verdict |
| --- | --- |
| CORE WORKFLOW | PASS (local browser tests) |
| TENANT SECURITY | FAIL (REL-003) |
| APPROVAL CONTROLS | PASS (local independent regression and browser workflow) |
| OPTIMIZER | PASS (stable requirement-ID regression and browser workflow) |
| POLICY | PASS (local deterministic and adversarial tests) |
| AUDIT CHAIN | PASS — tamper-evident, not immutable |
| PAYMENT IDEMPOTENCY | PASS (local unit tests only) |
| SECRET SCAN | PASS (current tree and reachable history; scanner limitation documented) |
| PUBLIC REPO SAFETY | PASS (no committed real secrets found) |
| DEPLOYMENT | NOT AVAILABLE |
| SPONSOR CLAIMS VERIFIED | 0/17 live track requirements verified |

**FINAL RELEASE VERDICT: DO NOT RELEASE OR SUBMIT FOR SPONSOR PRIZES until REL-003 and REL-004 are fixed and re-tested, demo controls are disabled in the public deployment, and a deployed smoke check is recorded.**
