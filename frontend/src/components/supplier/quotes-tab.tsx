"use client";

import { useState, type FormEvent } from "react";

import { ConfirmDialog } from "@/components/patterns/confirm-dialog";
import { SlideOver } from "@/components/patterns/overlays";
import { toLocalInput } from "@/components/quote-form";
import { day, money } from "@/components/status-badges";
import { quoteWords, word, type SupplierMission, type SupplierQuote } from "@/components/supplier/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

type Attempt = (operation: () => Promise<unknown>) => Promise<void>;

// "120 wool blankets at $28.50 · ETA Jan 3"
const summary = (quote: SupplierQuote) => `${quote.lines.map((line) => `${line.available_quantity} ${line.item} at ${money(line.unit_price)}`).join("; ")} · ETA ${day(quote.lines[0]?.delivery_date)}`;

function ReviseSlideOver({ quote, mission, token, attempt, onClose, onWithdraw }: {
  quote: SupplierQuote | null; mission?: SupplierMission; token: string; attempt: Attempt; onClose: () => void; onWithdraw: (quote: SupplierQuote) => void;
}) {
  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!quote) return;
    const form = new FormData(event.currentTarget);
    await attempt(() => api(`/v1/quotes/${quote.id}`, { method: "PUT", token, body: JSON.stringify({
      expires_at: new Date(String(form.get("expires_at"))).toISOString(), shipping_cost: Number(form.get("shipping_cost")).toFixed(2),
      lines: quote.lines.map((line, index) => ({ requirement_id: line.requirement_id ?? null, item: line.item, unit_price: Number(form.get(`price-${index}`)).toFixed(2), available_quantity: Number(form.get(`quantity-${index}`)), delivery_date: line.delivery_date })),
    }) }));
    onClose();
  };
  const several = (quote?.lines.length ?? 0) > 1;
  return (
    <SlideOver
      open={quote !== null} onOpenChange={(next) => { if (!next) onClose(); }} title="Revise quote" subtitle={mission ? mission.name : undefined}
      footer={<Button type="submit" form="revise-quote-form">Save changes</Button>}
    >
      {quote && (
        <form id="revise-quote-form" className="grid gap-5" onSubmit={(event) => void save(event)}>
          {quote.lines.map((line, index) => (
            <fieldset key={line.requirement_id ?? line.item} className="grid gap-5">
              {several && <legend className="mb-2 text-sm font-semibold">{line.item}</legend>}
              <div><Label htmlFor={`price-${index}`}>Unit price<span className="sr-only"> for {line.item}</span> (USD)</Label><Input id={`price-${index}`} name={`price-${index}`} className="mt-1.5" type="number" step="0.01" defaultValue={line.unit_price} /></div>
              <div><Label htmlFor={`quantity-${index}`}>Available quantity<span className="sr-only"> for {line.item}</span></Label><Input id={`quantity-${index}`} name={`quantity-${index}`} className="mt-1.5" type="number" defaultValue={line.available_quantity} /></div>
            </fieldset>
          ))}
          <div><Label htmlFor="revise-shipping">Shipping cost (USD)</Label><Input id="revise-shipping" name="shipping_cost" className="mt-1.5" type="number" step="0.01" defaultValue={quote.shipping_cost} /></div>
          <div><Label htmlFor="revise-expiry">Quote expiration</Label><Input id="revise-expiry" name="expires_at" className="mt-1.5" type="datetime-local" defaultValue={toLocalInput(quote.expires_at)} /></div>
          <div className="space-y-3 text-sm text-muted-foreground">
            <p>Any change invalidates the buyer&apos;s current plan approval and triggers automatic replanning.</p>
            <p>Competitors never see your quote.</p>
          </div>
          <div><Button type="button" variant="text" className="-ml-4" onClick={() => onWithdraw(quote)}>Withdraw quote</Button></div>
        </form>
      )}
    </SlideOver>
  );
}

export function QuotesTab({ quotes, missions, token, attempt }: { quotes: SupplierQuote[]; missions: Map<string, SupplierMission>; token: string; attempt: Attempt }) {
  const [revising, setRevising] = useState<SupplierQuote | null>(null);
  const [withdrawing, setWithdrawing] = useState<SupplierQuote | null>(null);
  const test = quotes.length > 0 && quotes.every((quote) => quote.is_demo);
  return (
    <section aria-label="Quotes">
      <h2 className="border-b pb-3 text-xl font-semibold">Quotes{test && <span className="font-normal text-muted-foreground"> · TEST data</span>}</h2>
      {quotes.length === 0 ? <p className="mt-6 text-sm text-muted-foreground">No quotes yet. Open an RFQ link from your email to submit one.</p> : (
        <ul>
          {quotes.map((quote) => {
            const mission = missions.get(quote.mission_id);
            const muted = quote.status !== "submitted";
            return (
              <li key={quote.id} className={cn("grid gap-x-8 gap-y-3 border-b py-6 md:grid-cols-[1.4fr_0.8fr_auto] md:items-start", muted && "text-tertiary")}>
                <div>
                  <p className="text-lg font-semibold">{mission?.name ?? quote.supplier_name ?? "RFQ"}</p>
                  {mission && <p className={cn("mt-0.5 text-sm", !muted && "text-muted-foreground")}>{mission.delivery_location} · Deliver by {day(mission.delivery_deadline)}</p>}
                  <p className="mt-2 text-sm tabular">{summary(quote)}</p>
                </div>
                <div><p className="font-medium" data-status={quote.status}>{word(quoteWords, quote.status)}</p><p className="text-sm text-muted-foreground">Quote v{quote.version}</p></div>
                {quote.status === "submitted" && <Button variant="text" className="justify-self-start md:-mr-4" onClick={() => setRevising(quote)}>Revise quote</Button>}
              </li>
            );
          })}
        </ul>
      )}
      <ReviseSlideOver
        quote={revising} mission={revising ? missions.get(revising.mission_id) : undefined} token={token} attempt={attempt}
        onClose={() => setRevising(null)} onWithdraw={(quote) => { setRevising(null); setWithdrawing(quote); }}
      />
      <ConfirmDialog
        open={withdrawing !== null} onOpenChange={(next) => { if (!next) setWithdrawing(null); }} title="Withdraw quote"
        facts={withdrawing && <p className="font-medium">{missions.get(withdrawing.mission_id)?.name ?? "This RFQ"} · {summary(withdrawing)}</p>}
        consequence="The buyer's plan loses this quote, any approval based on it is revoked, and the plan replans automatically. This can't be undone."
        confirmLabel="Withdraw quote"
        onConfirm={async () => { if (withdrawing) await attempt(() => api(`/v1/quotes/${withdrawing.id}/withdraw`, { method: "POST", token })); }}
      />
    </section>
  );
}
