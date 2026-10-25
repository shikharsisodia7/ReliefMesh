"use client";

import { AlertTriangle, ArrowRight, Download, Hash, Link2, Play, ShieldCheck, Zap } from "lucide-react";
import { useState } from "react";

import { PlanStatusText, Provenance, StatusText, ago, money, when } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { API_BASE_URL, api } from "@/lib/api";
import type { Approval, AuditEvent, AuditVerification, Disruption, Job, Mission, Notification, Payment, Plan, PurchaseOrder, SupplierRow } from "@/lib/types";

type Run = (operation: () => Promise<void>) => Promise<void>;

const PALETTE = ["#00d4ff", "#ffb800", "#26de81", "#a78bfa", "#ff9f43", "#f472b6", "#60a5fa"];

export function colorFor(order: string[], supplierId: string) {
  const index = order.indexOf(supplierId);
  return PALETTE[(index < 0 ? order.length : index) % PALETTE.length];
}

function supplierName(plan: Plan, supplierId: string) {
  const row = plan.policy?.suppliers?.[supplierId];
  return row?.legal_name || row?.email || supplierId.slice(0, 8);
}

function shares(plan: Plan) {
  const total = plan.allocations.reduce((sum, row) => sum + row.quantity, 0) || 1;
  const map = new Map<string, { units: number; cost: number }>();
  for (const row of plan.allocations) {
    const entry = map.get(row.supplier_id) ?? { units: 0, cost: 0 };
    entry.units += row.quantity;
    entry.cost += Number(row.line_cost);
    map.set(row.supplier_id, entry);
  }
  return [...map.entries()].map(([supplierId, value]) => ({ supplierId, ...value, share: value.units / total }));
}

export function AllocationBar({ plan, order }: { plan: Plan; order: string[] }) {
  if (plan.status === "infeasible") return <div className="h-3 rounded bg-critical/20" aria-label="No feasible allocation" />;
  return (
    <div className="flex h-3 overflow-hidden rounded bg-muted" role="img" aria-label={`Allocation for plan v${plan.version}`}>
      {shares(plan).map((entry) => <div key={entry.supplierId} style={{ width: `${entry.share * 100}%`, background: colorFor(order, entry.supplierId) }} title={`${supplierName(plan, entry.supplierId)} ${Math.round(entry.share * 100)}%`} />)}
    </div>
  );
}

function etaHours(plan: Plan) {
  if (!plan.latest_delivery) return null;
  return Math.max(0, Math.round((new Date(plan.latest_delivery).getTime() - new Date(plan.computed_at).getTime()) / 3_600_000));
}

export function OptimizerPanel({ mission, plan, eligibleCount, quoteCount, onOptimize, busy }: { mission: Mission; plan?: Plan; eligibleCount: number; quoteCount: number; onOptimize: () => void; busy: boolean }) {
  return (
    <section aria-label="Optimization" className="rounded-xl border bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-muted-foreground">Mixed-integer optimizer (PuLP / CBC)</h2>
          <p className="mt-1 text-sm"><span className="font-mono text-telemetry">{eligibleCount}</span> of {quoteCount} submitted quote{quoteCount === 1 ? "" : "s"} policy-eligible · latest plan: {plan ? `v${plan.version} ${plan.status}` : "not calculated"}</p>
        </div>
        <div className="text-right"><Button onClick={onOptimize} disabled={busy || eligibleCount === 0}><Play className="size-3.5" />Run optimization</Button>{eligibleCount === 0 && <p className="mt-1 max-w-56 text-[11px] text-muted-foreground">{quoteCount === 0 ? "Waiting for supplier quotes." : "Waiting for evidence checks to make a quote eligible."} A plan can be generated after eligible quotes are received.</p>}</div>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
        <div className="rounded border p-2"><dt className="text-muted-foreground">Budget ceiling</dt><dd className="font-mono text-base text-telemetry">{money(mission.budget)}</dd></div>
        <div className="rounded border p-2"><dt className="text-muted-foreground">Deliver by</dt><dd className="font-mono">{when(mission.delivery_deadline)}</dd></div>
        <div className="rounded border p-2"><dt className="text-muted-foreground">Max supplier share</dt><dd className="font-mono">{mission.max_supplier_share ? `${Math.round(Number(mission.max_supplier_share) * 100)}%` : "none"}</dd></div>
        <div className="rounded border p-2"><dt className="text-muted-foreground">Coverage</dt><dd className="font-mono">exact quantity · {mission.single_source_only ? "single source" : "multi-source"}</dd></div>
      </dl>
      <p className="mt-2 text-[11px] text-tertiary">Minimizes landed cost (unit price × quantity + per-supplier shipping) subject to exact coverage, inventory, delivery deadline, budget, and concentration. Binding constraints are reported with each plan.</p>
    </section>
  );
}

