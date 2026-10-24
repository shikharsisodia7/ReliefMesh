"""Durable background jobs: replanning, evidence refresh, supplier discovery.

Jobs live in the `jobs` collection with attempts, max attempts, last error, and retry
timestamps. Queued replans for the same mission coalesce so a burst of disruptions
produces one new plan version. On startup, queued jobs resume and jobs stuck in
`running` past `stuck_job_seconds` are requeued.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from .core import Services, audit, new_id, notify, now_iso


async def enqueue(services: Services, job_type: str, mission: dict[str, Any], *, trigger: dict[str, Any] | None = None,
                  payload: dict[str, Any] | None = None, coalesce: bool = True) -> dict[str, Any]:
    if coalesce:
        for job in await services.store.find("jobs", mission_id=mission["id"], type=job_type, status="queued"):
            if trigger:
                job.setdefault("triggers", []).append(trigger)
                job["updated_at"] = now_iso()
                await services.store.replace("jobs", job["id"], job)
            return job
    job = {
        "id": new_id(),
        "type": job_type,
        "mission_id": mission["id"],
        "organization_id": mission["organization_id"],
        "status": "queued",
        "attempts": 0,
        "max_attempts": services.settings.job_max_attempts,
        "triggers": [trigger] if trigger else [],
        "payload": payload or {},
        "last_error": None,
        "next_retry_at": None,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    # Kept for clients of the original replan API.
    if trigger and trigger.get("quote_id"):
        job["quote_id"] = trigger["quote_id"]
    await services.store.insert("jobs", job)
    services.schedule(run_job(services, job["id"]))
    return job


async def run_job(services: Services, job_id: str) -> None:
    job = await services.store.get("jobs", job_id)
    if not job or job["status"] != "queued":
        return
    job.update(status="running", attempts=job.get("attempts", 0) + 1, started_at=now_iso(), updated_at=now_iso())
    await services.store.replace("jobs", job_id, job)
    handler = services.job_handlers.get(job["type"])
    try:
        if handler is None:
            raise RuntimeError(f"no handler registered for job type {job['type']}")
        result = await handler(services, job)
        job.update(status="succeeded", result=result, finished_at=now_iso(), updated_at=now_iso(), last_error=None)
        if result and result.get("plan_id"):
            job["plan_id"] = result["plan_id"]
        await services.store.replace("jobs", job_id, job)
    except Exception as exc:  # keep a durable, visible failure record and retry with backoff
        job["last_error"] = f"{type(exc).__name__}: {exc}"
        job["updated_at"] = now_iso()
        mission = await services.store.get("missions", job["mission_id"])
        if job["attempts"] < job.get("max_attempts", 3):
            delay = 2 ** job["attempts"]
            job.update(status="queued", next_retry_at=(datetime.now(UTC) + timedelta(seconds=delay)).isoformat())
            await services.store.replace("jobs", job_id, job)
            services.schedule(run_job(services, job_id), delay=delay)
        else:
            job.update(status="failed", error=job["last_error"], finished_at=now_iso())
            await services.store.replace("jobs", job_id, job)
            if mission:
                await notify(services, mission, f"{job['type']}_failed",
                             f"{job['type'].replace('_', ' ').title()} failed after {job['attempts']} attempts: "
                             f"{job['last_error']}", "critical", {"job_id": job_id})
                await audit("job.failed", None, mission["organization_id"], mission["id"], "job", job_id, services,
                            {"type": job["type"], "error": job["last_error"]})


async def recover_jobs(services: Services) -> None:
    for job in await services.store.find("jobs", status="queued"):
        services.schedule(run_job(services, job["id"]))
    cutoff = datetime.now(UTC) - timedelta(seconds=services.settings.stuck_job_seconds)
    for job in await services.store.find("jobs", status="running"):
        started = job.get("started_at")
        if started and datetime.fromisoformat(started) < cutoff:
            job.update(status="queued", last_error="recovered a job stuck in running state at startup",
                       updated_at=now_iso())
            await services.store.replace("jobs", job["id"], job)
            services.schedule(run_job(services, job["id"]))
