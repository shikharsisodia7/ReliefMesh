"use client";

import { Circle, CircleCheck } from "lucide-react";
import { useState, type ReactNode } from "react";

import { ContinuityPanel } from "@/components/mission/continuity-panel";
import { CompareView, DemoControls } from "@/components/mission/planning-panels";
import { EVIDENCE_ORDER } from "@/components/mission/supplier-evidence";
import { Drawer } from "@/components/patterns/overlays";
import { PlanStatusText, PolicyText, Provenance, amount, clock, day, money, signedAmount, timeOnly, when } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useCountUp } from "@/hooks/use-count-up";
import { api } from "@/lib/api";
import type { Approval, ContinuityView, Disruption, Mission, Plan, PurchaseOrder, Quote, SupplierRow } from "@/lib/types";

type Run = (operation: () => Promise<void>) => Promise<void>;

const num = (value?: string | number | null) => Number(value ?? 0);

function supplierLabel(plan: Plan, supplierId: string) {
  const row = plan.policy?.suppliers?.[supplierId];
  return row?.legal_name || row?.email || supplierId.slice(0, 8);
}

export function isReplan(plan: Plan) {
  return plan.trigger === "supplier_disruption" || plan.trigger === "policy_change";
}

// Seconds from the triggering change to the finished plan, when the trigger recorded its time.
export function rebuildSeconds(plan: Plan) {
  const at = plan.trigger_detail.find((detail) => detail.at)?.at;
  if (!at) return null;
  const seconds = (new Date(plan.computed_at).getTime() - new Date(at).getTime()) / 1000;
  return seconds >= 0 ? seconds.toFixed(1) : null;
}

function planSentence(plan: Plan, previous: Plan | undefined, revoked: Approval | undefined) {
  if (!isReplan(plan)) {
    const eligible = plan.policy?.eligible_quote_ids.length ?? 0;
    return `Computed at ${timeOnly(plan.computed_at)} from ${eligible} policy-eligible quote${eligible === 1 ? "" : "s"}${plan.trigger === "agent" ? " at the Fetch.ai agent's request" : ""}.`;
  }
  const reasons = plan.trigger_detail.map((detail) => detail.summary).filter(Boolean);
  const parts = [`Rebuilt automatically at ${timeOnly(plan.computed_at)}${reasons.length ? ` after ${reasons.join("; ")}` : ""}.`];
  if (previous) parts.push(revoked ? `Plan v${previous.version} and its approval no longer apply.` : `Plan v${previous.version} no longer applies.`);
  const seconds = rebuildSeconds(plan);
  if (seconds) parts.push(`Replanned in ${seconds} s.`);
  return parts.join(" ");
}

type Row = { id: string; name: string; units: number; unit: string | null; items: number; ship: number | null; orders: string[] };

// Per-supplier totals for one plan. Shipping isn't stored on the plan, so it comes from each allocated quote.
function supplierRows(plan: Plan, quotes: Map<string, Quote>) {
  const rows = new Map<string, Row & { quoteIds: Set<string>; prices: Set<string> }>();
  for (const line of plan.allocations) {
    const row = rows.get(line.supplier_id) ?? { id: line.supplier_id, name: supplierLabel(plan, line.supplier_id), units: 0, unit: null, items: 0, ship: null, orders: [], quoteIds: new Set<string>(), prices: new Set<string>() };
    row.units += line.quantity;
    row.items += num(line.line_cost);
    row.quoteIds.add(line.quote_id);
    row.prices.add(line.unit_price);
    if (line.committed && line.po_number) row.orders.push(line.po_number);
    rows.set(line.supplier_id, row);
  }
  for (const row of rows.values()) {
    row.unit = row.prices.size === 1 ? [...row.prices][0] : null;
    const shipping = [...row.quoteIds].map((id) => quotes.get(id)?.shipping_cost);
    row.ship = shipping.every((value) => value !== undefined) ? shipping.reduce((sum, value) => sum + num(value), 0) : null;
  }
  return rows as Map<string, Row>;
}

