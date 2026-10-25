"use client";

import { Fragment, useState } from "react";

import { ConfirmDialog } from "@/components/patterns/confirm-dialog";
import { amount, day, when } from "@/components/status-badges";
import { orderWords, word, type SupplierOrder } from "@/components/supplier/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";

type Attempt = (operation: () => Promise<unknown>) => Promise<void>;
type Pending = { order: SupplierOrder; kind: "decline" | "cancel" } | null;

const open = ["supplier_accepted", "in_fulfillment"];

// Dated history in gray: "Oct 20 Sent → Accepted", one entry per change.
function History({ order }: { order: SupplierOrder }) {
  const events = order.events.filter((event) => event.status !== "draft");
  if (events.length === 0) return null;
  return (
    <p className="mt-3 text-sm text-muted-foreground tabular">
      {events.map((event, index) => (
        <Fragment key={`${event.status}-${event.at}`}>
          {index > 0 && <span className="mx-2" aria-hidden>→</span>}
          <span title={when(event.at)}>{day(event.at)} {word(orderWords, event.status)}{event.note ? ` (${event.note})` : ""}</span>
        </Fragment>
      ))}
    </p>
  );
}

export function OrdersTab({ orders, token, attempt }: { orders: SupplierOrder[]; token: string; attempt: Attempt }) {
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [pending, setPending] = useState<Pending>(null);
  // Drafts haven't been sent by the buyer yet, so they aren't the supplier's to act on.
  const rows = orders.filter((order) => order.status !== "draft");
  const respond = (order: SupplierOrder, accepted: boolean, reason?: string) => attempt(() => api(`/v1/purchase-orders/${order.id}/supplier-response`, { method: "POST", token, body: JSON.stringify({ accepted, reason: reason || null }) }));
  const fulfill = (order: SupplierOrder, status: "in_fulfillment" | "completed" | "cancelled", reason?: string) => {
    const fallback = status === "completed" ? "Delivered to site" : status === "cancelled" ? "Supplier can no longer fulfill this order" : "Shipment dispatched";
    return attempt(() => api(`/v1/purchase-orders/${order.id}/fulfillment`, { method: "POST", token, body: JSON.stringify({ status, note: reason || notes[order.id] || fallback }) }));
  };
  return (
    <section aria-label="Orders">
      <h2 className="border-b pb-3 text-xl font-semibold">Orders</h2>
      {rows.length === 0 ? <p className="mt-6 text-sm text-muted-foreground">No purchase orders yet. They appear here when a buyer sends one.</p> : (
        <ul>
          {rows.map((order) => {
            const units = order.lines.reduce((sum, line) => sum + line.quantity, 0);
            const items = [...new Set(order.lines.map((line) => line.item))].join(", ");
            const due = order.lines.map((line) => line.delivery_date).filter(Boolean).sort().at(-1);
            return (
              <li key={order.id} data-testid={`order-${order.po_number}`} className="grid gap-x-8 gap-y-4 border-b py-6 md:grid-cols-[1.2fr_1fr_1fr]">
                <div>
                  <p className="font-semibold">{order.po_number}</p>
                  <p className="mt-0.5">{order.buyer_organization}</p>
                  <p className="mt-0.5 text-sm text-muted-foreground">{units.toLocaleString("en-US")} {items}</p>
                </div>
                <div className="text-sm">
                  <p className="text-base font-medium tabular">{amount(order.subtotal)}</p>
                  <p className="mt-0.5 text-muted-foreground">{order.delivery_location}</p>
                  {due && <p className="text-muted-foreground">Deliver by {day(due)}</p>}
                </div>
                <div>
                  <p className="font-medium" data-status={order.status}>{word(orderWords, order.status)}</p>
                  {order.status === "sent" && (
                    <>
                      {order.sent_at && <p className="text-sm text-muted-foreground">Received {when(order.sent_at)}</p>}
                      <div className="mt-3 flex items-center gap-2">
                        <Button onClick={() => void respond(order, true)}>Accept</Button>
                        <Button variant="text" onClick={() => setPending({ order, kind: "decline" })}>Decline</Button>
                      </div>
                    </>
                  )}
                  {open.includes(order.status) && (
                    <div className="mt-3 space-y-2">
                      <Input aria-label={`Fulfillment note for ${order.po_number}`} placeholder="Tracking number or delivery note" value={notes[order.id] ?? ""} onChange={(event) => setNotes({ ...notes, [order.id]: event.target.value })} />
                      <div className="flex flex-wrap items-center gap-2">
                        {order.status === "supplier_accepted" && <Button variant="secondary" size="sm" onClick={() => void fulfill(order, "in_fulfillment")}>Mark shipped</Button>}
                        <Button variant="secondary" size="sm" onClick={() => void fulfill(order, "completed")}>Mark delivered</Button>
                        <Button variant="text" size="sm" onClick={() => setPending({ order, kind: "cancel" })}>Cannot fulfill</Button>
                      </div>
                    </div>
                  )}
                </div>
                <div className="md:col-span-3"><History order={order} /></div>
              </li>
            );
          })}
        </ul>
      )}
      <p className="mt-6 text-sm text-muted-foreground">Accepting confirms the order only. It is not payment.</p>
      <p className="mt-1 text-sm text-muted-foreground">Declining or marking Cannot fulfill makes the buyer&apos;s plan replan automatically.</p>
      <ConfirmDialog
        open={pending !== null} onOpenChange={(next) => { if (!next) setPending(null); }}
        title={pending?.kind === "decline" ? "Decline order" : "Cannot fulfill"}
        facts={pending && <p className="font-medium">{pending.order.po_number} · {pending.order.buyer_organization} · {amount(pending.order.subtotal)}</p>}
        consequence={pending?.kind === "decline" ? "Your quote is withdrawn and the buyer's plan replans without it." : "The order is cancelled, your quote is withdrawn, and the buyer's plan replans the remaining quantity."}
        reasonLabel="Reason for the buyer"
        confirmLabel={pending?.kind === "decline" ? "Decline order" : "Cannot fulfill"}
        onConfirm={async (reason) => { if (!pending) return; await (pending.kind === "decline" ? respond(pending.order, false, reason) : fulfill(pending.order, "cancelled", reason)); }}
      />
    </section>
  );
}
