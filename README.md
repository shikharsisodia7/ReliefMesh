# ReliefMesh

ReliefMesh is an emergency-procurement workflow: organizations source supplier quotes, solve an auditable purchasing allocation, invalidate stale approvals after supplier disruption, and issue confirmed purchase orders.

## Local product run

Use MongoDB for a persistent local product run:

```powershell
docker compose up --build
cd frontend
Copy-Item .env.example .env.local
npm install
npm run dev
```

Set `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` in `frontend/.env.local`. Copy `backend/.env.example` to `backend/.env` and supply Atlas + Resend values for a production-equivalent run.

## Verification

```powershell
cd backend; .\.venv\Scripts\python.exe -m pytest
cd frontend; npm test; npm run lint; npm run build; npm run test:e2e
```

The browser test uses separate coordinator and supplier browser contexts and verifies quote withdrawal, autonomous replanning, approval invalidation, purchase-order confirmation, and supplier acceptance.
