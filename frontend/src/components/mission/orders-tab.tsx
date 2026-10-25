"use client";

import { useState } from "react";

import { OperationsPanel } from "@/components/mission/operations-panel";
import { Dialog } from "@/components/patterns/overlays";
import { amount, day, money, timeOnly } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import { Table } from "@/components/ui/table";
import { API_BASE_URL, api } from "@/lib/api";
import type { Approval, Plan, PurchaseOrder, Quote, SupplierRow } from "@/lib/types";
import { cn } from "@/lib/utils";

type Run = (operation: () => Promise<void>) => Promise<void>;

const STEPS = ["Draft", "Sent", "Accepted", "Shipped", "Delivered"];
// Where each PO status sits on the progress line. Statuses off the line (declined, cancelled, void) end the row.
const STEP_OF: Record<string, number> = { draft: 0, sent: 1, supplier_accepted: 2, in_fulfillment: 3, completed: 4 };
const ENDED: Record<string, string> = { supplier_declined: "Declined by the supplier", cancelled: "Supplier cannot fulfill", void: "Void: the plan behind this draft was replaced" };

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

function ProgressLine({ status }: { status: string }) {
  const current = STEP_OF[status];
  return (
    <p className="text-sm">
      {STEPS.map((step, index) => (
        <span key={step}>
          {index > 0 && <span aria-hidden className="mx-2 text-tertiary">→</span>}
          <span aria-current={index === current ? "step" : undefined} className={index === current ? "font-medium text-foreground" : "text-muted-foreground"}>{step}</span>
        </span>
      ))}
    </p>
  );
}

const quantity = (order: PurchaseOrder) => {
  const byItem = new Map<string, number>();
  for (const line of order.lines) byItem.set(line.item, (byItem.get(line.item) ?? 0) + line.quantity);
  return [...byItem.entries()].map(([item, units]) => `${units} ${item}`).join(", ");
};

// Shipping is quoted by the supplier but isn't part of the purchase order document.
const quotedShipping = (order: PurchaseOrder, quotes: Map<string, Quote>) => {
  const values = [...new Set(order.lines.map((line) => line.quote_id))].map((id) => quotes.get(id)?.shipping_cost);
  return values.every((value) => value !== undefined) ? values.reduce((sum, value) => sum + Number(value), 0) : null;
};

