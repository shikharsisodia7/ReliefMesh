# Local performance smoke

Environment: isolated local FastAPI test deployment on `127.0.0.1:8001`, in-memory storage, no public deployment, sampled once on 2026-10-24. These are smoke measurements, not capacity benchmarks.

| Operation | Latency |
| --- | ---: |
| Health | 148 ms |
| Mission load | 17 ms |
| Quote submission | 18 ms |
| Evidence refresh request | 689 ms |
| Optimizer request | 60 ms |
| Audit retrieval | 17 ms |
| Demo seed request | 9 ms |
| Disruption enqueue | 49 ms |
| Replan job completion | <200 ms (first poll observed `succeeded`) |

No MongoDB Atlas, Render, Vercel, Resend, Apify, CRS, x402 facilitator, or Solana devnet production path was benchmarked. Re-run `scripts/qa/smoke.py` with a least-privilege test account after deployment, then collect an authenticated production trace before claiming production performance.
