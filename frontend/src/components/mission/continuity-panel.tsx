"use client";

import { RefreshCw } from "lucide-react";
import type { ReactNode } from "react";

import { Provenance, StatusText, money, signedAmount, when } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import type { ContinuityAnalysis, ContinuityView, Plan } from "@/lib/types";

function percent(value: number) {
  return `${Math.round(value * 100)}%`;
}

function delta(value: string | null) {
  return value ? signedAmount(value) : "—";
}

function Subsection({ label, title, note, children }: { label: string; title: ReactNode; note?: string; children: ReactNode }) {
  return (
    <section aria-label={label} className="mt-8">
      <h4 className="text-sm font-semibold">{title}</h4>
      {note && <p className="mt-1 max-w-2xl text-xs text-muted-foreground">{note}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}

const head = "py-2 text-left text-xs font-medium text-muted-foreground";
const cell = "py-2.5 align-top";

function DigitalTwin({ analysis, view }: { analysis: ContinuityAnalysis; view: ContinuityView }) {
  const approvalCount = view.digital_twin.nodes.filter((node) => node.type === "approval").length;
  const purchaseOrderCount = view.digital_twin.nodes.filter((node) => node.type === "purchase_order").length;
  return (
    <Subsection label="Procurement Digital Twin" title={<>Procurement Digital Twin <Provenance className="ml-2" value={view.digital_twin.provenance} /></>}
      note={`Persisted mission → requirements → policy-eligible allocations → plan v${analysis.plan_version}. ${approvalCount} approval${approvalCount === 1 ? "" : "s"} and ${purchaseOrderCount} purchase order${purchaseOrderCount === 1 ? "" : "s"} recorded. The rows show where this plan can break.`}>
      <table className="w-full text-sm">
        <thead><tr className="border-b"><th className={head}>Supplier</th><th className={`${head} text-right`}>Units</th><th className={`${head} text-right`}>Concentration</th><th className={`${head} text-right`}>If this supplier is lost</th></tr></thead>
        <tbody>
          {analysis.baseline.supplier_concentration.map((supplier) => {
            const scenario = analysis.n1_scenarios.find((row) => row.supplier_id === supplier.supplier_id);
            const unsafe = scenario && !scenario.feasible;
            return (
              <tr key={supplier.supplier_id} className="border-b">
                <td className={cell}>{supplier.supplier}</td>
                <td className={`${cell} text-right tabular`}>{supplier.units}</td>
                <td className={`${cell} text-right tabular`}>{percent(supplier.unit_share)}</td>
                <td className={`${cell} text-right`}>{unsafe ? <StatusText tone="warn">Critical · loss is infeasible</StatusText> : <>Recoverable{scenario?.feasible && scenario.cost_delta ? <span className="text-muted-foreground"> · {delta(scenario.cost_delta)}</span> : ""}</>}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Subsection>
  );
}

function Scenarios({ analysis }: { analysis: ContinuityAnalysis }) {
  return (
    <Subsection label="N-1 survivability" title={<>N-1 survivability <span className="ml-2 font-normal text-muted-foreground tabular">{analysis.metrics.n1_survivability.survives}/{analysis.metrics.n1_survivability.tested} recoverable</span></>}
      note="Each row removes one allocated supplier, reruns deterministic policy-gated optimization, and leaves persisted supplier state untouched.">
      <ul>
        {analysis.n1_scenarios.map((scenario) => (
          <li key={scenario.supplier_id} className="border-b py-2.5 text-sm">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span>Stress test: {scenario.supplier} unavailable</span>
              <StatusText value={scenario.status}>{scenario.feasible ? "Recoverable" : "Unrecoverable"}</StatusText>
            </div>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {scenario.feasible
                ? <>Recovery {money(scenario.new_cost ?? "0")} · {delta(scenario.cost_delta)} · {scenario.deadline_delta_hours === 0 ? "same deadline" : `${scenario.deadline_delta_hours ?? 0}h delivery shift`}{scenario.replacement_suppliers.length > 0 && ` · via ${scenario.replacement_suppliers.join(", ")}`}</>
                : <>{scenario.lost_quantity} units uncovered{scenario.shortages.length > 0 ? ` · ${scenario.shortages.map((row) => `${row.item}: ${row.shortage} (${row.reason})`).join(", ")}` : ""}</>}
            </p>
          </li>
        ))}
      </ul>
    </Subsection>
  );
}

function FailureFrontier({ analysis }: { analysis: ContinuityAnalysis }) {
  return (
    <Subsection label="Failure frontier" title="Failure frontier" note="Smallest monotonic shock that makes the current quote snapshot infeasible. These are mathematical counterfactuals, not actual supplier failures.">
      <table className="w-full text-sm">
        <thead><tr className="border-b"><th className={head}>Supplier</th><th className={`${head} text-right`}>Price</th><th className={`${head} text-right`}>ETA</th><th className={`${head} text-right`}>Capacity</th></tr></thead>
        <tbody>
          {analysis.failure_frontier.map((frontier) => (
            <tr key={frontier.supplier_id} className="border-b">
              <td className={cell}>{frontier.supplier}{frontier.note && <span className="block text-xs text-muted-foreground">{frontier.note}</span>}</td>
              <td className={`${cell} text-right tabular`}>{frontier.price ? `+${frontier.price.increase_percent}%` : "—"}</td>
              <td className={`${cell} text-right tabular`}>{frontier.delay ? `+${frontier.delay.hours}h` : "—"}</td>
              <td className={`${cell} text-right tabular`}>{frontier.capacity ? `${frontier.capacity.loss_units} units` : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Subsection>
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return <div><dt className="text-xs font-medium text-muted-foreground">{label}</dt><dd className="mt-1 text-base tabular">{children}</dd></div>;
}

// A section of the Plan tab: deterministic N-1 stress tests of the current plan, always labeled HYPOTHETICAL.
export function ContinuityPanel({ plan, view, running, onRun }: { plan?: Plan; view?: ContinuityView; running: boolean; onRun: () => void }) {
  const analysis = view?.analysis;
  const state = view?.state ?? "NOT_READY";
  const canRun = Boolean(plan && (plan.status === "feasible" || plan.status === "approved"));
  const resilient = analysis?.resilient_alternative;
  return (
    <section aria-label="Continuity Engine" className="border-t pt-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h3 className="text-base font-semibold">Continuity <Provenance className="ml-2" value="HYPOTHETICAL" /></h3>
          <p className="mt-1 max-w-xl text-sm text-muted-foreground">Will this plan survive reality? ReliefMesh stress-tests the exact plan inputs before a real supplier change forces recovery.</p>
        </div>
        <Button variant="secondary" onClick={onRun} disabled={!canRun || running}><RefreshCw className={running ? "size-3.5 motion-safe:animate-spin" : "size-3.5"} />Find resilient alternative</Button>
      </div>
      {!plan && <p className="mt-4 text-sm text-muted-foreground">Create a feasible plan first. Continuity analysis is queued automatically for every feasible plan.</p>}
      {plan && state === "RUNNING" && <p className="mt-4 text-sm text-muted-foreground">Continuity analysis running… deterministic N-1 scenarios are executing in the background.</p>}
      {plan && state === "NOT_READY" && <p className="mt-4 text-sm text-muted-foreground">Continuity analysis is queued automatically after optimization. You can also start a fresh current-snapshot run.</p>}
      {state === "STALE" && analysis && <p className="mt-4 text-sm text-muted-foreground">This is a historical HYPOTHETICAL result for Plan v{analysis.plan_version}; quote, evidence, policy, or plan inputs changed. It is not shown as current.</p>}
      {analysis && (
        <>
          <p className="mt-4 max-w-2xl text-xs text-muted-foreground">{analysis.counterfactual_label} Input hash <span className="font-mono">{analysis.input_hash.slice(0, 12)}</span> · analyzed {when(analysis.created_at)}</p>
          {analysis.scope && analysis.scope.kind !== "FULL_MISSION" && <p className="mt-2 max-w-2xl text-xs text-muted-foreground">Scope: {analysis.scope.statement} Fixed commitments: {money(analysis.scope.fixed_commitment_cost)} across {analysis.scope.fixed_commitment_count} PO line{analysis.scope.fixed_commitment_count === 1 ? "" : "s"}.</p>}
          <dl className="mt-6 grid grid-cols-2 gap-6 sm:grid-cols-4">
            <Fact label="N-1 survivability">{analysis.metrics.n1_survivability.survives}/{analysis.metrics.n1_survivability.tested}<span className="block text-xs text-muted-foreground">allocated suppliers</span></Fact>
            <Fact label="Budget headroom">{money(analysis.metrics.budget_headroom)}</Fact>
            <Fact label="Deadline slack">{analysis.metrics.deadline_slack_hours === null ? "—" : `${analysis.metrics.deadline_slack_hours}h`}</Fact>
            <Fact label="Largest concentration">{percent(analysis.metrics.largest_supplier_concentration)}<span className="block text-xs text-muted-foreground">{analysis.metrics.critical_supplier?.supplier ?? "no critical supplier"}</span></Fact>
          </dl>
          <DigitalTwin analysis={analysis} view={view!} />
          <Scenarios analysis={analysis} />
          <FailureFrontier analysis={analysis} />
          <Subsection label="Cost vs resilience" title="Cheapest vs resilient" note="The resilient alternative is a separate MILP with a ≤50% supplier-concentration guardrail. It is a proposal only; human approval remains required.">
            {resilient?.status === "AVAILABLE" ? (
              <dl className="grid grid-cols-2 gap-6 sm:grid-cols-4">
                <Fact label="Cheapest">{money(analysis.baseline.total_cost)}</Fact>
                <Fact label="Resilient">{money(resilient.total_cost ?? "0")}</Fact>
                <Fact label="Added cost">{money(resilient.added_cost ?? "0")}</Fact>
                <Fact label="N-1 under guardrail">{resilient.n1_survivability?.survives}/{resilient.n1_survivability?.tested}</Fact>
              </dl>
            ) : <p className="text-sm text-muted-foreground">{resilient?.reason}</p>}
          </Subsection>
          <p className="mt-6 text-xs text-muted-foreground">Policy and approval are unchanged; deterministic optimization calculated these scenarios. AI does not decide eligibility, constraints, approval, or payment.</p>
        </>
      )}
    </section>
  );
}
