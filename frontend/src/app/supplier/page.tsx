"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { AppHeader } from "@/components/app-header";
import { toLocalInput } from "@/components/quote-form";
import { money, when } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { signInUrl } from "@/lib/session";
import { api } from "@/lib/api";
import { useHydrated, useSession } from "@/hooks/use-session";

type Invitation = { id: string; status: string; mission: { name: string; delivery_location: string; requirements: { item: string; quantity: number }[] } };
type Quote = { id: string; mission_id: string; status: string; version: number; shipping_cost: string; expires_at: string; supplier_name?: string | null; lines: { requirement_id?: string; item: string; available_quantity: number; unit_price: string; delivery_date: string }[] };
type Order = { id: string; po_number: string; status: string; subtotal?: string; buyer_organization: string; delivery_location: string; lines: { item: string; quantity: number }[]; events: { status: string; note?: string; at: string }[] };

const badge = "rounded border px-1.5 py-0.5 font-mono text-[10px] uppercase";

export default function SupplierPage() {
  const router = useRouter(); const session = useSession(); const [error, setError] = useState<string | null>(null); const [notes, setNotes] = useState<Record<string, string>>({});
  const hydrated = useHydrated();
  useEffect(() => { if (hydrated && (!session || session.user.role !== "supplier")) router.replace(signInUrl()); }, [hydrated, router, session]);
  const invitations = useQuery({ queryKey: ["supplier-invitations"], enabled: Boolean(session), queryFn: () => api<Invitation[]>("/v1/supplier/invitations", { token: session!.token }) });
  const quotes = useQuery({ queryKey: ["supplier-quotes"], enabled: Boolean(session), queryFn: () => api<Quote[]>("/v1/supplier/quotes", { token: session!.token }) });
  const orders = useQuery({ queryKey: ["supplier-orders"], enabled: Boolean(session), refetchInterval: 5000, queryFn: () => api<Order[]>("/v1/purchase-orders", { token: session!.token }) });
  if (!session) return <main className="grid min-h-screen place-items-center bg-background text-muted-foreground">Loading supplier portal…</main>;
  const attempt = async (operation: () => Promise<unknown>, after: () => Promise<unknown>) => { setError(null); try { await operation(); await after(); } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Request failed"); } };
  const respond = (orderId: string, accepted: boolean) => attempt(() => api(`/v1/purchase-orders/${orderId}/supplier-response`, { method: "POST", token: session.token, body: JSON.stringify({ accepted }) }), orders.refetch);
  const fulfill = (orderId: string, status: "in_fulfillment" | "completed" | "cancelled") => attempt(() => api(`/v1/purchase-orders/${orderId}/fulfillment`, { method: "POST", token: session.token, body: JSON.stringify({ status, note: notes[orderId] || (status === "completed" ? "Delivered to site" : status === "cancelled" ? "Supplier can no longer fulfill this order" : "Shipment dispatched") }) }), () => Promise.all([orders.refetch(), quotes.refetch()]));
  const withdraw = (quoteId: string) => attempt(() => api(`/v1/quotes/${quoteId}/withdraw`, { method: "POST", token: session.token }), quotes.refetch);
  const revise = async (event: React.FormEvent<HTMLFormElement>, quote: Quote) => { event.preventDefault(); const form = new FormData(event.currentTarget); await attempt(() => api(`/v1/quotes/${quote.id}`, { method: "PUT", token: session.token, body: JSON.stringify({ expires_at: new Date(String(form.get("expires_at"))).toISOString(), shipping_cost: Number(form.get("shipping_cost")).toFixed(2), lines: quote.lines.map((line, index) => ({ requirement_id: line.requirement_id ?? null, item: line.item, unit_price: Number(form.get(`price-${index}`)).toFixed(2), available_quantity: Number(form.get(`quantity-${index}`)), delivery_date: line.delivery_date })) }) }), quotes.refetch); };
  return (
    <main className="min-h-screen bg-background">
      <AppHeader email={session.user.email} home="/supplier" label="Supplier" />
      <div className="mx-auto max-w-5xl space-y-6 px-5 py-8">
        <section><p className="font-mono text-xs uppercase tracking-[0.2em] text-live">Supplier portal</p><h1 className="mt-1 text-3xl font-semibold">RFQs and purchase orders</h1></section>
        {error && <p role="alert" className="rounded border border-critical/40 bg-critical/10 p-3 text-sm text-critical">{error}</p>}
        <Card><CardHeader><CardTitle>Incoming RFQs</CardTitle><CardDescription>Open the signed invitation link from your email to accept and quote a mission.</CardDescription></CardHeader><CardContent>{invitations.data?.length ? <div className="space-y-3">{invitations.data.map((invite) => <div key={invite.id} className="flex items-center justify-between rounded border p-3"><div><p className="font-medium">{invite.mission.name}</p><p className="text-sm text-muted-foreground">{invite.mission.delivery_location} · {invite.mission.requirements.map((item) => `${item.quantity} ${item.item}`).join(", ")}</p></div><span className={badge}>{invite.status}</span></div>)}</div> : <p className="text-sm text-muted-foreground">No invitations linked to this supplier email yet.</p>}</CardContent></Card>
        <Card><CardHeader><CardTitle>Your quotes</CardTitle><CardDescription>Quote changes automatically invalidate affected plans and queue a replan. Competitors never see your quote.</CardDescription></CardHeader><CardContent>{quotes.data?.length ? <div className="space-y-3">{quotes.data.map((quote) => <div className="rounded border p-3" key={quote.id}><div className="flex justify-between"><span className="font-medium">{quote.supplier_name ? `${quote.supplier_name} · ` : ""}Quote v{quote.version}</span><span className={badge}>{quote.status}</span></div><p className="mt-1 text-sm text-muted-foreground">{quote.lines.map((line) => `${line.available_quantity} ${line.item} at ${money(line.unit_price)}`).join("; ")} · ETA {when(quote.lines[0]?.delivery_date)}</p>{quote.status === "submitted" && <div className="mt-3 flex flex-wrap gap-2"><Button size="sm" variant="outline" onClick={() => void withdraw(quote.id)}>Withdraw quote</Button><details className="min-w-64"><summary className="cursor-pointer text-sm font-medium">Revise price or inventory</summary><form className="mt-3 grid gap-2" onSubmit={(event) => void revise(event, quote)}>{quote.lines.map((line, index) => <div className="grid grid-cols-2 gap-2" key={line.item}><input aria-label={`${line.item} price`} className="rounded border bg-background px-2 py-1 text-sm" name={`price-${index}`} defaultValue={line.unit_price} type="number" step="0.01" /><input aria-label={`${line.item} quantity`} className="rounded border bg-background px-2 py-1 text-sm" name={`quantity-${index}`} defaultValue={line.available_quantity} type="number" /></div>)}<input aria-label="Shipping cost" className="rounded border bg-background px-2 py-1 text-sm" name="shipping_cost" defaultValue={quote.shipping_cost} type="number" step="0.01" /><input aria-label="Quote expiration" className="rounded border bg-background px-2 py-1 text-sm" name="expires_at" defaultValue={toLocalInput(quote.expires_at)} type="datetime-local" /><Button size="sm" type="submit">Save revision</Button></form></details></div>}</div>)}</div> : <p className="text-sm text-muted-foreground">No submitted quotes.</p>}</CardContent></Card>
        <Card><CardHeader><CardTitle>Purchase order inbox</CardTitle><CardDescription>Accepting an order confirms supplier acceptance only; it does not represent payment.</CardDescription></CardHeader><CardContent>{orders.data?.length ? <div className="space-y-3">{orders.data.map((order) => (
          <div className="rounded border p-3" key={order.id}>
            <div className="flex flex-wrap items-center justify-between gap-3"><div><p className="font-mono font-medium">{order.po_number}</p><p className="text-sm text-muted-foreground">{order.buyer_organization} · {order.lines.map((line) => `${line.quantity} ${line.item}`).join(", ")} · {money(order.subtotal)} → {order.delivery_location}</p></div>
              <div className="flex items-center gap-2"><span className={badge}>{order.status}</span>{order.status === "sent" && <><Button size="sm" onClick={() => void respond(order.id, true)}>Accept</Button><Button size="sm" variant="outline" onClick={() => void respond(order.id, false)}>Decline</Button></>}</div></div>
            {(order.status === "supplier_accepted" || order.status === "in_fulfillment") && <div className="mt-2 flex flex-wrap items-center gap-2"><input aria-label={`Fulfillment note for ${order.po_number}`} className="h-7 flex-1 rounded border bg-background px-2 text-sm" placeholder="Fulfillment note (e.g. tracking number)" value={notes[order.id] ?? ""} onChange={(event) => setNotes({ ...notes, [order.id]: event.target.value })} />{order.status === "supplier_accepted" && <Button size="sm" variant="secondary" onClick={() => void fulfill(order.id, "in_fulfillment")}>Mark shipped</Button>}<Button size="sm" onClick={() => void fulfill(order.id, "completed")}>Mark delivered</Button><Button size="sm" variant="outline" title="Withdraws your quote; the buyer replans the remaining quantity" onClick={() => void fulfill(order.id, "cancelled")}>Cannot fulfill</Button></div>}
            <ol className="mt-2 flex flex-wrap gap-x-3 font-mono text-[10px] text-tertiary">{order.events.map((event) => <li key={`${event.status}-${event.at}`}>{event.status}{event.note ? ` (${event.note})` : ""} · {when(event.at)}</li>)}</ol>
          </div>))}</div> : <p className="text-sm text-muted-foreground">No purchase orders.</p>}</CardContent></Card>
      </div>
    </main>
  );
}