export function OrdersTab({ missionId, organizationId, plans, approvals, orders, quotes, suppliers, token, run, setNotice, isAdmin, onTab }: {
  missionId: string; organizationId: string; plans: Plan[]; approvals: Approval[]; orders: PurchaseOrder[]; quotes: Quote[]; suppliers: SupplierRow[];
  token: string; run: Run; setNotice: (value: string) => void; isAdmin: boolean; onTab: (tab: string) => void;
}) {
  const [confirming, setConfirming] = useState<PurchaseOrder | null>(null);
  const quotesById = new Map(quotes.map((quote) => [quote.id, quote]));
  const supplierBy = new Map(suppliers.map((row) => [row.supplier.id, row.supplier]));
  const nameOf = (order: PurchaseOrder) => (order.supplier_id && supplierBy.get(order.supplier_id)?.legal_name) || order.supplier_email;
  const isTest = (order: PurchaseOrder) => Boolean(order.supplier_id && supplierBy.get(order.supplier_id)?.is_demo);
  const used = [...approvals].filter((approval) => approval.status === "consumed").sort((a, b) => b.approved_at.localeCompare(a.approved_at))[0];
  const usedPlan = used && plans.find((plan) => plan.id === used.plan_id);
  const send = (order: PurchaseOrder) => run(async () => {
    await api(`/v1/purchase-orders/${order.id}/send`, { method: "POST", token, body: JSON.stringify({ confirm: true }) });
    setConfirming(null);
    setNotice(`${order.po_number} sent to ${nameOf(order)}.`);
  });
  const shipping = confirming ? quotedShipping(confirming, quotesById) : null;

  return (
    <div>
      {used && usedPlan && <p className="text-sm text-muted-foreground">Plan v{usedPlan.version} approved by {used.approver_email ?? "an approver"} at {timeOnly(used.approved_at)}.{used.consumed_at ? ` Draft POs generated at ${timeOnly(used.consumed_at)}.` : ""}</p>}
      <section aria-label="Purchase orders" className="mt-8">
        <h2 className="text-xl font-semibold">Purchase orders{orders.length > 0 && orders.every(isTest) && <span className="font-normal text-muted-foreground"> · TEST suppliers</span>}</h2>
        <p className="mt-1 text-sm text-muted-foreground">Supplier acceptance confirms the order only. It is not payment. Drafts aren&apos;t binding until you confirm and send them.</p>
        {orders.length === 0 ? (
          <p className="mt-6 text-sm text-muted-foreground">No purchase orders yet. Generate them from an approved plan. <button type="button" className="font-medium text-foreground hover:underline" onClick={() => onTab("plan")}>Go to Plan →</button></p>
        ) : (
          <ul className="mt-4">
            {orders.map((order) => {
              const ended = ENDED[order.status];
              const note = [...(order.events ?? [])].reverse().find((event) => event.note)?.note;
              const latestDelivery = order.lines.map((line) => line.delivery_date).sort().at(-1);
              const delivered = [...(order.events ?? [])].reverse().find((event) => event.status === "completed")?.at;
              const ship = quotedShipping(order, quotesById);
              return (
                <li key={order.id} data-testid={`po-${order.po_number}`} className={cn("grid gap-4 border-b py-6 md:grid-cols-[minmax(0,1.6fr)_minmax(0,0.8fr)_minmax(0,0.9fr)] md:gap-8", ended && "text-tertiary")}>
                  <div className="min-w-0">
                    <p className="text-base font-semibold">{order.po_number}</p>
                    <p className="text-base">{nameOf(order)}</p>
                    <div className="mt-4">{ended ? <p className="text-sm">{ended}</p> : <ProgressLine status={order.status} />}</div>
                    <p className="mt-3 text-sm text-muted-foreground">
                      {order.status === "draft" ? `Draft created at ${timeOnly(order.created_at)}. Not yet sent.` : order.sent_at ? `Sent at ${timeOnly(order.sent_at)}.` : ""}
                      {order.delivery?.status === "skipped_test_supplier" && " TEST supplier, so no email went out."}
                      {order.delivery?.status === "sent" && ` Emailed${order.delivery.provider ? ` via ${order.delivery.provider}` : ""}.`}
                      {order.plan_stale && ` From plan v${order.plan_version}, since replaced.`}
                    </p>
                    {note && <div className="mt-3 text-sm"><p className="text-xs text-muted-foreground">Supplier note</p><p>{note}</p></div>}
                  </div>
                  <div className="text-base tabular">
                    <p>{quantity(order)}</p>
                    <p>{amount(order.subtotal)}</p>
                    {ship !== null && ship > 0 && <p className="mt-1 text-xs text-muted-foreground">Quoted shipping {amount(ship)} isn&apos;t on the PO</p>}
                  </div>
                  <div className="flex flex-col items-start text-sm">
                    {order.status === "draft" ? <Button onClick={() => setConfirming(order)}>Confirm &amp; send</Button>
                      : ended ? null
                        : order.status === "completed" ? <p className="text-base">Delivered {day(delivered)}</p>
                          : order.status === "sent" ? <p className="text-base">Awaiting supplier</p>
                            : <p className="text-base">Expected {day(latestDelivery)}</p>}
                    <Button variant="text" size="sm" className="mt-2 px-0" onClick={() => void run(() => downloadPdf(order.id, order.po_number, token))}>Download PDF</Button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <OperationsPanel missionId={missionId} organizationId={organizationId} token={token} isAdmin={isAdmin} />

      <Dialog open={confirming !== null} onOpenChange={(open) => { if (!open) setConfirming(null); }} title="Confirm & send" subtitle={confirming ? `${confirming.po_number} · ${nameOf(confirming)}` : undefined}
        footer={confirming && <Button onClick={() => void send(confirming)}>Confirm &amp; send</Button>}>
        {confirming && (
          <>
            <p className="text-xs text-muted-foreground">Recipient email</p>
            <p className="text-base">{confirming.supplier_email}</p>
            <h3 className="mt-6 text-base font-semibold">Line items</h3>
            <Table className="mt-2 w-full text-sm">
              <thead><tr className="border-b text-left text-xs text-muted-foreground"><th className="py-2 font-medium">Item</th><th className="py-2 text-right font-medium">Qty</th><th className="py-2 text-right font-medium">Unit price</th><th className="py-2 text-right font-medium">Subtotal</th></tr></thead>
              <tbody>
                {confirming.lines.map((line) => <tr key={`${line.quote_id}-${line.item}`} className="border-b"><td className="py-2.5">{line.item}</td><td className="py-2.5 text-right tabular">{line.quantity}</td><td className="py-2.5 text-right tabular">{money(line.unit_price)}</td><td className="py-2.5 text-right tabular">{money(line.line_cost)}</td></tr>)}
                <tr><td colSpan={3} className="py-2.5 text-right font-medium">Total</td><td className="py-2.5 text-right font-medium tabular">{money(confirming.subtotal)}</td></tr>
              </tbody>
            </Table>
            {shipping !== null && shipping > 0 && <p className="mt-2 text-xs text-muted-foreground">The supplier&apos;s quoted shipping of {money(shipping)} isn&apos;t included on the purchase order.</p>}
            <p className="mt-6">{isTest(confirming) ? "This marks the purchase order as sent. TEST suppliers aren't emailed. It can't be undone." : "This emails the purchase order to the supplier. It can't be unsent."}</p>
          </>
        )}
      </Dialog>
    </div>
  );
}
