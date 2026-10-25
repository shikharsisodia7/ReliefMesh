"use client";

import { useState } from "react";

import { Provenance, money, when } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import type { ContinuityAnalysis, ContinuityView, Plan, RealityCheck } from "@/lib/types";

const percent = (value: number) => `${Math.round(value * 100)}%`;
const signedMoney = (value?: string | null) => (value == null ? "—" : `${Number(value) >= 0 ? "+" : "−"}${money(Math.abs(Number(value)))}`);
const hours = (value: number) => (value >= 48 ? `${Math.round((value / 24) * 10) / 10} d` : `${value} h`);

// Every counterfactual carries this exact label; real events never do.
function StressLabel() {
  return <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">Hypothetical stress test</span>;
}

function Fact({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="border-t py-2.5">
      <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
      <dd className="tabular mt-0.5 text-sm font-medium">{value}</dd>
      {detail && <p className="text-xs text-tertiary">{detail}</p>}
    </div>
  );
}

// The judge-readable picture: who carries the plan, and what losing each one does (from the N-1 scenarios).
function SinglePointOfFailure({ analysis }: { analysis: ContinuityAnalysis }) {
  const critical = analysis.metrics.critical_supplier?.supplier_id;
  return (
    <section aria-label="Single point of failure" className="space-y-2">
      <h3 className="text-base font-semibold">Where this plan can break</h3>
      <ul className="space-y-3">
        {analysis.baseline.supplier_concentration.map((row) => {
          const scenario = analysis.n1_scenarios.find((item) => item.supplier_id === row.supplier_id);
          const isCritical = row.supplier_id === critical;
          return (
            <li key={row.supplier_id}>
              <div className="flex flex-wrap items-baseline justify-between gap-x-4 text-sm">
                <span className="font-medium">{row.supplier}</span>
                <span className="tabular text-muted-foreground">{row.units} units · {percent(row.unit_share)} of allocation</span>
              </div>
              <div className="mt-1 h-2 rounded-sm bg-muted" aria-hidden>
                <div className={`h-full rounded-sm ${isCritical ? "bg-foreground" : "bg-muted-foreground/40"}`} style={{ width: `${Math.max(2, row.unit_share * 100)}%` }} />
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                <StressLabel /> · Stress test: {row.supplier} unavailable →{" "}
                {scenario?.feasible
                  ? <>recoverable at {money(scenario.new_cost)} ({signedMoney(scenario.cost_delta)}){scenario.replacement_suppliers.length > 0 && ` via ${scenario.replacement_suppliers.join(", ")}`}</>
                  : <span className={isCritical ? "font-medium text-warn" : ""}>mission infeasible{scenario ? ` · ${scenario.lost_quantity} units uncovered` : ""}{isCritical ? " · single point of failure" : ""}</span>}
              </p>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function CostOfResilience({ analysis, plan }: { analysis: ContinuityAnalysis; plan?: Plan }) {
  const [compare, setCompare] = useState(false);
  const alternative = analysis.resilient_alternative;
  const n1 = analysis.metrics.n1_survivability;
  if (alternative.status !== "AVAILABLE") {
    return (
      <section aria-label="Cost of resilience" className="space-y-1">
        <h3 className="text-base font-semibold">Resilient alternative</h3>
        <p className="text-sm text-muted-foreground">{alternative.reason ?? "No feasible plan meets the stronger supplier-concentration guardrail."}</p>
      </section>
    );
  }
  const altN1 = alternative.n1_survivability ?? { survives: 0, tested: 0 };
  const fullyResilient = altN1.tested > 0 && altN1.survives === altN1.tested;
  const share = alternative.constraint ? percent(Number(alternative.constraint.max_supplier_share)) : "50%";
  const unitsBySupplier = (rows: { supplier_id: string; quantity: number }[]) =>
    rows.reduce<Record<string, number>>((acc, row) => ({ ...acc, [row.supplier_id]: (acc[row.supplier_id] ?? 0) + row.quantity }), {});
  const current = unitsBySupplier((plan?.allocations ?? []).filter((row) => !row.committed));
  const proposed = unitsBySupplier(alternative.allocations ?? []);
  const names: Record<string, string> = Object.fromEntries([
    ...analysis.baseline.supplier_concentration.map((row) => [row.supplier_id, row.supplier]),
    ...(alternative.allocations ?? []).map((row) => [row.supplier_id, row.supplier ?? row.supplier_email]),
  ]);
  return (
    <section aria-label="Cost of resilience" className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h3 className="text-base font-semibold">Cost of resilience</h3>
        <Button size="sm" variant="secondary" type="button" onClick={() => setCompare(!compare)}>{compare ? "Hide comparison" : "Compare"}</Button>
      </div>
      <dl className="grid gap-x-8 sm:grid-cols-3">
        <Fact label="Current plan (cheapest)" value={money(analysis.baseline.total_cost)} detail={`N-1 ${n1.survives}/${n1.tested}`} />
        <Fact label={`Resilient alternative (max share ≤ ${share})`} value={money(alternative.total_cost)} detail={`N-1 ${altN1.survives}/${altN1.tested}`} />
        <Fact label="Additional cost" value={signedMoney(alternative.added_cost)} detail={fullyResilient ? "Every single-supplier loss is recoverable (proven by stress test)" : "Reduces concentration; not every single-supplier loss is recoverable"} />
      </dl>
      <p className="text-xs text-muted-foreground"><StressLabel /> · the alternative&apos;s N-1 result comes from stress-testing it the same way as the current plan.</p>
      {compare && (
        <table className="w-full text-sm">
          <thead><tr className="text-left text-xs text-muted-foreground"><th className="py-1 font-medium">Supplier</th><th className="py-1 text-right font-medium">Current plan</th><th className="py-1 text-right font-medium">Resilient alternative</th></tr></thead>
          <tbody>
            {Object.keys({ ...current, ...proposed }).sort((a, b) => (names[a] ?? a).localeCompare(names[b] ?? b)).map((id) => (
              <tr key={id} className="border-t"><td className="py-1.5">{names[id] ?? id}</td><td className="tabular py-1.5 text-right">{current[id] ?? 0} units</td><td className="tabular py-1.5 text-right">{proposed[id] ?? 0} units</td></tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="text-xs text-tertiary">A proposal only, computed by the same optimizer with a stronger concentration constraint. It cannot be approved or ordered; adopting it means setting the guardrail on the mission and re-optimizing.</p>
    </section>
  );
}

function RealityChecks({ checks }: { checks: RealityCheck[] }) {
  if (!checks.length) return null;
  return (
    <section aria-label="Actual versus stress test" className="space-y-3">
      <h3 className="text-base font-semibold">Actual change vs earlier stress test</h3>
      {checks.map((check) => {
        const change = check.actual.change;
        const actualText = typeof change === "string" || !change ? (change ?? check.actual.kind) : [
          change.price_change_basis_points ? `price ${change.price_change_percent > 0 ? "+" : ""}${change.price_change_percent}%` : null,
          change.capacity_loss_units ? `${change.capacity_loss_units > 0 ? "−" : "+"}${Math.abs(change.capacity_loss_units)} units` : null,
          change.delay_hours ? `ETA ${change.delay_hours > 0 ? "+" : ""}${change.delay_hours} h` : null,
        ].filter(Boolean).join(", ") || "no material change";
        const earlier = check.earlier_stress_test;
        return (
          <div key={check.supplier_id} className="grid gap-x-8 border-t pt-2 sm:grid-cols-2">
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">Predicted counterfactual</p>
              <Provenance value="HYPOTHETICAL" />
              {earlier ? (
                <p className="mt-1 text-sm">
                  {earlier.label}{earlier.predicted_cost ? ` → recovery ${money(earlier.predicted_cost)} (${signedMoney(earlier.predicted_cost_delta)})` : ""}
                  {earlier.tolerance && ` → breaks at ${[
                    earlier.tolerance.price_breakpoint_basis_points != null ? `+${earlier.tolerance.price_breakpoint_basis_points / 100}% price` : null,
                    earlier.tolerance.delay_breakpoint_hours != null ? `+${earlier.tolerance.delay_breakpoint_hours} h ETA` : null,
                    earlier.tolerance.capacity_breakpoint_units != null ? `−${earlier.tolerance.capacity_breakpoint_units} units` : null,
                  ].filter(Boolean).join(" or ") || "no single-supplier breakpoint"}`}
                  <span className="block text-xs text-muted-foreground">Run on plan v{earlier.plan_version} before the change.</span>
                </p>
              ) : <p className="mt-1 text-sm text-muted-foreground">{check.note}</p>}
            </div>
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                {check.actual.provenance === "USER_SUBMITTED" ? "Actual user-submitted change" : "Actual change"}
              </p>
              <Provenance value={check.actual.provenance} />
              <p className="mt-1 text-sm">
                {check.actual.supplier}: {actualText} → plan v{check.actual.plan_version} {check.actual.plan_total_cost ? money(check.actual.plan_total_cost) : check.actual.plan_status}
                <span className="block text-xs text-muted-foreground">
                  {check.consistent === true ? "Outcome matches the earlier stress test." : check.consistent === false ? "Outcome differs from the earlier stress test." : check.note ?? "Not directly comparable."}
                </span>
              </p>
            </div>
          </div>
        );
      })}
    </section>
  );
}

export function ContinuityPanel({ plan, view, running, onRun }: { plan?: Plan; view?: ContinuityView; running: boolean; onRun: () => void }) {
  const analysis = view?.analysis;
  const state = view?.state ?? "NOT_READY";
  const canRun = Boolean(plan && (plan.status === "feasible" || plan.status === "approved"));
  const current = state === "COMPLETE" && analysis;
  const metrics = analysis?.metrics;
  const progress = view?.progress;
  return (
    <section aria-label="Continuity Engine" className="space-y-5 border-t pt-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-baseline gap-3"><h2 className="text-base font-semibold">Continuity</h2><Provenance value="HYPOTHETICAL" /></div>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">Would this plan survive losing a supplier? Each scenario re-runs the same optimizer and policy on copies of the exact quotes behind this plan. No quote, plan, approval, or order is changed.</p>
          <p className="mt-1 text-xs text-muted-foreground"><StressLabel /> · every scenario on this panel is a counterfactual, not an event that happened. Real changes appear under &ldquo;Actual change vs earlier stress test&rdquo;.</p>
        </div>
        <Button size="sm" variant="secondary" type="button" onClick={onRun} disabled={!canRun || running || state === "RUNNING"}>Find resilient alternative</Button>
      </div>

      {!plan && <p className="text-sm text-muted-foreground">Create a feasible plan first. Every feasible plan is stress-tested automatically.</p>}
      {plan && !canRun && <p className="text-sm text-muted-foreground">Plan v{plan.version} is {plan.status}; only a feasible or approved plan can be stress-tested.</p>}
      {plan && canRun && state === "RUNNING" && (
        <p className="text-sm text-muted-foreground" role="status">
          Continuity analysis running…{progress?.total ? ` ${progress.done} / ${progress.total} scenarios` : ""}{progress?.label && progress.done ? ` · ${progress.label}` : ""}
        </p>
      )}
      {plan && canRun && state === "NOT_READY" && <p className="text-sm text-muted-foreground">Queued automatically after optimization.</p>}
      {analysis && state === "STALE" && <p className="text-sm text-muted-foreground">Stale: the result for plan v{analysis.plan_version} no longer matches its quotes, evidence, or policy, so it is not shown as current.</p>}

      {current && metrics && (
        <>
          {analysis.scope && analysis.scope.kind !== "FULL_MISSION" && <p className="text-sm text-muted-foreground">{analysis.scope.statement} Already committed on purchase orders: {money(analysis.scope.fixed_commitment_cost)}.</p>}
          <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
            <div role="region" aria-label="N-1 survivability">
              <p className="text-xs font-medium text-muted-foreground">N-1 survivability</p>
              <p className="tabular text-4xl font-semibold">{metrics.n1_survivability.survives} / {metrics.n1_survivability.tested}</p>
              <p className="text-xs text-muted-foreground">allocated suppliers whose loss is recoverable</p>
              <dl className="mt-4 grid grid-cols-2 gap-x-6">
                <Fact label="Critical supplier" value={metrics.critical_supplier?.supplier ?? "None"} />
                <Fact label="Budget headroom" value={money(metrics.budget_headroom)} />
                <Fact label="Largest supplier share" value={percent(metrics.largest_supplier_concentration)} />
                <Fact label="Deadline slack" value={metrics.deadline_slack_hours == null ? "—" : hours(metrics.deadline_slack_hours)} />
                <Fact label="Price tolerance" value={metrics.price_shock_tolerance ? `+${metrics.price_shock_tolerance.increase_percent}%` : "No breakpoint"} />
                <Fact label="Delay tolerance" value={metrics.delay_tolerance ? hours(metrics.delay_tolerance.hours) : "No breakpoint"} />
                <Fact label="Capacity tolerance" value={metrics.capacity_loss_tolerance ? `${metrics.capacity_loss_tolerance.loss_units} units` : "No breakpoint"} />
                <Fact label="Alternative eligible capacity" value={`${metrics.alternative_eligible_capacity} units`} />
              </dl>
              <p className="mt-2 text-xs text-tertiary">Tolerances are the smallest shock to one supplier that makes the mission infeasible; one step less still has a feasible plan. “No breakpoint” means no single-supplier shock can break this plan.</p>
            </div>
            <SinglePointOfFailure analysis={analysis} />
          </div>
          <CostOfResilience analysis={analysis} plan={plan} />
          <details className="text-sm" open aria-label="Failure frontier">
            <summary className="cursor-pointer font-medium">Failure frontier by supplier <StressLabel /></summary>
            <table className="mt-2 w-full">
              <thead><tr className="text-left text-xs text-muted-foreground"><th className="py-1 font-medium">Supplier</th><th className="py-1 text-right font-medium">Price</th><th className="py-1 text-right font-medium">ETA delay</th><th className="py-1 text-right font-medium">Capacity loss</th></tr></thead>
              <tbody>
                {analysis.failure_frontier.map((row) => (
                  <tr key={row.supplier_id} className="border-t">
                    <td className="py-1.5">{row.supplier}</td>
                    {row.note ? <td colSpan={3} className="py-1.5 text-right text-muted-foreground">Recoverable without it: no breakpoint</td> : <>
                      <td className="tabular py-1.5 text-right">{row.price ? `+${row.price.increase_percent}%` : "—"}</td>
                      <td className="tabular py-1.5 text-right">{row.delay ? hours(row.delay.hours) : "—"}</td>
                      <td className="tabular py-1.5 text-right">{row.capacity ? `${row.capacity.loss_units} units` : "—"}</td>
                    </>}
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
          <p className="text-xs text-tertiary">Bound to plan v{analysis.plan_version} · inputs {analysis.input_hash.slice(0, 12)} · computed {when(analysis.created_at)} · deterministic optimization, no AI.</p>
        </>
      )}
      <RealityChecks checks={view?.reality_check ?? []} />
    </section>
  );
}