// Shipping-based figures are shown only when the rows add back up to the plan's own total.
function addsUp(plan: Plan, rows: Map<string, Row>) {
  let sum = 0;
  for (const row of rows.values()) {
    if (row.ship === null) return false;
    sum += row.items + row.ship;
  }
  return Math.abs(sum - num(plan.total_cost)) < 0.01;
}

function coverage(mission: Mission, plan: Plan) {
  const requirements = plan.constraints?.requirements ?? mission.requirements;
  return requirements.map((requirement) => {
    const units = plan.allocations.filter((line) => line.item === requirement.item).reduce((sum, line) => sum + line.quantity, 0);
    return `${units} of ${requirement.quantity} ${requirement.item}`;
  }).join(", ") + " covered";
}

const humanize = (rule: string) => rule.charAt(0) + rule.slice(1).toLowerCase().replace(/_/g, " ");

function RailSection({ title, children }: { title: string; children: ReactNode }) {
  return <section className="border-b py-6 first:pt-0 last:border-0"><h3 className="text-base font-semibold">{title}</h3><div className="mt-4">{children}</div></section>;
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return <div className="flex items-baseline justify-between gap-4 py-1.5 text-sm"><dt className="text-muted-foreground">{label}</dt><dd className="text-right tabular">{children}</dd></div>;
}

function Step({ done, children }: { done: boolean; children: ReactNode }) {
  const Icon = done ? CircleCheck : Circle;
  return (
    <li className="relative flex gap-3 pb-5 text-sm last:pb-0 before:absolute before:top-6 before:bottom-1 before:left-[9.5px] before:w-px before:bg-border last:before:hidden">
      <Icon className="size-5 shrink-0 text-muted-foreground" strokeWidth={1.5} />
      <span className={done ? "text-muted-foreground" : ""}>{children}</span>
    </li>
  );
}

const linkClass = "text-sm font-medium hover:underline";

function ApprovalSection({ plan, approvals, canApprove, approvalBlocked, requester, ttlMinutes, token, run, setNotice, onTab }: {
  plan: Plan; approvals: Approval[]; canApprove: boolean; approvalBlocked: string | null; requester: string; ttlMinutes: number;
  token: string; run: Run; setNotice: (value: string) => void; onTab: (tab: string) => void;
}) {
  const approval = approvals.find((row) => row.plan_id === plan.id && (row.status === "active" || row.status === "consumed" || row.status === "expired"));
  const requested = <Step done>Requested by {requester} · {timeOnly(plan.computed_at)}</Step>;
  const approve = () => run(async () => { await api(`/v1/plans/${plan.id}/approve`, { method: "POST", token }); setNotice(`Plan v${plan.version} is approved.`); });
  const generate = () => run(async () => {
    const created = await api<PurchaseOrder[]>(`/v1/plans/${plan.id}/purchase-orders`, { method: "POST", token, headers: { "Idempotency-Key": crypto.randomUUID() } });
    setNotice(`${created.length} purchase order draft${created.length === 1 ? "" : "s"} generated. Review and send them on the Orders tab.`);
  });
  if (plan.status === "stale") return <p className="text-sm text-muted-foreground">This plan is stale, so it can&apos;t be approved.{plan.stale_reason ? ` ${plan.stale_reason}` : ""}</p>;
  if (plan.status === "infeasible") return <p className="text-sm text-muted-foreground">There is no feasible plan to approve.</p>;
  if (plan.status === "feasible") {
    return (
      <>
        <ol>{requested}<Step done={false}>{canApprove ? "Your approval" : "Independent approver"}</Step></ol>
        {canApprove ? (
          <div className="mt-5">
            <Button className="w-full" onClick={() => void approve()}>Approve plan v{plan.version}</Button>
            <p className="mt-2 text-sm text-muted-foreground">Approves this exact version.</p>
            <p className="mt-1 text-sm text-muted-foreground">Approval expires {ttlMinutes % 60 === 0 ? `${ttlMinutes / 60} h` : `${ttlMinutes} min`} after it&apos;s given.</p>
          </div>
        ) : <p className="mt-5 text-sm text-muted-foreground">{approvalBlocked ?? "Only an organization admin or approver can approve this plan."}</p>}
      </>
    );
  }
  return (
    <>
      <ol>
        {requested}
        <Step done>Approved by {approval?.approver_email ?? "an approver"}{approval ? ` · ${timeOnly(approval.approved_at)}` : ""}{approval?.segregation_of_duties === "DEMO_ORG_SELF_APPROVAL_OVERRIDE" ? " · DEMO override" : ""}</Step>
      </ol>
      {approval?.status === "active" && (
        <div className="mt-5">
          <Button className="w-full" onClick={() => void generate()}>Generate POs</Button>
          <p className="mt-2 text-sm text-muted-foreground">Creates drafts. Sending is a separate step.</p>
          {approval.expires_at && <p className="mt-1 text-sm text-muted-foreground">Approval expires {when(approval.expires_at)}.</p>}
        </div>
      )}
      {approval?.status === "consumed" && <div className="mt-5 text-sm"><p className="text-muted-foreground">Purchase orders were generated from this approval.</p><button type="button" className={`mt-2 ${linkClass}`} onClick={() => onTab("orders")}>Review orders →</button></div>}
      {approval?.status === "expired" && <p className="mt-5 text-sm text-muted-foreground">This approval expired before purchase orders were generated.</p>}
    </>
  );
}

