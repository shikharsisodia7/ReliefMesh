# QA test status

Audited branch: `origin/feat/reliefmesh-finish` at `f27fcdc`; QA work is isolated on `codex/qa-release`.

| Suite | Command | Result | Notes |
| --- | --- | --- | --- |
| Backend full suite | `backend/.venv/Scripts/python.exe -m pip install -r requirements.txt; python -m pytest -v` | PASS WITH EXPECTED FAILURES | 32 passed, 8 strict `xfail` after a clean dependency install; each `xfail` is a reproducible release defect described in `RELEASE_VERDICT.md`. |
| QA regressions | `backend/.venv/Scripts/python.exe -m pytest -v tests/test_release_qa.py` | PASS WITH EXPECTED FAILURES | 4 passed, 8 strict `xfail`. |
| Frontend unit | `cd frontend; npm test` | PASS | 1 passed. |
| Frontend lint | `cd frontend; npm run lint` | PASS | ESLint completed with no findings. |
| Frontend production build | `cd frontend; npm run build` | PASS | Next.js 16.4.3 production build completed. |
| Two-supplier browser workflow | `E2E_BASE_URL=http://127.0.0.1:3001 npx playwright test e2e/procurement-workflow.spec.ts` | PASS | Separate coordinator/two-supplier sessions; RFQ, quote, withdrawal, replan, approval, PO, acceptance, fulfillment. |
| Judge browser workflow | `E2E_BASE_URL=http://127.0.0.1:3001 npx playwright test e2e/judge-scenario.spec.ts` | PASS | Emergency context, evidence gates, disruption, replan, review, audit verification. |
| API collection syntax | `node -e "JSON.parse(require('fs').readFileSync('postman/reliefmesh.collection.json'))"` | PASS (prior baseline) | Local reusable collection parses. No shared Postman workspace was modified. |

Browser tests ran against an isolated local API (`RELIEFMESH_APP_ENV=test`, in-memory storage, test email gateway) and a separate Next development server. The judge test called live public sources; unit tests used explicit deterministic upstream doubles. No public deployment URL was provided, so no production smoke evidence exists.

## Requirement-ID regressions

`backend/tests/test_release_qa.py` contains strict expected-failure cases for:

- `requirement_id` with a changed human description;
- unknown ID;
- missing ID;
- duplicate mapping; and
- explicit legacy-name compatibility.

These are expected failures because the current persisted mission and quote schemas do not carry a stable requirement ID. They must become ordinary passing tests after the production fix; no submitted quote line may be silently skipped.
