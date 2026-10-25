"use client";

import { useState } from "react";

import { Dialog } from "@/components/patterns/overlays";
import { PlanStatusText, ago, money, signedAmount } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table } from "@/components/ui/table";
import { api } from "@/lib/api";
import type { Approval, Disruption, Plan, SupplierRow } from "@/lib/types";
import { cn } from "@/lib/utils";

type Run = (operation: () => Promise<void>) => Promise<void>;

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
      <Table className="mt-4 w-full text-sm">
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
      </Table>
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