export type PlanTabProps = {
  mission: Mission; plans: Plan[]; approvals: Approval[]; quotes: Quote[]; suppliers: SupplierRow[]; continuity?: ContinuityView; disruptions: Disruption[];
  token: string; run: Run; setNotice: (value: string) => void; onTab: (tab: string) => void; onOptimize: () => void;
  canApprove: boolean; approvalBlocked: string | null; requester: string; showDemo: boolean; approvalTtlMinutes: number;
  busy: boolean; continuityRunning: boolean; eligibleCount: number; quoteCount: number;
};

export function PlanTab(props: PlanTabProps) {
  const { mission, plans, approvals, quotes, suppliers, token, run, setNotice, onTab, onOptimize, busy, eligibleCount, quoteCount } = props;
  const [comparing, setComparing] = useState(false);
  const [plan, previous] = plans;
  const total = useCountUp(plan && plan.status !== "infeasible" ? num(plan.total_cost) : 0);
  const demo = props.showDemo && <DemoControls missionId={mission.id} token={token} rows={suppliers} plan={plan} run={run} disruptions={props.disruptions} setNotice={setNotice} />;
  const continuity = <ContinuityPanel plan={plan} view={props.continuity} running={props.continuityRunning} onRun={() => void run(async () => {
    if (!plan) throw new Error("Create a feasible plan before running continuity analysis.");
    await api(`/v1/plans/${plan.id}/continuity`, { method: "POST", token });
    setNotice(`Continuity analysis queued for Plan v${plan.version}. All scenarios are explicitly HYPOTHETICAL.`);
  })} />;
  const missionFacts = (
    <RailSection title="Mission">
      <dl>
        <Fact label="Budget">{amount(mission.budget)}</Fact>
        {plan && plan.status !== "infeasible" && <Fact label="Remaining">{amount(plan.remaining_budget)}</Fact>}
        <Fact label="Deliver by">{day(mission.delivery_deadline)}</Fact>
        <Fact label="Destination">{mission.delivery_location}</Fact>
        {mission.max_supplier_share && <Fact label="Max share per supplier">{Math.round(num(mission.max_supplier_share) * 100)}%</Fact>}
        <Fact label="Disaster">{mission.emergency_event ? <button type="button" className={linkClass} onClick={() => onTab("context")}>View event →</button> : "—"}</Fact>
      </dl>
    </RailSection>
  );

  if (!plan) {
    return (
      <div className="grid gap-12 lg:grid-cols-[minmax(0,7fr)_minmax(0,3fr)]">
        <div className="space-y-8">
          <section>
            <h2 className="text-xl font-semibold">No plan yet</h2>
            <p className="mt-2 max-w-xl text-sm text-muted-foreground">{eligibleCount} of {quoteCount} submitted quote{quoteCount === 1 ? "" : "s"} {eligibleCount === 1 ? "is" : "are"} policy-eligible. {quoteCount === 0 ? "Waiting for supplier quotes." : eligibleCount === 0 ? "Waiting for evidence checks to make a quote eligible." : ""}</p>
            <Button className="mt-5" onClick={onOptimize} disabled={busy || eligibleCount === 0}>Run optimization</Button>
            <p className="mt-3 max-w-xl text-xs text-muted-foreground">The optimizer (PuLP / CBC) minimizes landed cost, meaning unit price × quantity plus per-supplier shipping, subject to exact coverage, inventory, delivery deadline, budget, and concentration.</p>
          </section>
          {continuity}
          {demo}
        </div>
        <aside>{missionFacts}</aside>
      </div>
    );
  }

  if (comparing && previous) return <CompareView latest={plan} previous={previous} approvals={approvals} onClose={() => setComparing(false)} />;

  const quotesById = new Map(quotes.map((quote) => [quote.id, quote]));
  const rows = supplierRows(plan, quotesById);
  const previousRows = previous ? supplierRows(previous, quotesById) : new Map<string, Row>();
  const shipping = addsUp(plan, rows);
  const comparable = Boolean(previous && previous.status !== "infeasible");
  const versus = comparable && shipping && addsUp(previous!, previousRows);
  const removed = comparable ? [...previousRows.values()].filter((row) => !rows.has(row.id)) : [];
  const revoked = previous && approvals.find((row) => row.plan_id === previous.id && row.status === "invalidated");
  const subtotal = (row?: Row) => (row && row.ship !== null ? row.items + row.ship : 0);
  const allTest = [...rows.values(), ...removed].every((row) => plan.policy?.suppliers?.[row.id]?.is_demo ?? previous?.policy?.suppliers?.[row.id]?.is_demo);
  const blocked = new Map<string, { quoteIds: string[]; rules: Set<string> }>();
  for (const row of plan.rejected_quotes) {
    // A withdrawn or expired quote already shows as a muted allocation row; list only live quotes here.
    if (!row.reason.startsWith("policy") || !row.supplier_id || quotesById.get(row.quote_id)?.status !== "submitted") continue;
    const entry = blocked.get(row.supplier_id) ?? { quoteIds: [], rules: new Set<string>() };
    entry.quoteIds.push(row.quote_id);
    row.rules?.forEach((rule) => entry.rules.add(rule));
    blocked.set(row.supplier_id, entry);
  }
  const removedReason = (supplierId: string) => quotes.some((quote) => quote.supplier_id === supplierId && quote.status === "withdrawn") ? "Withdrawn" : blocked.has(supplierId) ? "Not eligible" : "Not allocated";
  const lowestPrice = (item: string) => Math.min(...quotes.filter((quote) => quote.status === "submitted").flatMap((quote) => quote.lines.filter((line) => line.item === item).map((line) => num(line.unit_price))));
  const head = (label: string, right = true) => <TableHead className={right ? "text-right" : undefined}>{label}</TableHead>;
  const v = (plan_: Plan) => `v${plan_.version}`;

  return (
    <div className="grid gap-12 lg:grid-cols-[minmax(0,7fr)_minmax(0,3fr)]">
      <div className="min-w-0">
        <div className="flex flex-wrap items-baseline gap-3"><h2 className="text-xl font-semibold">Plan v{plan.version}</h2><PlanStatusText value={plan.status} /></div>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">{planSentence(plan, previous, revoked)}</p>
        {plan.status === "infeasible" ? (
          <div className="mt-6 max-w-2xl text-sm">
            <p className="text-warn">No feasible allocation{plan.binding_constraints.length ? `: the binding constraint is ${plan.binding_constraints.join(", ")}` : ""}.</p>
            <ul className="mt-2 space-y-1 text-muted-foreground">{plan.shortages.map((shortage) => <li key={shortage.item}>{shortage.item}: short {shortage.shortage} ({shortage.reason})</li>)}</ul>
          </div>
        ) : (
          <>
            <div className="mt-6 flex flex-wrap items-baseline gap-x-3">
              <span data-testid="plan-total" className="text-4xl font-semibold tracking-tight tabular">{amount(Math.abs(total - num(plan.total_cost)) < 0.005 ? plan.total_cost : Math.round(total))}</span>
              {comparable && plan.difference.cost_delta && <span className="text-lg text-muted-foreground tabular">{signedAmount(plan.difference.cost_delta)} vs {v(previous!)}</span>}
            </div>
            <p className="mt-1 text-base">{coverage(mission, plan)}</p>
            {plan.committed_cost && <p className="mt-1 text-sm text-muted-foreground">Committed on POs {money(plan.committed_cost)} · New spend {money(plan.new_spend ?? "0")}</p>}

            <section aria-label="Allocation" className="mt-10">
              <h3 className="text-base font-semibold">Allocation{allTest && <span className="font-normal text-muted-foreground"> · TEST suppliers</span>}</h3>
              <Table data-testid="allocation-table" className="mt-3">
                <TableHeader><TableRow>{head("Supplier", false)}{head(comparable ? `Qty (${v(previous!)} → ${v(plan)})` : "Qty")}{head("Unit")}{shipping && head("Ship")}{shipping && head(comparable ? `${v(plan)} subtotal` : "Subtotal")}{versus && head(`vs ${v(previous!)}`)}</TableRow></TableHeader>
                <TableBody>
                  {[...rows.values()].map((row) => {
                    const before = previousRows.get(row.id);
                    return (
                      <TableRow key={row.id}>
                        <TableCell className="whitespace-normal">{row.name}{row.orders.length > 0 && <span className="block text-xs text-muted-foreground">On {row.orders.join(", ")}</span>}</TableCell>
                        <TableCell className="text-right tabular">{comparable ? `${before?.units ?? 0} → ${row.units}` : row.units}</TableCell>
                        <TableCell className="text-right tabular">{row.unit ? money(row.unit) : "varies"}</TableCell>
                        {shipping && <TableCell className="text-right tabular">{amount(row.ship)}</TableCell>}
                        {shipping && <TableCell className="text-right tabular">{amount(subtotal(row))}</TableCell>}
                        {versus && <TableCell className="text-right tabular">{signedAmount(subtotal(row) - subtotal(before))}</TableCell>}
                      </TableRow>
                    );
                  })}
                  {removed.map((row) => (
                    <TableRow key={row.id} className="text-tertiary">
                      <TableCell className="whitespace-normal">{row.name}<span className="block text-xs">{removedReason(row.id)}</span></TableCell>
                      <TableCell className="text-right tabular">{row.units} → 0</TableCell>
                      <TableCell className="text-right tabular">{row.unit ? money(row.unit) : "varies"}</TableCell>
                      {shipping && <TableCell className="text-right tabular">{amount(row.ship)}</TableCell>}
                      {shipping && <TableCell className="text-right">—</TableCell>}
                      {versus && <TableCell className="text-right tabular">{signedAmount(-subtotal(row))}</TableCell>}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </section>
          </>
        )}

        {blocked.size > 0 && (
          <section aria-label="Not eligible" className="mt-10">
            <h3 className="text-base font-semibold">Not eligible</h3>
            <ul className="mt-2">
              {[...blocked.entries()].map(([supplierId, entry]) => {
                const line = quotesById.get(entry.quoteIds[0])?.lines[0];
                return (
                  <li key={supplierId} className="border-b py-3 last:border-0">
                    <div className="flex flex-wrap items-baseline justify-between gap-3">
                      <span>{supplierLabel(plan, supplierId)}</span>
                      <button type="button" className={linkClass} onClick={() => onTab("evidence")}>Review evidence →</button>
                    </div>
                    {line && <p className="mt-0.5 text-sm text-muted-foreground">{money(line.unit_price)} per unit{num(line.unit_price) <= lowestPrice(line.item) ? " · Lowest quote" : ""}</p>}
                    <p className="mt-0.5 text-sm text-muted-foreground">{[...entry.rules].map(humanize).join(" · ")}{entry.rules.size > 0 && " · "}<PolicyText value={plan.policy?.quotes?.[entry.quoteIds[0]]?.status} /></p>
                  </li>
                );
              })}
            </ul>
          </section>
        )}

        <div className="mt-10 flex flex-wrap items-center gap-x-6 gap-y-2">
          <button type="button" className={linkClass} onClick={() => onTab("audit")}>View activity →</button>
          <Button variant="text" size="sm" onClick={onOptimize} disabled={busy || eligibleCount === 0}>Run optimization</Button>
        </div>

        <div className="mt-10 space-y-10">
          {continuity}
          {demo}
        </div>
      </div>

      <aside className="min-w-0">
        <RailSection title="Approval">
          <ApprovalSection plan={plan} approvals={approvals} canApprove={props.canApprove} approvalBlocked={props.approvalBlocked} requester={props.requester} ttlMinutes={props.approvalTtlMinutes} token={token} run={run} setNotice={setNotice} onTab={onTab} />
        </RailSection>
        {missionFacts}
        {previous && (
          <RailSection title="Previous plan">
            <p className="text-sm text-muted-foreground"><span className="tabular">{v(previous)} · {previous.status === "infeasible" ? "—" : amount(previous.total_cost)}</span> · <PlanStatusText value={previous.status} /></p>
            {revoked && <p className="mt-1 text-sm text-muted-foreground">Approval revoked{revoked.invalidated_at ? ` at ${timeOnly(revoked.invalidated_at)}` : ""}</p>}
            <button type="button" className={`mt-3 ${linkClass}`} onClick={() => setComparing(true)}>Compare {v(previous)} and {v(plan)} →</button>
          </RailSection>
        )}
      </aside>
    </div>
  );
}

// Read-only drawer for the header's "Explain changes". Built from the plan's recorded reasons and evidence.
export function ExplainDrawer({ open, onOpenChange, plan, previous, suppliers }: { open: boolean; onOpenChange: (open: boolean) => void; plan: Plan; previous?: Plan; suppliers: SupplierRow[] }) {
  const decisions = [...Object.values(plan.policy?.suppliers ?? {}), ...Object.values(plan.policy?.quotes ?? {})].flatMap((row) => row.decisions);
  // Sources are the findings that affect eligibility, not every warning.
  const evidenceIds = new Set(decisions.filter((decision) => decision.status === "NEEDS_REVIEW" || decision.status === "BLOCK").flatMap((decision) => decision.evidence_ids));
  const records = [...new Map(suppliers.flatMap((row) => row.evidence_history).filter((record) => evidenceIds.has(record.id)).map((record) => [record.id, record])).values()];
  const changed = (plan.difference.supplier_delta ?? []).filter((row) => row.units_before !== row.units_after);
  const label = (type: string, provider: string) => EVIDENCE_ORDER.find(([key]) => key === type)?.[1] ?? provider;
  return (
    <Drawer open={open} onOpenChange={onOpenChange} title="Explain changes" subtitle="From the plan record · read-only">
      <section>
        <h3 className="text-sm font-semibold">What changed in plan v{plan.version}</h3>
        <ul className="mt-2 space-y-1.5 text-sm">
          {(plan.difference.why ?? []).map((reason) => <li key={reason}>{reason}</li>)}
          {changed.map((row) => <li key={row.supplier_id}>{row.supplier}: {row.units_before} → {row.units_after} units</li>)}
          {previous && plan.difference.cost_delta && <li>Total {signedAmount(plan.difference.cost_delta, true)} vs v{previous.version} ({money(previous.total_cost)} → {money(plan.total_cost)}).</li>}
        </ul>
      </section>
      <section className="mt-8">
        <h3 className="text-sm font-semibold">Sources</h3>
        {records.length === 0 ? <p className="mt-2 text-sm text-muted-foreground">No evidence records were involved in this change.</p> : (
          <ul className="mt-2">
            {records.map((record) => (
              <li key={record.id} className="border-b py-2.5 text-sm last:border-0">
                <p>{label(record.type, record.provider)} evidence record · <Provenance value={record.provenance} />{record.retrieved_at && <span className="text-muted-foreground"> · retrieved {clock(record.retrieved_at)}</span>}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">{record.subject_name}: {record.summary}</p>
              </li>
            ))}
          </ul>
        )}
      </section>
      <p className="mt-8 text-xs text-muted-foreground">Assembled by fixed rules from the reasons and evidence ReliefMesh recorded, not written by AI.</p>
    </Drawer>
  );
}
