import { ArrowDown, ArrowUpRight, CheckCircle2, CircleAlert, Clock3, LoaderCircle, ShieldCheck, Sparkles } from "lucide-react";
import { useState } from "react";

import { PlanStatusText, money, when } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { Approval, AuditVerification, Job, Mission, Plan, PurchaseOrder } from "@/lib/types";

type RecoveryExplanation = { draft: string; citations: string[]; model: string; plan_id: string; plan_version: number; human_review_required: boolean; notice: string };
const explanationSources: Record<string, { label: string; href: string }> = {
  mission_request: { label: "Mission request", href: "#mission-summary" },
  current_plan: { label: "Current plan", href: "#recovery-comparison" },
  plan_change: { label: "Plan comparison", href: "#recovery-comparison" },
  item_coverage: { label: "Aid coverage", href: "#recovery-impact" },
};

export function RecoveryImpactPanel({ mission, plans, approvals, jobs, orders, verification, loading, token, claudeEnabled }: {
  mission: Mission;
  plans: Plan[];
  approvals: Approval[];
  jobs: Job[];
  orders: PurchaseOrder[];
  verification?: AuditVerification;
  loading: boolean;
  token: string;
  claudeEnabled: boolean;
}) {
  const [explanation, setExplanation] = useState<RecoveryExplanation | null>(null);
  const [explanationError, setExplanationError] = useState<string | null>(null);
  const [explaining, setExplaining] = useState(false);
  const latest = [...plans].sort((a, b) => b.version - a.version)[0];
  const previous = latest?.difference.previous_plan_id ? plans.find((plan) => plan.id === latest.difference.previous_plan_id) : undefined;
  const replan = [...jobs].filter((job) => job.type === "replan").sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
  const replanActive = replan?.status === "queued" || replan?.status === "running";
  const staleOrders = orders.filter((order) => order.plan_stale && !["cancelled", "canceled", "closed"].includes(order.status.toLowerCase()));
  const approval = latest && approvals.find((item) => item.plan_id === latest.id && item.status === "active");
  const invalidated = previous && approvals.find((item) => item.plan_id === previous.id && item.status === "invalidated");
  const showCurrentNumbers = Boolean(latest && latest.status !== "stale" && !replanActive);
  const allocated = new Map<string, number>();
  if (showCurrentNumbers && latest) for (const row of latest.allocations) allocated.set(row.item.toLocaleLowerCase(), (allocated.get(row.item.toLocaleLowerCase()) ?? 0) + row.quantity);
  const changedSupplier = latest?.difference.supplier_delta?.find((entry) => entry.units_before !== entry.units_after);
  const headline = !latest ? "Build the first recovery plan" : replanActive ? "Rechecking the recovery plan" : latest.status === "infeasible" ? "Current supply cannot meet the mission" : latest.status === "stale" ? "Plan needs to be refreshed" : latest.status === "approved" ? "Recovery plan approved" : "Recovery plan ready for review";
  const reason = latest?.difference.why?.[0] ?? latest?.trigger_detail?.[0]?.summary ?? latest?.trigger ?? null;
  const costDelta = latest?.difference.cost_delta;
  const latestDelivery = showCurrentNumbers ? latest?.latest_delivery : null;
  const late = latestDelivery ? new Date(latestDelivery).getTime() > new Date(mission.delivery_deadline).getTime() : false;
  const exposurePending = !latest || latest.status === "stale" || replanActive;
  const onTime = new Map<string, number>();
  if (!exposurePending && latest && latest.status !== "infeasible") for (const row of latest.allocations) {
    if (new Date(row.delivery_date).getTime() <= new Date(mission.delivery_deadline).getTime()) {
      const key = row.item.toLocaleLowerCase();
      onTime.set(key, (onTime.get(key) ?? 0) + row.quantity);
    }
  }
  const atRisk = mission.requirements.map((requirement) => {
    const item = requirement.item.toLocaleLowerCase();
    const plannedByDeadline = onTime.get(item) ?? 0;
    return { ...requirement, plannedByDeadline, exposed: exposurePending || latest?.status === "infeasible" ? null : Math.max(0, requirement.quantity - plannedByDeadline) };
  });
  const riskUnits = atRisk.reduce((sum, row) => sum + (row.exposed ?? 0), 0);
  const explanationCurrent = explanation && explanation.plan_id === latest?.id;
  const generateExplanation = async () => {
    setExplaining(true); setExplanationError(null);
    try {
      setExplanation(await api<RecoveryExplanation>(`/v1/missions/${mission.id}/recovery-explanation`, { method: "POST", token }));
    } catch (error) {
      setExplanationError(error instanceof Error ? error.message : "Claude explanation is unavailable");
    } finally { setExplaining(false); }
  };

  return (
    <section id="recovery-impact" aria-label="Recovery brief" className="scroll-mt-28 overflow-hidden rounded-2xl border border-live/25 bg-[linear-gradient(115deg,rgba(8,28,43,.96),rgba(13,20,36,.96)_55%,rgba(24,27,48,.94))] shadow-[0_18px_60px_rgba(0,0,0,.18)]">
      <div className="grid gap-5 p-5 lg:grid-cols-[minmax(0,1.5fr)_minmax(280px,.8fr)] lg:p-6">
        <div>
          <div className="flex flex-wrap items-center gap-2 font-mono text-[10px] uppercase tracking-[.18em] text-live"><span className="size-1.5 rounded-full bg-live shadow-[0_0_12px_currentColor]" />Recovery brief{latest && <span className="text-tertiary">· plan v{latest.version}</span>}</div>
          {mission.community_label && <p className="mt-2 text-xs text-[#b8c5d9]">Community served · <span className="font-medium text-foreground">{mission.community_label}</span> <span className="text-tertiary">(coordinator-provided)</span></p>}
          <h2 className="mt-2 text-xl font-semibold tracking-tight sm:text-2xl">{headline}</h2>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            {latest && <PlanStatusText value={latest.status} />}
            {replanActive && <span className="inline-flex items-center gap-1.5 text-live"><LoaderCircle className="size-3.5 animate-spin" />Background replan {replan.status}</span>}
            {!latest && loading && <span className="inline-flex items-center gap-1.5"><LoaderCircle className="size-3.5 animate-spin" />Loading mission plan</span>}
            {!latest && !loading && <span>No plan has been generated yet.</span>}
          </div>
          {reason && <p className="mt-3 max-w-3xl text-sm leading-6 text-[#b8c5d9]">{reason}</p>}
          {replan?.status === "failed" && <p className="mt-3 flex items-start gap-2 rounded-lg border border-critical/35 bg-critical/10 p-3 text-sm text-critical"><CircleAlert className="mt-0.5 size-4 shrink-0" />Replanning failed{replan.last_error ? `: ${replan.last_error}` : ". Review the timeline for details."}</p>}
          {staleOrders.length > 0 && <p className="mt-3 flex items-start gap-2 rounded-lg border border-warn/35 bg-warn/10 p-3 text-sm text-warn"><CircleAlert className="mt-0.5 size-4 shrink-0" />{staleOrders.length} active purchase order{staleOrders.length === 1 ? " is" : "s are"} tied to an older plan and need review. They have not been canceled.</p>}
          {latest?.status === "infeasible" && latest.shortages.length > 0 && <ul className="mt-3 space-y-1 text-sm text-critical">{latest.shortages.map((row) => <li key={row.item}>{row.item}: short {row.shortage} of {row.required} required · {row.reason}</li>)}</ul>}
          <nav aria-label="Recovery brief details" className="mt-4 flex flex-wrap gap-x-4 gap-y-2 text-xs font-medium text-live">
            <a className="inline-flex items-center gap-1 hover:underline" href="#recovery-comparison">Compare plans <ArrowDown className="size-3" /></a>
            <a className="inline-flex items-center gap-1 hover:underline" href="#supplier-evidence">Supplier evidence <ArrowDown className="size-3" /></a>
            <a className="inline-flex items-center gap-1 hover:underline" href="#mission-timeline">Audit timeline <ArrowDown className="size-3" /></a>
            {changedSupplier && <a className="inline-flex items-center gap-1 hover:underline" href={`#supplier-${encodeURIComponent(changedSupplier.supplier_id)}`}>Changed supplier <ArrowUpRight className="size-3" /></a>}
          </nav>
        </div>

        <div className="grid grid-cols-2 gap-2 self-start">
          <div className="rounded-xl border border-white/10 bg-black/15 p-3"><p className="font-mono text-[10px] uppercase tracking-wider text-tertiary">Current plan cost</p><p className="mt-1 text-lg font-semibold text-telemetry">{showCurrentNumbers && latest ? money(latest.total_cost) : "—"}</p>{latest?.committed_cost && <p className="mt-1 text-[10px] text-tertiary">{money(latest.committed_cost)} committed on POs</p>}</div>
          <div className="rounded-xl border border-white/10 bg-black/15 p-3"><p className="font-mono text-[10px] uppercase tracking-wider text-tertiary">Cost change</p><p className={`mt-1 text-lg font-semibold ${costDelta?.startsWith("-") ? "text-ok" : "text-telemetry"}`}>{previous && costDelta ? `${costDelta.startsWith("-") ? "−" : "+"}${money(costDelta.replace(/^[+-]/, ""))}` : "—"}</p><p className="mt-1 text-[10px] text-tertiary">vs. plan v{previous?.version ?? "—"}</p></div>
          <div className="rounded-xl border border-white/10 bg-black/15 p-3"><p className="font-mono text-[10px] uppercase tracking-wider text-tertiary">Latest quoted arrival</p><p className={`mt-1 text-sm font-semibold ${late ? "text-critical" : "text-foreground"}`}>{latestDelivery ? when(latestDelivery) : "—"}</p><p className="mt-1 inline-flex items-center gap-1 text-[10px] text-tertiary"><Clock3 className="size-3" />Deadline {when(mission.delivery_deadline)}</p></div>
          <div className="rounded-xl border border-white/10 bg-black/15 p-3"><p className="font-mono text-[10px] uppercase tracking-wider text-tertiary">Approval</p><p className="mt-1 text-sm font-semibold">{approval ? <span className="inline-flex items-center gap-1 text-ok"><ShieldCheck className="size-3.5" />Approved</span> : latest?.status === "feasible" ? <span className="text-telemetry">Review required</span> : invalidated ? <span className="text-critical">Prior approval void</span> : <span className="text-muted-foreground">No active approval</span>}</p><p className="mt-1 text-[10px] text-tertiary">{approval ? `v${latest?.version} · ${money(approval.amount)}` : invalidated ? `v${previous?.version} approval invalidated` : latest?.status === "feasible" ? `Plan v${latest.version}` : "Human approval gate"}</p></div>
        </div>
      </div>

      {latest && showCurrentNumbers && latest.status !== "infeasible" && <div className="grid gap-3 border-t border-white/10 px-5 py-4 sm:grid-cols-[1fr_auto] sm:items-center lg:px-6">
        <div className="flex flex-wrap gap-x-5 gap-y-2">{mission.requirements.map((requirement) => {
          const quantity = allocated.get(requirement.item.toLocaleLowerCase()) ?? 0;
          const complete = quantity >= requirement.quantity;
          return <div key={requirement.id ?? requirement.item} className="flex items-center gap-2 text-xs"><span className={complete ? "text-ok" : "text-critical"}>{complete ? <CheckCircle2 className="size-3.5" /> : <CircleAlert className="size-3.5" />}</span><span className="text-muted-foreground">{requirement.item}</span><span className="font-mono">{quantity}/{requirement.quantity} planned</span></div>;
        })}</div>
        <span className="font-mono text-[10px] uppercase tracking-wider text-tertiary">Planned quantities · not delivered</span>
      </div>}
      <div className="border-t border-white/10 px-5 py-4 lg:px-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div><p className="font-mono text-[10px] uppercase tracking-[.16em] text-live">Aid at risk by the deadline</p><p className="mt-1 text-sm text-[#b8c5d9]">Item-level exposure from planned quantities and quoted arrival dates. This is not a count of people or proof of delivery.</p></div>
          <span className={`font-mono text-xs uppercase tracking-wider ${exposurePending || riskUnits > 0 ? "text-warn" : "text-ok"}`}>{exposurePending ? "Replan / plan needed" : `${riskUnits.toLocaleString()} units uncovered or late`}</span>
        </div>
        <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{atRisk.map((row) => <div key={row.id ?? row.item} className="rounded-lg border border-white/10 bg-black/15 p-3">
          <div className="flex items-center justify-between gap-2"><span className="text-sm font-medium">{row.item}</span><span className={`font-mono text-[10px] uppercase ${row.exposed === null ? "text-tertiary" : row.exposed > 0 ? "text-warn" : "text-ok"}`}>{row.exposed === null ? "Exposure unknown" : row.exposed > 0 ? `${row.exposed.toLocaleString()} at risk` : "Covered by deadline"}</span></div>
          <p className="mt-1 font-mono text-[11px] text-tertiary">{row.exposed === null ? `${row.quantity.toLocaleString()} requested · plan is not current` : `${row.plannedByDeadline.toLocaleString()} / ${row.quantity.toLocaleString()} planned by deadline`}</p>
        </div>)}</div>
      </div>
      <div className="border-t border-white/10 px-5 py-4 lg:px-6">
        <div className="flex flex-wrap items-center justify-between gap-3"><div><p className="font-mono text-[10px] uppercase tracking-[.16em] text-live">Claude recovery explanation</p><p className="mt-1 text-xs text-tertiary">Evidence-cited draft for a coordinator to review. It cannot change the plan or approval.</p></div>
          <Button size="sm" variant="secondary" disabled={!claudeEnabled || !mission.community_label || !latest || latest.status === "stale" || replanActive || explaining} onClick={() => void generateExplanation()}>{explaining ? <LoaderCircle className="size-3.5 animate-spin" /> : <Sparkles className="size-3.5" />}{explaining ? "Drafting…" : explanation ? "Draft again with Claude" : "Explain this plan with Claude"}</Button>
        </div>
        {!claudeEnabled && <p className="mt-2 text-xs text-tertiary">Claude is not configured on this API deployment.</p>}
        {claudeEnabled && !mission.community_label && <p className="mt-2 text-xs text-tertiary">Add a specific, substantiated community when creating the mission to use this explanation.</p>}
        {explanationError && <p role="alert" className="mt-3 rounded-md border border-warn/30 bg-warn/10 p-2 text-xs text-warn">{explanationError}</p>}
        {explanation && <div className="mt-3 rounded-lg border border-live/20 bg-live/[.04] p-3">
          <p className="text-sm leading-6 text-foreground">{explanation.draft}</p>
          <div className="mt-2 flex flex-wrap gap-2">{explanation.citations.map((citation) => { const source = explanationSources[citation]; return source ? <a key={citation} href={source.href} className="rounded border border-live/25 px-2 py-1 text-[10px] text-live hover:bg-live/10">{source.label} ↗</a> : null; })}</div>
          <p className="mt-2 text-[10px] text-tertiary">{explanationCurrent ? `Claude · ${explanation.model} · draft for plan v${explanation.plan_version}` : `Draft is for plan v${explanation.plan_version}; the current plan changed. Generate a new explanation.`} Review every cited record before sharing.</p>
        </div>}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-white/10 bg-black/10 px-5 py-2.5 text-[10px] text-tertiary lg:px-6">
        <span>{verification ? verification.valid ? <span className="inline-flex items-center gap-1 text-ok"><ShieldCheck className="size-3" />Audit chain verified · {verification.length} events</span> : <span className="text-critical">Audit chain issue · {verification.reason ?? `event ${verification.broken_at}`}</span> : "Audit verification loading"}</span>
        {latest && <a href="#recovery-comparison" className="font-mono uppercase tracking-wider text-live hover:underline">See full plan details <ArrowUpRight className="inline size-3" /></a>}
      </div>
    </section>
  );
}
