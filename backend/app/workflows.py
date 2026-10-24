"""Workflows shared by supplier actions, judge disruptions, agents, and background jobs."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from .core import Services, audit, new_id, notify, now_iso, secret
from .evidence.service import collect_supplier_evidence
from .integrations import apify
from .jobs import enqueue
from .planning import compute_plan, evaluate_mission, invalidate_for_change


FAILURE_TYPES = {"withdrawn": "Supplier withdrew its quote", "updated": "Supplier revised its quote"}


async def apply_quote_change(services: Services, quote: dict[str, Any], mission: dict[str, Any],
                             actor_id: str | None, *, kind: str, summary: str,
                             updates: dict[str, Any] | None = None, withdraw: bool = False,
                             failure_type: str | None = None) -> tuple[dict, dict]:
    """Persist a quote revision/withdrawal, invalidate dependent plans, and queue a replan."""

    await services.store.insert("quote_versions", {
        "id": new_id(), "quote_id": quote["id"], "version": quote["version"], "snapshot": quote,
        "created_at": now_iso(),
    })
    if withdraw:
        quote["status"] = "withdrawn"
        quote["withdrawn_at"] = now_iso()
    else:
        quote.update(updates or {})
        quote["version"] += 1
    quote["updated_at"] = now_iso()
    await services.store.replace("quotes", quote["id"], quote)
    await notify(services, mission, f"quote_{kind}", summary, "warning",
                 {"quote_id": quote["id"], "supplier_id": quote["supplier_id"]})
    supplier = await services.store.get("suppliers", quote["supplier_id"])
    await invalidate_for_change(services, mission, actor_id, summary, cause={
        "supplier_id": quote["supplier_id"], "supplier": supplier_label(supplier, quote["supplier_email"]),
        "failure_type": failure_type or FAILURE_TYPES.get(kind, kind)})
    job = await enqueue(services, "replan", mission, trigger={
        "kind": kind, "quote_id": quote["id"], "supplier_id": quote["supplier_id"], "summary": summary,
        "at": now_iso(),
    })
    return quote, job


def supplier_label(supplier: dict[str, Any] | None, fallback: str) -> str:
    if not supplier:
        return fallback
    return supplier.get("legal_name") or supplier.get("email") or fallback


async def handle_replan(services: Services, job: dict[str, Any]) -> dict[str, Any]:
    mission = await services.store.get("missions", job["mission_id"])
    if not mission:
        raise RuntimeError("mission no longer exists")
    if mission.get("status") == "cancelled":
        return {"status": "skipped", "reason": "mission cancelled"}
    triggers = job.get("triggers") or []
    await notify(services, mission, "replan_started",
                 f"Replanning started after {len(triggers) or 1} change(s).", "info", {"job_id": job["id"]})
    kind = triggers[0]["kind"] if triggers else "supplier_disruption"
    trigger = "policy_change" if kind == "policy_change" else "supplier_disruption"
    plan = await compute_plan(services, mission["id"], trigger, triggers)
    delta = plan["difference"].get("cost_delta")
    if plan["status"] == "feasible":
        message = f"Plan v{plan['version']} was computed after a supplier disruption: total ${plan['total_cost']}" + (
            f" ({delta} vs prior plan)." if delta else ".") + " A new human approval is required."
        await notify(services, mission, "plan_replanned", message, "success",
                     {"plan_id": plan["id"], "version": plan["version"], "cost_delta": delta})
    else:
        await notify(services, mission, "plan_replanned",
                     f"Plan v{plan['version']} is infeasible after the disruption; see shortages.", "critical",
                     {"plan_id": plan["id"], "version": plan["version"]})
    return {"plan_id": plan["id"], "version": plan["version"], "status": plan["status"]}


async def refresh_supplier_evidence(services: Services, mission: dict[str, Any], supplier_ids: list[str],
                                    actor_id: str | None) -> dict[str, Any]:
    from .integrations.crs import crs_checker  # local import: CRS is optional

    before_plan = await latest_plan(services, mission["id"])
    checked = []
    for supplier_id in supplier_ids:
        supplier = await services.store.get("suppliers", supplier_id)
        if not supplier:
            continue
        records = await collect_supplier_evidence(
            services.store, services.hub, services.settings, organization_id=mission["organization_id"],
            supplier=supplier, mission_id=mission["id"], crs_check=crs_checker(services),
        )
        checked.append({"supplier_id": supplier_id, "records": len(records)})
        await audit("evidence.collected", actor_id, mission["organization_id"], mission["id"], "supplier",
                    supplier_id, services, {
                        "evidence": [{"id": r["id"], "type": r["type"], "status": r["status"],
                                      "provenance": r["provenance"]} for r in records],
                    })
    report, _ = await evaluate_mission(services, mission)
    changes = []
    if before_plan and before_plan["status"] in {"feasible", "approved"}:
        old = {sid: row["status"] for sid, row in before_plan["policy"]["suppliers"].items()}
        for sid, row in report["suppliers"].items():
            if sid in old and old[sid] != row["status"]:
                changes.append({"supplier_id": sid, "before": old[sid], "after": row["status"]})
        if changes or report["fingerprint"] != before_plan["policy"]["fingerprint"]:
            names = {sid: row.get("legal_name") or row.get("email") for sid, row in report["suppliers"].items()}
            summary = "; ".join(f"{names[c['supplier_id']]} policy {c['before']} -> {c['after']}" for c in changes) \
                or "Supplier evidence changed the policy inputs"
            await invalidate_for_change(services, mission, actor_id, summary)
            await enqueue(services, "replan", mission, trigger={"kind": "policy_change", "summary": summary,
                                                               "at": now_iso()})
    return {"checked": checked, "policy_changes": changes, "fingerprint": report["fingerprint"]}


async def handle_evidence_refresh(services: Services, job: dict[str, Any]) -> dict[str, Any]:
    mission = await services.store.get("missions", job["mission_id"])
    if not mission:
        raise RuntimeError("mission no longer exists")
    supplier_ids = set(job.get("payload", {}).get("supplier_ids") or [])
    supplier_ids |= {t["supplier_id"] for t in job.get("triggers") or [] if t.get("supplier_id")}
    if not supplier_ids:
        supplier_ids = {q["supplier_id"] for q in await services.store.find("quotes", mission_id=mission["id"])}
    result = await refresh_supplier_evidence(services, mission, sorted(supplier_ids), job.get("payload", {}).get("actor_id"))
    await notify(services, mission, "evidence_refreshed",
                 f"Evidence checks completed for {len(result['checked'])} supplier(s).", "info",
                 {"job_id": job["id"], "policy_changes": result["policy_changes"]})
    return result


async def handle_supplier_discovery(services: Services, job: dict[str, Any]) -> dict[str, Any]:
    mission = await services.store.get("missions", job["mission_id"])
    if not mission:
        raise RuntimeError("mission no longer exists")
    payload = job["payload"]
    token = secret(services.settings.apify_api_token)
    actor = services.settings.apify_discovery_actor
    run = await apify.start_discovery(services.hub, token, actor, query=payload["query"],
                                      location=payload.get("location"), max_places=payload.get("max_results", 8))
    if run.status == "BLOCKED_EXTERNAL":
        return {"status": "BLOCKED_EXTERNAL", "error": run.error, "leads": 0}
    if not run.ok:
        raise RuntimeError(run.error or "Apify run could not start")
    run_id, dataset_id = run.data["run_id"], run.data["dataset_id"]
    job["payload"].update(run_id=run_id, dataset_id=dataset_id)
    await services.store.replace("jobs", job["id"], job)
    status = run.data["status"]
    for _ in range(6):  # up to ~6 minutes of server-side waiting
        if status in {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}:
            break
        waited = await apify.wait_for_run(services.hub, token, run_id, wait_seconds=60)
        if not waited.ok:
            raise RuntimeError(waited.error or "Apify run status unavailable")
        status = waited.data["status"]
    if status != "SUCCEEDED":
        raise RuntimeError(f"Apify run {run_id} ended with status {status}")
    items = await apify.dataset_leads(services.hub, token, dataset_id, limit=payload.get("max_results", 8))
    if not items.ok:
        raise RuntimeError(items.error or "Apify dataset unavailable")
    existing = {(lead.get("place_id") or lead["name"]) for lead in
                await services.store.find("supplier_leads", mission_id=mission["id"])}
    created = 0
    for lead in items.data:
        key = lead.get("place_id") or lead["name"]
        if key in existing:
            continue
        existing.add(key)
        await services.store.insert("supplier_leads", {
            "id": new_id(),
            "organization_id": mission["organization_id"],
            "mission_id": mission["id"],
            **lead,
            "query": payload["query"],
            "status": "lead",
            "provenance": items.provenance,
            "retrieved_at": items.retrieved_at,
            "apify_run_id": run_id,
            "apify_dataset_id": dataset_id,
            "apify_actor": actor,
            "created_at": now_iso(),
            # A lead is public listing data only: no inventory, price, or delivery commitment.
            "binding_terms": None,
        })
        created += 1
    await audit("supplier_discovery.completed", payload.get("actor_id"), mission["organization_id"], mission["id"],
                "job", job["id"], services, {"run_id": run_id, "dataset_id": dataset_id, "leads": created})
    await notify(services, mission, "discovery_completed",
                 f"Apify discovery found {created} new supplier lead(s) for '{payload['query']}'.", "info",
                 {"run_id": run_id, "dataset_id": dataset_id})
    return {"status": "SUCCEEDED", "run_id": run_id, "dataset_id": dataset_id, "leads": created}


async def latest_plan(services: Services, mission_id: str) -> dict[str, Any] | None:
    plans = await services.store.find("plans", mission_id=mission_id)
    return max(plans, key=lambda plan: plan["version"]) if plans else None


def register_handlers(services: Services) -> None:
    services.job_handlers.update({
        "replan": handle_replan,
        "evidence_refresh": handle_evidence_refresh,
        "supplier_discovery": handle_supplier_discovery,
    })


def money(value: Decimal | str) -> str:
    return f"{Decimal(str(value)):.2f}"
