"use client";

import { AlertTriangle, GitCompareArrows, Network, RefreshCw, ShieldCheck, ShieldX } from "lucide-react";

import { Provenance, money, when } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import type { ContinuityAnalysis, ContinuityView, Plan } from "@/lib/types";

function percent(value: number) {
  return `${Math.round(value * 100)}%`;
}

function delta(value: string | null) {
  if (!value) return "—";
  const numeric = Number(value);
  return `${numeric > 0 ? "+" : ""}${money(value)}`;
}

function Metric({ label, value, note }: { label: string; value: string; note?: string }) {
  return <div className="rounded-lg border border-border/80 bg-background/40 p-2.5">
    <dt className="text-[10px] font-medium uppercase tracking-[0.12em] text-muted-foreground">{label}</dt>
    <dd className="mt-1 font-mono text-base text-foreground">{value}</dd>
    {note && <p className="mt-0.5 text-[10px] text-tertiary">{note}</p>}
  </div>;
}

function DigitalTwin({ analysis, view }: { analysis: ContinuityAnalysis; view: ContinuityView }) {
  const suppliers = analysis.baseline.supplier_concentration;
  const approvalCount = view.digital_twin.nodes.filter((node) => node.type === "approval").length;
  const purchaseOrderCount = view.digital_twin.nodes.filter((node) => node.type === "purchase_order").length;
  return <section className="rounded-lg border border-border/80 bg-background/35 p-3" aria-label="Procurement Digital Twin">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div><h3 className="flex items-center gap-1.5 text-sm font-semibold"><Network className="size-4 text-telemetry" />Procurement Digital Twin</h3>
        <p className="mt-0.5 text-[11px] text-tertiary">Persisted mission → quote → plan → approval → PO state. Supplier lanes below show where this plan can break.</p></div>
      <span className="rounded border px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">{view.digital_twin.provenance}</span>
    </div>
    <div className="mt-3 grid gap-2 md:grid-cols-[minmax(0,1fr)_auto]">
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2 font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
          <span className="rounded bg-live/10 px-1.5 py-1 text-live">Mission</span><span>→</span><span>Requirements</span><span>→</span><span>Policy-eligible supplier allocations</span><span>→</span><span>Plan v{analysis.plan_version}</span>
        </div>
        {suppliers.map((supplier) => {
          const scenario = analysis.n1_scenarios.find((row) => row.supplier_id === supplier.supplier_id);
          const unsafe = scenario && !scenario.feasible;
          return <div key={supplier.supplier_id} className={`rounded border p-2 ${unsafe ? "border-critical/50 bg-critical/5" : "border-border/80"}`}>
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs"><span className="font-medium">{supplier.supplier}</span>
              <span className={`font-mono text-[10px] ${unsafe ? "text-critical" : "text-ok"}`}>{unsafe ? "CRITICAL · loss is infeasible" : "RECOVERABLE"}</span></div>
            <div className="mt-1.5 h-2 overflow-hidden rounded bg-muted"><div className={unsafe ? "h-full bg-critical" : "h-full bg-telemetry"} style={{ width: `${Math.max(3, supplier.unit_share * 100)}%` }} /></div>
            <p className="mt-1 font-mono text-[10px] text-tertiary">{supplier.units} units · {percent(supplier.unit_share)} concentration{scenario?.feasible && scenario.cost_delta ? ` · recovery ${delta(scenario.cost_delta)}` : ""}</p>
          </div>;
        })}
      </div>
      <div className="grid content-start grid-cols-2 gap-2 text-center text-[10px] md:grid-cols-1">
        <div className="rounded border p-2"><p className="text-muted-foreground">Approvals</p><p className="font-mono text-base">{approvalCount}</p></div>
        <div className="rounded border p-2"><p className="text-muted-foreground">POs</p><p className="font-mono text-base">{purchaseOrderCount}</p></div>
      </div>
    </div>
  </section>;
}

