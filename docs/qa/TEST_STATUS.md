# QA test status

Audited branch: `origin/feat/reliefmesh-finish` at `643a4c1`; QA work is isolated on `codex/qa-release`.

| Suite | Command | Result | Notes |
| --- | --- | --- | --- |
| Backend full suite | `backend/.venv/Scripts/python.exe -m pytest -ra` | PASS WITH EXPECTED FAILURES | 43 passed, 2 strict `xfail`; each remaining `xfail` is a reproducible release defect described in `RELEASE_VERDICT.md`. |
| QA regressions | `backend/.venv/Scripts/python.exe -m pytest -v -rxX tests/test_release_qa.py` | PASS WITH EXPECTED FAILURES | 12 passed, 2 strict `xfail`. |
| Frontend unit | `cd frontend; npm test` | PASS | 1 passed. |
| Frontend lint | `cd frontend; npm run lint` | PASS | ESLint completed with no findings. |
| Frontend production build | `cd frontend; npm run build` | PASS | Next.js 16.4.3 production build completed. |
| Two-supplier browser workflow | `E2E_BASE_URL=http://127.0.0.1:3002 npx playwright test e2e/procurement-workflow.spec.ts` | PASS | Separate requester, independent approver, and two supplier sessions; RFQ, quote, withdrawal, replan, approval, PO, acceptance, fulfillment. |
| Judge browser workflow | `E2E_BASE_URL=http://127.0.0.1:3002 npx playwright test e2e/judge-scenario.spec.ts` | PASS | Emergency context, evidence gates, disruption, replan, review, audit verification. |
| API collection syntax | `node -e "JSON.parse(require('fs').readFileSync('postman/reliefmesh.collection.json'))"` | PASS (prior baseline) | Local reusable collection parses. No shared Postman workspace was modified. |

Browser tests ran against an isolated local API (`RELIEFMESH_APP_ENV=test`, in-memory storage, test email gateway) and a separately built Next server on port 3002. The judge test called live public sources; unit tests used explicit deterministic upstream doubles. No public deployment URL was provided, so no production smoke evidence exists.

## Requirement-ID regressions

`backend/tests/test_release_qa.py` contains passing regression checks for:

- `requirement_id` with a changed human description;
- unknown ID;
- missing ID;
- duplicate mapping; and
- exact-name legacy compatibility;
- real-organization self-approval denial and independent-approver success; and
- one-time organization invitation acceptance.

The two strict expected failures deliberately remain for the direct agent-plan tenant leak (REL-003) and replayable supplier-RFQ acceptance (REL-004). They are release blockers, not passing controls.
