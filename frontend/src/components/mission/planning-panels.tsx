"use client";

import { AlertTriangle, Hash, Link2, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { Dialog } from "@/components/patterns/overlays";
import { PlanStatusText, Provenance, StatusText, ago, money, signedAmount, when } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import type { Approval, AuditEvent, AuditVerification, Disruption, Job, Notification, Payment, Plan, PurchaseOrder, SupplierRow } from "@/lib/types";
import { cn } from "@/lib/utils";

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

const DISRUPTIONS = [
  { kind: "withdraw", label: "Supplier withdraws quote" },
  { kind: "reduce_inventory", label: "Supplier cuts inventory" },
  { kind: "raise_price", label: "Supplier raises price" },
  { kind: "delay_eta", label: "Supplier delays delivery" },
  { kind: "block_supplier", label: "Policy blocks supplier" },
] as const;

// Demo-only section at the bottom of the Plan tab. The dialog changes persisted quote or policy state
// through the same code path a real supplier edit uses.
export function DemoControls({ missionId, token, rows, plan, run, disruptions, setNotice }: { missionId: string; token: string; rows: SupplierRow[]; plan?: Plan; run: Run; disruptions: Disruption[]; setNotice: (value: string) => void }) {
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<(typeof DISRUPTIONS)[number]["kind"]>("withdraw");
  const allocated = new Set(plan?.allocations.map((row) => row.supplier_id));
  const candidates = rows.filter((row) => kind === "block_supplier" || row.supplier.is_demo);
  const defaultSupplier = candidates.find((row) => allocated.has(row.supplier.id))?.supplier.id ?? candidates[0]?.supplier.id ?? "";
  const [supplierId, setSupplierId] = useState("");
  const [value, setValue] = useState("");
  const chosen = supplierId && candidates.some((row) => row.supplier.id === supplierId) ? supplierId : defaultSupplier;
  const last = disruptions[0];
  const valueLabel = kind === "reduce_inventory" ? "New quantity" : kind === "raise_price" ? "New unit price" : kind === "delay_eta" ? "Delay (hours)" : "Reason";
  const select = "mt-1.5 h-9 w-full rounded-md border bg-background px-3 text-sm";
  const apply = () => run(async () => {
    const body: Record<string, unknown> = { kind, supplier_id: chosen };
    if (kind === "reduce_inventory" && value) body.quantity = Number(value);
    if (kind === "raise_price" && value) body.unit_price = Number(value).toFixed(2);
    if (kind === "delay_eta" && value) body.delay_hours = Number(value);
    if (kind === "block_supplier") body.reason = value || "Blocked during a supply-chain disruption drill";
    const result = await api<Disruption>(`/v1/missions/${missionId}/disruptions`, { method: "POST", token, body: JSON.stringify(body) });
    setNotice(`${result.summary}. Plan invalidated; autonomous replanning job ${result.job_id?.slice(0, 8)} queued.`);
    setOpen(false); setValue("");
  });
  return (
    <section aria-label="Demo controls" className="border-t pt-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h3 className="text-base font-semibold">Demo controls</h3>
          <p className="mt-1 max-w-xl text-sm text-muted-foreground">Change saved quote or policy state through the same code path a supplier edit uses. Quote changes are limited to labeled TEST suppliers.</p>
          {last && <p className="mt-2 text-sm text-muted-foreground">Last: {last.summary} · {ago(last.created_at)}</p>}
        </div>
        <Button variant="secondary" onClick={() => setOpen(true)}>Disrupt supply chain</Button>
      </div>
      <Dialog open={open} onOpenChange={setOpen} title="Disrupt supply chain" subtitle="Demo only" footer={<Button type="submit" form="disruption-form" disabled={!chosen}>Apply disruption</Button>}>
        <form id="disruption-form" className="space-y-4" onSubmit={(event) => { event.preventDefault(); void apply(); }}>
          <div><Label htmlFor="disruption-kind">Disruption</Label><select id="disruption-kind" className={select} value={kind} onChange={(event) => setKind(event.target.value as typeof kind)}>{DISRUPTIONS.map((option) => <option key={option.kind} value={option.kind}>{option.label}</option>)}</select></div>
          <div><Label htmlFor="disruption-supplier">Supplier</Label><select id="disruption-supplier" className={select} value={chosen} onChange={(event) => setSupplierId(event.target.value)}>{candidates.map((row) => <option key={row.supplier.id} value={row.supplier.id}>{row.supplier.legal_name ?? row.supplier.email}{row.supplier.is_demo ? " (TEST)" : ""}{allocated.has(row.supplier.id) ? " · allocated" : ""}</option>)}</select></div>
          {kind !== "withdraw" && <div><Label htmlFor="disruption-value">{valueLabel}</Label><Input id="disruption-value" className="mt-1.5" value={value} onChange={(event) => setValue(event.target.value)} placeholder={kind === "reduce_inventory" ? "auto: ÷3" : kind === "raise_price" ? "auto: +35%" : kind === "delay_eta" ? "72" : ""} /></div>}
          <p className="text-muted-foreground">This changes saved data, so the current plan goes stale and ReliefMesh replans.</p>
        </form>
      </Dialog>
    </section>
  );
}

// Full-width, side-by-side view of the previous and current plan. Changed cells are marked by weight, not color.
export function CompareView({ latest, previous, approvals, onClose }: { latest: Plan; previous: Plan; approvals: Approval[]; onClose: () => void }) {
  const invalidated = approvals.find((approval) => approval.plan_id === previous.id && approval.status === "invalidated");
  const rows = latest.difference.previous_plan_id === previous.id ? latest.difference.supplier_delta ?? [] : [];
  const delta = latest.difference.cost_delta;
  const column = (plan: Plan, label: string, side: "before" | "after") => (
    <div>
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <div className="mt-1 flex items-baseline gap-3"><h3 className="text-lg font-semibold">v{plan.version}</h3><PlanStatusText value={plan.status} /></div>
      <table className="mt-4 w-full text-sm">
        <thead><tr className="border-b text-left text-xs text-muted-foreground"><th className="py-2 font-medium">Supplier</th><th className="py-2 text-right font-medium">Units</th><th className="py-2 text-right font-medium">Items cost</th></tr></thead>
        <tbody>
          {rows.map((row) => {
            const units = side === "before" ? row.units_before : row.units_after;
            const changed = row.units_before !== row.units_after;
            return (
              <tr key={row.supplier_id} className={cn("border-b", changed && "font-semibold")}>
                <td className="py-2.5">{row.supplier}</td>
                <td className="py-2.5 text-right tabular">{units}</td>
                <td className="py-2.5 text-right tabular">{money(side === "before" ? row.cost_before : row.cost_after)}</td>
              </tr>
            );
          })}
          <tr><td className="py-2.5 text-muted-foreground">Total with shipping</td><td /><td className="py-2.5 text-right font-medium tabular">{plan.status === "infeasible" ? "—" : money(plan.total_cost)}</td></tr>
        </tbody>
      </table>
    </div>
  );
  return (
    <section aria-label="Plan comparison" data-testid="compare-view">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold">Compare v{previous.version} and v{latest.version}</h2>
        <Button variant="text" onClick={onClose}>Back to plan</Button>
      </div>
      <div className="mt-6 grid gap-12 md:grid-cols-2">
        {column(previous, "Previous plan", "before")}
        {column(latest, "Current plan", "after")}
      </div>
      <dl className="mt-10 grid max-w-3xl gap-x-6 gap-y-4 text-sm sm:grid-cols-[160px_1fr]">
        <dt className="text-muted-foreground">Cost change</dt>
        <dd><span className="text-base font-semibold tabular">{delta ? signedAmount(delta, true) : "—"}</span></dd>
        <dt className="text-muted-foreground">Why it changed</dt>
        <dd><ul className="space-y-1">{(latest.difference.why?.length ? latest.difference.why : [latest.trigger]).map((reason) => <li key={reason}>{reason}</li>)}</ul></dd>
        <dt className="text-muted-foreground">Approval</dt>
        <dd>{invalidated ? <><span className="font-medium">Approval revoked</span> · v{previous.version} approval for {money(invalidated.amount)}: {invalidated.invalidation_reason}</> : <span className="text-muted-foreground">Plan v{previous.version} was not approved.</span>}</dd>
      </dl>
    </section>
  );
}

export function PlanVersions({ plans, approvals, token, run, setNotice, order, isAdmin, approvalBlocked }: { plans: Plan[]; approvals: Approval[]; token: string; run: Run; setNotice: (value: string) => void; order: string[]; isAdmin: boolean; approvalBlocked?: string | null }) {
  return (
    <section aria-label="Plan versions" className="rounded-xl border bg-card p-4">
      <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-muted-foreground">Plan versions</h2>
      <p className="mb-3 text-xs text-tertiary">Each version is kept as append-only, tamper-evident evidence (inputs, policy fingerprint, hash). A stale plan cannot be approved; an approval authorizes exactly one plan version, expires, and is single-use.</p>
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