function Scenarios({ analysis }: { analysis: ContinuityAnalysis }) {
  return <section className="rounded-lg border border-border/80 p-3" aria-label="N-1 survivability">
    <div className="flex items-center justify-between gap-2"><h3 className="text-sm font-semibold">N-1 survivability</h3><span className="font-mono text-xs text-telemetry">{analysis.metrics.n1_survivability.survives}/{analysis.metrics.n1_survivability.tested} recoverable</span></div>
    <p className="mt-1 text-[11px] text-tertiary">Each row removes one allocated supplier, reruns deterministic policy-gated optimization, and leaves persisted supplier state untouched.</p>
    <div className="mt-2 space-y-2">
      {analysis.n1_scenarios.map((scenario) => <article key={scenario.supplier_id} className={`rounded border p-2 ${scenario.feasible ? "border-ok/30" : "border-critical/40 bg-critical/5"}`}>
        <div className="flex flex-wrap items-center justify-between gap-2"><span className="text-sm font-medium">Stress test: {scenario.supplier} unavailable</span>
          <span className={`font-mono text-[10px] ${scenario.feasible ? "text-ok" : "text-critical"}`}>{scenario.status}</span></div>
        {scenario.feasible ? <p className="mt-1 text-xs text-muted-foreground">Recovery {money(scenario.new_cost ?? "0")} · {delta(scenario.cost_delta)} · {scenario.deadline_delta_hours === 0 ? "same deadline" : `${scenario.deadline_delta_hours ?? 0}h delivery shift`} {scenario.replacement_suppliers.length > 0 && `· via ${scenario.replacement_suppliers.join(", ")}`}</p>
          : <p className="mt-1 text-xs text-critical">{scenario.lost_quantity} units uncovered{scenario.shortages.length > 0 ? ` · ${scenario.shortages.map((row) => `${row.item}: ${row.shortage} (${row.reason})`).join(", ")}` : ""}</p>}
      </article>)}
    </div>
  </section>;
}

function FailureFrontier({ analysis }: { analysis: ContinuityAnalysis }) {
  return <section className="rounded-lg border border-border/80 p-3" aria-label="Failure frontier">
    <h3 className="text-sm font-semibold">Failure frontier</h3>
    <p className="mt-1 text-[11px] text-tertiary">Smallest monotonic shock that makes the current quote snapshot infeasible. These are mathematical counterfactuals, not actual supplier failures.</p>
    <div className="mt-2 space-y-2">
      {analysis.failure_frontier.map((frontier) => <div key={frontier.supplier_id} className="rounded border border-border/70 p-2 text-xs">
        <p className="font-medium">{frontier.supplier}</p>
        {frontier.note ? <p className="mt-1 text-muted-foreground">{frontier.note}</p> : <div className="mt-1 grid gap-1 sm:grid-cols-3">
          <span>Price: <b className="font-mono">{frontier.price ? `+${frontier.price.increase_percent}%` : "—"}</b></span>
          <span>ETA: <b className="font-mono">{frontier.delay ? `+${frontier.delay.hours}h` : "—"}</b></span>
          <span>Capacity: <b className="font-mono">{frontier.capacity ? `${frontier.capacity.loss_units} units` : "—"}</b></span>
        </div>}
      </div>)}
    </div>
  </section>;
}

