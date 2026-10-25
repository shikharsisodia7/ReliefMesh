"use client";

import { useState } from "react";

import { Provenance, amount, when } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import { Table } from "@/components/ui/table";
import type { ContinuityAnalysis, ContinuityView, Plan, RealityCheck } from "@/lib/types";

const percent = (value: number) => `${Math.round(value * 100)}%`;
// Whole dollars like the plan itself; a zero delta reads as words, not "+$0".
const signedMoney = (value?: string | null) => {
  if (value == null) return "—";
  const number = Number(value);
  return Math.abs(number) < 0.005 ? "no added cost" : `${number > 0 ? "+" : "−"}${amount(Math.abs(number))}`;
};
const hours = (value: number) => (value >= 48 ? `${Math.round((value / 24) * 10) / 10} d` : `${value} h`);

// Every counterfactual carries this exact label; real events never do.
function StressLabel() {
  return <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">Hypothetical stress test</span>;
}

function Fact({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="border-t py-2.5">
      <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
      <dd className="tabular mt-0.5 text-sm font-medium">{value}{detail && <span className="block text-xs font-normal text-tertiary">{detail}</span>}</dd>
    </div>
  );
}

// The judge-readable picture: who carries the plan, and what losing each one does (from the N-1 scenarios).
function SinglePointOfFailure({ analysis }: { analysis: ContinuityAnalysis }) {
  const critical = analysis.metrics.critical_supplier?.supplier_id;
  return (
    <section aria-label="Single point of failure" className="space-y-3">
      <div className="flex flex-wrap items-baseline gap-x-2"><h3 className="text-base font-semibold">Where this plan can break</h3><StressLabel /></div>
      <ul className="space-y-4">
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
              <p className="mt-1.5 text-sm text-muted-foreground">
                If {row.supplier} is lost:{" "}
                {scenario?.feasible
                  ? <>recoverable at {amount(scenario.new_cost)} ({signedMoney(scenario.cost_delta)}){scenario.replacement_suppliers.length > 0 && ` via ${scenario.replacement_suppliers.join(", ")}`}</>
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
      <h3 className="text-base font-semibold">Cost of resilience</h3>
      <dl className="grid gap-x-8 sm:grid-cols-3">
        <Fact label="Current plan (cheapest)" value={amount(analysis.baseline.total_cost)} detail={`N-1 ${n1.survives} of ${n1.tested}`} />
        <Fact label={`Resilient alternative (max share ${share})`} value={amount(alternative.total_cost)} detail={`N-1 ${altN1.survives} of ${altN1.tested}`} />
        <Fact label="Added cost" value={signedMoney(alternative.added_cost)} detail={fullyResilient ? "Every single-supplier loss is recoverable" : "Less concentrated; not every single-supplier loss is recoverable"} />
      </dl>
      {/* The allocation change is the substance of the trade-off, so it is always shown. */}
      <Table className="w-full text-sm">
        <thead><tr className="text-left text-xs text-muted-foreground"><th className="py-1.5 font-medium">Supplier</th><th className="py-1.5 text-right font-medium">Current plan</th><th className="py-1.5 text-right font-medium">Resilient alternative</th><th className="py-1.5 text-right font-medium">Change</th></tr></thead>
        <tbody>
          {Object.keys({ ...current, ...proposed }).sort((a, b) => (names[a] ?? a).localeCompare(names[b] ?? b)).map((id) => {
            const change = (proposed[id] ?? 0) - (current[id] ?? 0);
            return (
              <tr key={id} className="border-t">
                <td className="py-2">{names[id] ?? id}</td>
                <td className="tabular py-2 text-right">{current[id] ?? 0} units</td>
                <td className={`tabular py-2 text-right ${change !== 0 ? "font-semibold" : ""}`}>{proposed[id] ?? 0} units</td>
                <td className="tabular py-2 text-right text-muted-foreground">{change === 0 ? "—" : `${change > 0 ? "+" : "−"}${Math.abs(change)}`}</td>
              </tr>
            );
          })}
        </tbody>
      </Table>
      <p className="text-xs text-tertiary">A proposal only, computed by the same optimizer with a stronger concentration constraint and stress-tested the same way as the current plan. It cannot be approved or ordered; adopting it means setting the guardrail on the mission and re-optimizing.</p>
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
                  {earlier.label}{earlier.predicted_cost ? ` → recovery ${amount(earlier.predicted_cost)} (${signedMoney(earlier.predicted_cost_delta)})` : ""}
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
                {check.actual.supplier}: {actualText} → plan v{check.actual.plan_version} {check.actual.plan_total_cost ? amount(check.actual.plan_total_cost) : check.actual.plan_status}
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
  const queued = (view?.active_jobs?.length ?? 0) > 0;
  // Everything already on purchase orders leaves nothing to stress-test; "0 of 0" would read as a failure.
  const nothingLeft = analysis?.scope?.kind === "NO_UNCOMMITTED_REQUIREMENTS";
  // Open by default: this is the plan's main risk read-out. The toggle only tucks it away.
  const [open, setOpen] = useState(true);
  const summary = !plan ? "needs a feasible plan" : !canRun ? `plan v${plan.version} is ${plan.status}`
    : state === "RUNNING" ? `running${progress?.total ? ` · ${progress.done} / ${progress.total} scenarios` : ""}`
      : state === "STALE" ? "result is out of date" : current && nothingLeft ? "nothing left to stress-test: every unit is on a purchase order" : current && metrics
        ? `${metrics.n1_survivability.survives} of ${metrics.n1_survivability.tested} supplier losses recoverable${metrics.critical_supplier ? ` · critical supplier: ${metrics.critical_supplier.supplier}` : ""}`
        : queued ? "queued" : `not run for plan v${plan.version} yet`;
  // Re-running a current result returns the same cached analysis, so the action shows only when it would add something.
  const needsRun = canRun && !queued && (state === "NOT_READY" || state === "STALE");
  return (
    <section aria-label="Continuity Engine" className="space-y-8 border-t pt-6">
      <div className="text-sm">
        <div className="flex flex-wrap items-baseline gap-x-2"><h2 className="text-base font-semibold">Continuity</h2><span className="text-muted-foreground">·</span><Provenance value="HYPOTHETICAL" /></div>
        {/* The result and its toggle get their own line, so a separator never starts a wrapped line. */}
        <p className="mt-1"><span className="text-muted-foreground">{summary.charAt(0).toUpperCase() + summary.slice(1)} · </span><button type="button" aria-expanded={open} className="font-medium hover:underline" onClick={() => setOpen(!open)}>{open ? "Hide details" : "Show details"}</button></p>
      </div>
      {open && <>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="max-w-3xl text-sm text-muted-foreground">Would this plan survive losing a supplier? Each scenario re-runs the same optimizer and policy on copies of the exact quotes behind this plan. Every scenario is a counterfactual, not an event that happened; no quote, plan, approval, or order is changed. Real supplier changes appear under &ldquo;Actual change vs earlier stress test&rdquo;.</p>
          </div>
          {needsRun && <Button size="sm" variant="secondary" type="button" onClick={onRun} disabled={running}>Run stress test</Button>}
        </div>

        {!plan && <p className="text-sm text-muted-foreground">Create a feasible plan first. Every feasible plan is stress-tested automatically.</p>}
        {plan && !canRun && <p className="text-sm text-muted-foreground">Plan v{plan.version} is {plan.status}; only a feasible or approved plan can be stress-tested.</p>}
        {plan && canRun && state === "RUNNING" && (
          <p className="text-sm text-muted-foreground" role="status">
            Continuity analysis running…{progress?.total ? ` ${progress.done} / ${progress.total} scenarios` : ""}{progress?.label && progress.done ? ` · ${progress.label}` : ""}
          </p>
        )}
        {plan && canRun && state === "NOT_READY" && <p className="text-sm text-muted-foreground">{queued ? "Queued automatically after optimization." : `No current stress test for plan v${plan.version}. A result is kept only if the plan's inputs didn't change while it was computing. Run it to see where this plan can break.`}</p>}
        {analysis && state === "STALE" && <p className="text-sm text-muted-foreground">Stale: the result for plan v{analysis.plan_version} no longer matches its quotes, evidence, policy, or committed orders, so it is not shown as current. Run it again for the current inputs.</p>}

        {current && nothingLeft && analysis.scope && <p className="text-sm text-muted-foreground">{analysis.scope.statement} Already committed on purchase orders: {amount(analysis.scope.fixed_commitment_cost)}.</p>}
        {current && metrics && !nothingLeft && (
          <>
            {analysis.scope && analysis.scope.kind !== "FULL_MISSION" && <p className="text-sm text-muted-foreground">{analysis.scope.statement} Already committed on purchase orders: {amount(analysis.scope.fixed_commitment_cost)}.</p>}
            {/* Headline figure, then the facts behind it in one full-width grid. */}
            <div role="region" aria-label="N-1 survivability" className="grid gap-x-10 gap-y-4 md:grid-cols-[auto_minmax(0,1fr)]">
              <div>
                <p className="text-xs font-medium text-muted-foreground">N-1 survivability</p>
                <p className="tabular text-4xl font-semibold tracking-tight">{metrics.n1_survivability.survives} of {metrics.n1_survivability.tested}</p>
                <p className="mt-1 max-w-48 text-xs text-muted-foreground">allocated suppliers whose loss the plan can recover from</p>
              </div>
              <dl className="grid grid-cols-2 gap-x-6 sm:grid-cols-3">
                <Fact label="Critical supplier" value={metrics.critical_supplier?.supplier ?? "None"} detail={metrics.critical_supplier?.reason} />
                <Fact label="Largest supplier share" value={percent(metrics.largest_supplier_concentration)} />
                <Fact label="Alternative eligible capacity" value={`${metrics.alternative_eligible_capacity} units`} detail="Eligible but unallocated" />
                <Fact label="Budget headroom" value={amount(metrics.budget_headroom)} />
                <Fact label="Deadline slack" value={metrics.deadline_slack_hours == null ? "—" : hours(metrics.deadline_slack_hours)} />
              </dl>
            </div>
            <SinglePointOfFailure analysis={analysis} />
            <section aria-label="Failure frontier" className="space-y-3">
              <div className="flex flex-wrap items-baseline gap-x-2"><h3 className="text-base font-semibold">Failure frontier</h3><StressLabel /></div>
              <p className="text-sm text-muted-foreground">The smallest shock to one supplier that breaks the mission. One step less still has a feasible plan.</p>
              <dl className="grid gap-x-8 sm:grid-cols-3">
                <Fact label="Price shock that breaks it" value={metrics.price_shock_tolerance ? `+${metrics.price_shock_tolerance.increase_percent}%` : "No breakpoint"} />
                <Fact label="Delay that misses the deadline" value={metrics.delay_tolerance ? hours(metrics.delay_tolerance.hours) : "No breakpoint"} />
                <Fact label="Capacity loss that breaks coverage" value={metrics.capacity_loss_tolerance ? `${metrics.capacity_loss_tolerance.loss_units} units` : "No breakpoint"} />
              </dl>
              <Table className="w-full text-sm">
                <thead><tr className="text-left text-xs text-muted-foreground"><th className="py-1.5 font-medium">Supplier</th><th className="py-1.5 text-right font-medium">Price</th><th className="py-1.5 text-right font-medium">ETA delay</th><th className="py-1.5 text-right font-medium">Capacity loss</th></tr></thead>
                <tbody>
                  {analysis.failure_frontier.map((row) => (
                    <tr key={row.supplier_id} className="border-t">
                      <td className="py-2">{row.supplier}</td>
                      {row.note ? <td colSpan={3} className="py-2 text-right text-muted-foreground">No breakpoint: the plan recovers without it</td> : <>
                        <td className="tabular py-2 text-right">{row.price ? `+${row.price.increase_percent}%` : "—"}</td>
                        <td className="tabular py-2 text-right">{row.delay ? hours(row.delay.hours) : "—"}</td>
                        <td className="tabular py-2 text-right">{row.capacity ? `${row.capacity.loss_units} units` : "—"}</td>
                      </>}
                    </tr>
                  ))}
                </tbody>
              </Table>
              <p className="text-xs text-tertiary">“No breakpoint” means no shock of that kind to a single supplier can break this plan.</p>
            </section>
            <CostOfResilience analysis={analysis} plan={plan} />
            <p className="text-xs text-tertiary">Bound to plan v{analysis.plan_version} · inputs {analysis.input_hash.slice(0, 12)} · computed {when(analysis.created_at)} · deterministic optimization, no AI.</p>
          </>
        )}
      <RealityChecks checks={view?.reality_check ?? []} />
      </>}
    </section>
  );
}
