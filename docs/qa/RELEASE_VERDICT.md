# Release verdict

Audited implementation commit: `f27fcdc` (`origin/feat/reliefmesh-finish`). QA changes are isolated on `codex/qa-release`.

## Blocking defects

1. **REL-001 — quote lines can be silently dropped (critical).**
   - Reproduction: submit or persist a line whose human-readable `item` differs from the mission text. `backend/app/optimizer.py:solve()` executes `if line["item"] not in requirements: continue`; `backend/app/policy/engine.py:quote_decisions()` repeats the same name match.
   - Expected: mission requirements receive immutable IDs; RFQ/quote lines reference them; unknown, missing, and duplicate IDs return specific validation errors; legacy mappings are explicitly marked.
   - Actual: no requirement ID exists in `backend/app/schemas.py` for mission or quote lines; unmatched lines are ignored and eventually look like an infeasible/delivery problem.
   - Required fix: generate and persist `requirement_id` on mission creation, expose it in RFQs, require it for new quotes, validate every line before policy/optimization, carry it into allocations, and implement a labeled exact-name legacy migration path.

2. **REL-002 — mission creators can self-approve (critical financial-control failure).**
   - Reproduction: any organization admin creates a mission, optimizes, then `POST /v1/plans/{id}/approve` using that same user. Existing workflow tests demonstrate the current 201 response.
   - Expected: `403` with an explicit separation-of-duties message, except for a separately labeled synthetic/demo override.
   - Actual: `backend/app/routes/procurement.py:approve_plan()` checks admin membership but never compares `user["id"]` with `mission["created_by"]`.
   - Required fix: deny self-approval for real missions; add a distinct, audited demo-only override if judges need one; test a second-admin approval as the allowed path.

3. **REL-003 — cross-conversation Fetch agent plan leak (critical tenant-isolation failure).**
   - Reproduction: create an agent mission with `X-Agent-Sender: conversation-a`, optimize it, then use the same organization agent token with `X-Agent-Sender: conversation-b` on `GET /v1/plans/{plan_id}`. It returns the plan.
   - Expected: `403` because the plan's mission belongs to another sender.
   - Actual: `backend/app/routes/procurement.py:get_plan()` calls `require_org_member()` only. Other mission-scoped endpoints use `require_mission_access()` and enforce sender isolation.
   - Required fix: load the plan's mission and use `require_mission_access()` (or an equivalent sender-aware helper) for direct plan reads; audit every direct mission-derived object endpoint the same way.

## High-risk defects

- **REL-004 — invitation acceptance is replayable.** `invitation_from_token()` checks existence and expiry but not consumed/accepted status; the same matching supplier can accept repeatedly. Make acceptance a one-time state transition or explicitly document an idempotent endpoint with a stable prior response.
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
| APPROVAL CONTROLS | FAIL (REL-002) |
| OPTIMIZER | FAIL (REL-001) |
| POLICY | PASS (local deterministic and adversarial tests) |
| AUDIT CHAIN | PASS — tamper-evident, not immutable |
| PAYMENT IDEMPOTENCY | PASS (local unit tests only) |
| SECRET SCAN | PASS (current tree and reachable history; scanner limitation documented) |
| PUBLIC REPO SAFETY | PASS (no committed real secrets found) |
| DEPLOYMENT | NOT AVAILABLE |
| SPONSOR CLAIMS VERIFIED | 0/17 live track requirements verified |

**FINAL RELEASE VERDICT: DO NOT RELEASE OR SUBMIT FOR SPONSOR PRIZES until REL-001, REL-002, and REL-003 are fixed and re-tested.**