const DISRUPTIONS = [
  { kind: "withdraw", label: "Supplier withdraws quote" },
  { kind: "reduce_inventory", label: "Supplier cuts inventory" },
  { kind: "raise_price", label: "Supplier raises price" },
  { kind: "delay_eta", label: "Supplier delays delivery" },
  { kind: "block_supplier", label: "Policy blocks supplier" },
] as const;

export function DisruptionConsole({ missionId, token, rows, plan, run, disruptions, setNotice }: { missionId: string; token: string; rows: SupplierRow[]; plan?: Plan; run: Run; disruptions: Disruption[]; setNotice: (value: string) => void }) {
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<(typeof DISRUPTIONS)[number]["kind"]>("withdraw");
  const allocated = new Set(plan?.allocations.map((row) => row.supplier_id));
  const candidates = rows.filter((row) => kind === "block_supplier" || row.supplier.is_demo);
  const defaultSupplier = candidates.find((row) => allocated.has(row.supplier.id))?.supplier.id ?? candidates[0]?.supplier.id ?? "";
  const [supplierId, setSupplierId] = useState("");
  const [value, setValue] = useState("");
  const chosen = supplierId && candidates.some((row) => row.supplier.id === supplierId) ? supplierId : defaultSupplier;
  const last = disruptions[0];
  return (
    <section aria-label="Disruption control" className="rounded-xl border border-critical/40 bg-critical/5 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-critical">Judge control</h2>
          <p className="text-xs text-muted-foreground">Mutates persisted quote or policy state through the same code path a supplier edit uses. Quote changes are limited to labeled TEST suppliers.</p>
        </div>
        <Button className="h-11 bg-critical px-5 text-base font-bold tracking-wide text-white hover:bg-critical/85" onClick={() => setOpen(!open)}><Zap className="size-4" />DISRUPT SUPPLY CHAIN</Button>
      </div>
      {open && (
        <form className="mt-4 grid gap-3 sm:grid-cols-[1fr_1fr_160px_auto] sm:items-end" onSubmit={(event) => { event.preventDefault(); void run(async () => {
          const body: Record<string, unknown> = { kind, supplier_id: chosen };
          if (kind === "reduce_inventory" && value) body.quantity = Number(value);
          if (kind === "raise_price" && value) body.unit_price = Number(value).toFixed(2);
          if (kind === "delay_eta" && value) body.delay_hours = Number(value);
          if (kind === "block_supplier") body.reason = value || "Blocked during a supply-chain disruption drill";
          const result = await api<Disruption>(`/v1/missions/${missionId}/disruptions`, { method: "POST", token, body: JSON.stringify(body) });
          setNotice(`${result.summary}. Plan invalidated; autonomous replanning job ${result.job_id?.slice(0, 8)} queued.`);
          setOpen(false); setValue("");
        }); }}>
          <div><Label htmlFor="disruption-kind">Disruption</Label><select id="disruption-kind" className="mt-1 h-8 w-full rounded-lg border bg-background px-2 text-sm" value={kind} onChange={(event) => setKind(event.target.value as typeof kind)}>{DISRUPTIONS.map((option) => <option key={option.kind} value={option.kind}>{option.label}</option>)}</select></div>
          <div><Label htmlFor="disruption-supplier">Supplier</Label><select id="disruption-supplier" className="mt-1 h-8 w-full rounded-lg border bg-background px-2 text-sm" value={chosen} onChange={(event) => setSupplierId(event.target.value)}>{candidates.map((row) => <option key={row.supplier.id} value={row.supplier.id}>{row.supplier.legal_name ?? row.supplier.email}{row.supplier.is_demo ? " (TEST)" : ""}{allocated.has(row.supplier.id) ? " · allocated" : ""}</option>)}</select></div>
          <div><Label htmlFor="disruption-value">{kind === "reduce_inventory" ? "New quantity" : kind === "raise_price" ? "New unit price" : kind === "delay_eta" ? "Delay (hours)" : kind === "block_supplier" ? "Reason" : "—"}</Label><Input id="disruption-value" className="mt-1" disabled={kind === "withdraw"} value={value} onChange={(event) => setValue(event.target.value)} placeholder={kind === "reduce_inventory" ? "auto: ÷3" : kind === "raise_price" ? "auto: +35%" : kind === "delay_eta" ? "72" : ""} /></div>
          <Button type="submit" variant="primary" disabled={!chosen}>Apply disruption</Button>
        </form>
      )}
      {last && <p className="mt-3 text-xs"><span className="font-mono text-critical">LAST</span> {last.summary} · {ago(last.created_at)}</p>}
    </section>
  );
}