export function ContinuityPanel({ plan, view, running, onRun }: { plan?: Plan; view?: ContinuityView; running: boolean; onRun: () => void }) {
  const analysis = view?.analysis;
  const state = view?.state ?? "NOT_READY";
  const canRun = Boolean(plan && (plan.status === "feasible" || plan.status === "approved"));
  return <section aria-label="Continuity Engine" className="rounded-xl border border-telemetry/30 bg-card p-4 shadow-[0_0_32px_-22px_var(--color-telemetry)]">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><div className="flex items-center gap-2"><h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-muted-foreground">Continuity Engine</h2><Provenance value="HYPOTHETICAL" /></div>
        <p className="mt-1 max-w-3xl text-sm">Will this plan survive reality? ReliefMesh stress-tests the exact plan inputs before a real supplier change forces recovery.</p></div>
      <Button size="sm" onClick={onRun} disabled={!canRun || running}><RefreshCw className={`size-3.5 ${running ? "animate-spin" : ""}`} />Find resilient alternative</Button>
    </div>
    {!plan && <p className="mt-3 rounded border border-border/80 p-3 text-sm text-muted-foreground">Create a feasible plan first. Continuity analysis is automatically queued for every feasible plan.</p>}
    {plan && state === "RUNNING" && <p className="mt-3 flex items-center gap-2 rounded border border-telemetry/40 bg-telemetry/5 p-3 text-sm text-telemetry"><RefreshCw className="size-4 animate-spin" />Continuity analysis running… deterministic N-1 scenarios are executing in the background.</p>}
    {plan && state === "NOT_READY" && <p className="mt-3 rounded border border-border/80 p-3 text-sm text-muted-foreground">Continuity analysis is queued automatically after optimization. You can also start a fresh current-snapshot run.</p>}
    {state === "STALE" && analysis && <p className="mt-3 flex gap-2 rounded border border-warn/40 bg-warn/5 p-3 text-sm text-warn"><AlertTriangle className="mt-0.5 size-4 shrink-0" />This is a historical HYPOTHETICAL result for Plan v{analysis.plan_version}; quote, evidence, policy, or plan inputs changed. It is not shown as current.</p>}
    {analysis && <div className="mt-4 space-y-4">
      <p className="rounded border border-violet-400/30 bg-violet-400/5 p-2 text-[11px] text-violet-200">{analysis.counterfactual_label} Input hash {analysis.input_hash.slice(0, 12)} · analyzed {when(analysis.created_at)}</p>
      {analysis.scope && analysis.scope.kind !== "FULL_MISSION" && <p className="rounded border border-warn/30 bg-warn/5 p-2 text-[11px] text-warn">Scope: {analysis.scope.statement} Fixed commitments: {money(analysis.scope.fixed_commitment_cost)} across {analysis.scope.fixed_commitment_count} PO line{analysis.scope.fixed_commitment_count === 1 ? "" : "s"}.</p>}
      <dl className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="N-1 survivability" value={`${analysis.metrics.n1_survivability.survives}/${analysis.metrics.n1_survivability.tested}`} note="allocated suppliers" />
        <Metric label="Budget headroom" value={money(analysis.metrics.budget_headroom)} />
        <Metric label="Deadline slack" value={analysis.metrics.deadline_slack_hours === null ? "—" : `${analysis.metrics.deadline_slack_hours}h`} />
        <Metric label="Largest concentration" value={percent(analysis.metrics.largest_supplier_concentration)} note={analysis.metrics.critical_supplier?.supplier ?? "no critical supplier"} />
      </dl>
      <DigitalTwin analysis={analysis} view={view!} />
      <div className="grid gap-4 xl:grid-cols-2"><Scenarios analysis={analysis} /><FailureFrontier analysis={analysis} /></div>
      <section className="rounded-lg border border-telemetry/40 bg-telemetry/5 p-3" aria-label="Cost vs resilience">
        <div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="flex items-center gap-1.5 text-sm font-semibold"><GitCompareArrows className="size-4 text-telemetry" />Cheapest vs resilient</h3>
          <p className="mt-1 text-[11px] text-tertiary">The resilient alternative is a separate MILP with a ≤50% supplier-concentration guardrail. It is a proposal only—human approval remains required.</p></div>
          {analysis.resilient_alternative.status === "AVAILABLE" ? <span className="font-mono text-lg text-telemetry">{money(analysis.resilient_alternative.added_cost ?? "0")}</span> : <ShieldX className="size-5 text-warn" />}</div>
        {analysis.resilient_alternative.status === "AVAILABLE" ? <div className="mt-2 grid gap-2 sm:grid-cols-3 text-xs"><div className="rounded border border-border/70 bg-card p-2"><p className="text-muted-foreground">Cheapest</p><p className="font-mono text-base">{money(analysis.baseline.total_cost)}</p></div><div className="rounded border border-telemetry/40 bg-card p-2"><p className="text-muted-foreground">Resilient</p><p className="font-mono text-base">{money(analysis.resilient_alternative.total_cost ?? "0")}</p></div><div className="rounded border border-border/70 bg-card p-2"><p className="text-muted-foreground">N-1 under guardrail</p><p className="font-mono text-base">{analysis.resilient_alternative.n1_survivability?.survives}/{analysis.resilient_alternative.n1_survivability?.tested}</p></div></div>
          : <p className="mt-2 text-sm text-warn">{analysis.resilient_alternative.reason}</p>}
      </section>
      <p className="flex items-center gap-1.5 text-[11px] text-tertiary"><ShieldCheck className="size-3.5 text-ok" />Policy and approval are unchanged; deterministic optimization calculated these scenarios. AI does not decide eligibility, constraints, approval, or payment.</p>
    </div>}
  </section>;
}