export function PlanComparison({ plans, approvals, order }: { plans: Plan[]; approvals: Approval[]; order: string[] }) {
  const [latest, previous] = plans;
  if (!latest || !previous) return null;
  const invalidated = approvals.find((approval) => approval.plan_id === previous.id && approval.status === "invalidated");
  const delta = latest.difference.cost_delta;
  const column = (plan: Plan, label: string) => (
    <div className={`rounded-lg border p-3 ${plan.status === "stale" ? "opacity-75" : "border-live/40"}`}>
      <div className="flex items-center justify-between"><span className="font-mono text-xs text-muted-foreground">{label}</span><PlanStatusText value={plan.status} /></div>
      <p className="mt-1 text-xl font-semibold">PLAN V{plan.version}</p>
      <AllocationBar plan={plan} order={order} />
      <ul className="mt-2 space-y-0.5 text-sm">
        {plan.status === "infeasible" ? plan.shortages.map((row) => <li key={row.item} className="text-critical">{row.item}: short {row.shortage} ({row.reason})</li>) : shares(plan).map((entry) => <li key={entry.supplierId} className="flex justify-between gap-2"><span className="flex items-center gap-1.5 truncate"><span className="inline-block size-2 rounded-sm" style={{ background: colorFor(order, entry.supplierId) }} />{supplierName(plan, entry.supplierId)}</span><span className="font-mono">{Math.round(entry.share * 100)}% · {entry.units}u</span></li>)}
      </ul>
      <p className="mt-2 font-mono text-lg text-telemetry">{plan.status === "infeasible" ? "—" : money(plan.total_cost)}</p>
      <p className="font-mono text-xs text-muted-foreground">{etaHours(plan) !== null ? `${etaHours(plan)}h to last delivery` : ""}</p>
    </div>
  );
  return (
    <section aria-label="Plan comparison" className="rounded-xl border bg-card p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-[0.16em] text-muted-foreground">Recovery: before → after</h2>
      <div className="grid items-stretch gap-3 md:grid-cols-[1fr_auto_1fr]">
        {column(previous, "OLD PLAN")}
        <div className="hidden items-center md:flex"><ArrowRight className="size-6 text-live" /></div>
        {column(latest, "NEW PLAN")}
      </div>
      <div className="mt-3 grid gap-3 md:grid-cols-3">
        <div className="rounded border p-2"><p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Why it changed</p><ul className="mt-1 list-disc pl-4 text-sm">{(latest.difference.why?.length ? latest.difference.why : [latest.trigger]).map((reason) => <li key={reason}>{reason}</li>)}</ul></div>
        <div className="rounded border p-2"><p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Cost delta</p><p className={`mt-1 font-mono text-2xl ${delta?.startsWith("-") ? "text-ok" : "text-telemetry"}`}>{delta ? `${delta.startsWith("-") ? "−" : "+"}${money(delta.replace(/^[+-]/, ""))}` : "n/a"}</p></div>
        <div className="rounded border p-2"><p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Approval</p>
          {invalidated ? <p className="mt-1 text-sm"><span className="font-mono text-critical">INVALIDATED</span> · v{previous.version} approval for {money(invalidated.amount)}: {invalidated.invalidation_reason}</p> : <p className="mt-1 text-sm text-muted-foreground">Prior plan was not approved.</p>}
          {latest.status === "feasible" && <p className="mt-1 text-sm font-medium text-telemetry">New human approval required for v{latest.version}.</p>}
          {latest.status === "approved" && <p className="mt-1 text-sm text-ok">v{latest.version} re-approved.</p>}
        </div>
      </div>
      {latest.difference.supplier_delta && latest.difference.supplier_delta.length > 0 && (
        <table className="mt-3 w-full text-xs"><thead><tr className="text-left text-muted-foreground"><th className="py-1 font-medium">Supplier delta</th><th className="font-medium">Units</th><th className="font-medium">Cost</th></tr></thead>
          <tbody>{latest.difference.supplier_delta.map((row) => <tr key={row.supplier_id} className="border-t border-border/60"><td className="py-1">{row.supplier}</td><td className="font-mono">{row.units_before} → {row.units_after}</td><td className="font-mono">{money(row.cost_before)} → {money(row.cost_after)}</td></tr>)}</tbody>
        </table>
      )}
    </section>
  );
}

export function PlanVersions({ plans, approvals, token, run, setNotice, order, isAdmin, approvalBlocked }: { plans: Plan[]; approvals: Approval[]; token: string; run: Run; setNotice: (value: string) => void; order: string[]; isAdmin: boolean; approvalBlocked?: string | null }) {
  return (
    <section aria-label="Plan versions" className="rounded-xl border bg-card p-4">
      <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-muted-foreground">Plan versions</h2>
      <p className="mb-3 text-xs text-tertiary">Each version is immutable evidence (inputs, policy fingerprint, hash). A stale plan cannot be approved; an approval authorizes exactly one plan version, expires, and is single-use.</p>
      {plans.length === 0 ? <p className="text-sm text-muted-foreground">Run optimization after suppliers submit quotes.</p> : (
        <div className="space-y-3">
          {plans.map((plan) => {
            const approval = approvals.find((row) => row.plan_id === plan.id);
            return (
              <article key={plan.id} className="rounded-lg border p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-2"><h3 className="font-semibold">Plan v{plan.version}</h3><PlanStatusText value={plan.status} /><span className="font-mono text-[10px] text-tertiary">{plan.trigger} · {ago(plan.computed_at)}</span></div>
                    <p className="mt-0.5 text-sm text-muted-foreground">Total {money(plan.total_cost)} · Shipping {money(plan.shipping_cost)} · Remaining {money(plan.remaining_budget)}{plan.committed_cost ? ` · Committed on POs ${money(plan.committed_cost)} · New spend ${money(plan.new_spend ?? "0")}` : ""}{plan.difference.total_cost_before ? ` · Prior total ${money(plan.difference.total_cost_before)}` : ""}</p>
                  </div>
                  <div className="flex gap-2">
                    {plan.status === "feasible" && !isAdmin && approvalBlocked && <span className="max-w-xs text-right text-xs text-telemetry">{approvalBlocked}</span>}
                    {plan.status === "feasible" && isAdmin && <Button size="sm" onClick={() => void run(async () => { await api(`/v1/plans/${plan.id}/approve`, { method: "POST", token }); setNotice(`Plan v${plan.version} is approved.`); })}><ShieldCheck className="size-3.5" />Approve plan</Button>}
                    {plan.status === "approved" && approval?.status === "active" && <Button size="sm" onClick={() => void run(async () => { const created = await api<PurchaseOrder[]>(`/v1/plans/${plan.id}/purchase-orders`, { method: "POST", token, headers: { "Idempotency-Key": crypto.randomUUID() } }); setNotice(`${created.length} purchase order draft${created.length === 1 ? "" : "s"} generated. Confirm each send below.`); })}>Generate POs</Button>}
                  </div>
                </div>
                <div className="mt-2"><AllocationBar plan={plan} order={order} /></div>
                {plan.status === "infeasible" ? (
                  <ul className="mt-2 list-disc pl-5 text-sm text-critical">{plan.shortages.map((shortage) => <li key={shortage.item}>{shortage.item}: shortage {shortage.shortage}; constraint: {shortage.reason}</li>)}</ul>
                ) : (
                  <ul className="mt-2 grid gap-0.5 text-sm">{plan.allocations.map((allocation) => <li key={`${allocation.supplier_id}-${allocation.item}-${allocation.po_number ?? "new"}`} className="flex items-center gap-1.5"><span className="inline-block size-2 rounded-sm" style={{ background: colorFor(order, allocation.supplier_id) }} />{supplierName(plan, allocation.supplier_id)}: {allocation.quantity} {allocation.item} × {money(allocation.unit_price)} = {money(allocation.line_cost)}{allocation.committed && <span className="rounded border px-1 font-mono text-[10px] text-muted-foreground" title="Already on an active purchase order; kept fixed while replanning">on {allocation.po_number}</span>}</li>)}</ul>
                )}
                {plan.rejected_quotes.some((row) => row.reason.startsWith("policy")) && (
                  <details className="mt-2 text-xs"><summary className="cursor-pointer text-telemetry">Withheld by policy ({plan.rejected_quotes.filter((row) => row.reason.startsWith("policy")).length})</summary>
                    <ul className="mt-1 space-y-1">{plan.rejected_quotes.filter((row) => row.reason.startsWith("policy")).map((row) => <li key={row.quote_id}><span className="font-medium">{row.supplier_id ? supplierName(plan, row.supplier_id) : row.supplier_email}</span>: {row.rules?.join(", ")}</li>)}</ul>
                  </details>
                )}
                <p className="mt-2 flex flex-wrap items-center gap-x-3 font-mono text-[10px] text-tertiary"><span className="inline-flex items-center gap-1"><Hash className="size-3" />{plan.plan_hash?.slice(0, 16)}</span>{plan.binding_constraints.length > 0 && <span>binding: {plan.binding_constraints.join(", ")}</span>}{approval && <span>approval {approval.status}{approval.expires_at ? ` · expires ${when(approval.expires_at)}` : ""}</span>}{plan.stale_reason && <span className="text-warn">stale: {plan.stale_reason}</span>}</p>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

async function downloadPdf(orderId: string, poNumber: string, token: string) {
  const response = await fetch(`${API_BASE_URL}/v1/purchase-orders/${orderId}/pdf`, { headers: { Authorization: `Bearer ${token}` } });
  if (!response.ok) throw new Error("Could not download the purchase order PDF");
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = `${poNumber}.pdf`;
  link.click();
  URL.revokeObjectURL(url);
}

export function OrdersPanel({ orders, token, run, setNotice }: { orders: PurchaseOrder[]; token: string; run: Run; setNotice: (value: string) => void }) {
  return (
    <section aria-label="Purchase orders" className="rounded-xl border bg-card p-4">
      <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-muted-foreground">Purchase orders</h2>
      <p className="mb-3 text-xs text-tertiary">Drafts are not binding. Sending requires a separate confirmation. Drafts from a plan that goes stale are voided automatically.</p>
      {orders.length === 0 ? <p className="text-sm text-muted-foreground">No purchase orders generated.</p> : (
        <div className="space-y-2">
          {orders.map((order) => (
            <div key={order.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3">
              <div><p className="font-mono font-medium">{order.po_number}</p><p className="text-sm text-muted-foreground">{order.supplier_email} · plan v{order.plan_version} · {money(order.subtotal)}{order.plan_stale ? " · plan since replaced" : ""}</p></div>
              <div className="flex items-center gap-2">
                <span className="rounded border px-1.5 py-0.5 font-mono text-[10px] uppercase">{order.status}</span>
                <Button size="sm" variant="text" aria-label={`Download ${order.po_number} PDF`} onClick={() => void run(() => downloadPdf(order.id, order.po_number, token))}><Download className="size-3.5" /></Button>
                {order.status === "draft" && <Button size="sm" onClick={() => void run(async () => { await api(`/v1/purchase-orders/${order.id}/send`, { method: "POST", token, body: JSON.stringify({ confirm: true }) }); setNotice(`${order.po_number} sent to supplier.`); })}>Confirm &amp; send</Button>}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export function PaymentsPanel({ payments }: { payments: Payment[] }) {
  if (payments.length === 0) return null;
  return (
    <section aria-label="Machine payments" className="rounded-xl border bg-card p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-muted-foreground">Machine payments · x402 on Solana devnet</h2>
        <span className="flex gap-3"><Provenance value="SANDBOX" /><span className="text-xs font-medium tracking-wide text-muted-foreground">DEVNET · TEST PAYMENT</span></span>
      </div>
      <p className="mb-2 text-xs text-tertiary">HTTP 402 → signed USDC transfer → facilitator verification and on-chain settlement → evidence unlocked. Devnet test USDC only: this proves machine-to-machine payment works. No supplier is paid and procurement funds never move through x402.</p>
      <ul className="space-y-2">
        {payments.map((payment) => (
          <li key={payment.id} className="rounded border p-2 text-xs">
            <div className="flex flex-wrap items-center justify-between gap-2"><span className="font-medium">Signed dossier: {payment.subject_name}</span><span className="font-mono text-telemetry">{payment.amount_display} · {payment.network_label}</span></div>
            <p className="mt-1 font-mono text-[11px] text-muted-foreground">{payment.payer.slice(0, 6)}… → {payment.pay_to.slice(0, 6)}… · {payment.scheme} · {payment.verified ? "settled" : payment.status} · {when(payment.created_at)}</p>
            <a className="font-mono text-[11px] text-live hover:underline" href={payment.explorer_url} target="_blank" rel="noreferrer">tx {payment.transaction.slice(0, 20)}… ↗</a>
            <span className="ml-2 font-mono text-[10px] text-tertiary">dossier sha256 {payment.dossier_sha256.slice(0, 12)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

// Only notifications that need attention carry a word; red stays reserved for real errors.
const severityWord: Record<string, string> = { warning: "Warning", critical: "Critical" };

export function Timeline({ notifications, audit, verification, jobs }: { notifications: Notification[]; audit: AuditEvent[]; verification?: AuditVerification; jobs: Job[] }) {
  const active = jobs.filter((job) => job.status === "queued" || job.status === "running");
  return (
    <section aria-label="Mission timeline" className="rounded-xl border bg-card p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-muted-foreground">Timeline &amp; audit</h2>
        {verification && (
          <span className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 font-mono text-[11px] ${verification.valid ? "border-ok/40 text-ok" : "border-critical/50 text-critical"}`} title="SHA-256 hash chain over canonical audit fields">
            <Link2 className="size-3" />{verification.valid ? `hash chain verified · ${verification.length} events · ${verification.head_hash?.slice(0, 10)}` : `CHAIN BROKEN at #${verification.broken_at}: ${verification.reason}`}
          </span>
        )}
      </div>
      {active.length > 0 && <div className="mt-2 space-y-1">{active.map((job) => <p key={job.id} className="text-sm text-muted-foreground">{job.type.replace(/_/g, " ")} {job.status} · attempt {job.attempts}/{job.max_attempts}</p>)}</div>}
      {jobs.filter((job) => job.status === "failed").slice(0, 2).map((job) => <p key={job.id} className="mt-1 flex items-center gap-2 text-sm text-critical"><AlertTriangle className="size-3.5" />{job.type} failed: {job.last_error}</p>)}
      <div className="mt-3 grid gap-4 lg:grid-cols-2">
        <ol className="max-h-96 space-y-2 overflow-y-auto pr-1" aria-label="Notifications">
          {notifications.length === 0 && <li className="text-sm text-muted-foreground">No notifications yet.</li>}
          {notifications.map((notification) => <li key={notification.id} className="text-sm"><span>{severityWord[notification.severity] && <StatusText tone="warn" value={notification.severity}>{severityWord[notification.severity]} · </StatusText>}<span>{notification.message}</span><span className="block font-mono text-[10px] text-tertiary">{when(notification.created_at)}</span></span></li>)}
        </ol>
        <ol className="max-h-96 space-y-1 overflow-y-auto pr-1 font-mono text-[11px]" aria-label="Audit events">
          {[...audit].reverse().map((event) => <li key={event.id} className="flex gap-2"><span className="w-7 shrink-0 text-right text-tertiary">#{event.sequence}</span><span className="min-w-0 flex-1 truncate">{event.action}</span><span className="text-tertiary" title={`prev ${event.previous_hash}`}>{event.event_hash.slice(0, 8)}</span></li>)}
        </ol>
      </div>
      <p className="mt-2 text-[11px] text-tertiary">Tamper-evident application audit chaining (each event hashes its predecessor). Not blockchain storage. <Provenance value="LIVE" className="ml-1" /> data is fetched at the time shown.</p>
    </section>
  );
}
