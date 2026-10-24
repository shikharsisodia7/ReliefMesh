"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { QuoteDraft, Requirement } from "@/lib/types";

const line = z.object({
  requirement_id: z.string(),
  item: z.string().min(1),
  unit_price: z.number().nonnegative(),
  available_quantity: z.number().int().nonnegative(),
  delivery_date: z.string(),
});
const schema = z.object({
  legal_name: z.string().min(2, "Enter the legal business name used for compliance screening"),
  website: z.string(),
  shipping_cost: z.number().nonnegative(),
  expires_at: z.string().min(1),
  lines: z.array(line),
});
export type QuoteValues = z.infer<typeof schema>;

// datetime-local inputs take local wall-clock time without a zone.
const toLocalInput = (iso: string) => { const date = new Date(iso); return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16); };

// One block per mission requirement; each submitted line is pinned to that requirement's stable ID.
export function QuoteForm({ requirements, legalName, onSubmit, onDraft }: { requirements: Requirement[]; legalName?: string | null; onSubmit: (values: QuoteValues) => Promise<void>; onDraft?: (text: string) => Promise<QuoteDraft> }) {
  const form = useForm<QuoteValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      legal_name: legalName ?? "", website: "", shipping_cost: 0, expires_at: "",
      lines: requirements.map((requirement) => ({ requirement_id: requirement.id ?? "", item: requirement.item, unit_price: 0, available_quantity: 0, delivery_date: "" })),
    },
  });
  const [pasted, setPasted] = useState("");
  const [drafting, setDrafting] = useState(false);
  const [draft, setDraft] = useState<QuoteDraft | null>(null);
  const [draftError, setDraftError] = useState<string | null>(null);
  const label = (index: number, base: string) => (index === 0 ? base : `${requirements[index].item}: ${base.toLowerCase()}`);
  const draftLine = (index: number) => draft?.lines.find((row) => row.requirement_id === requirements[index].id);
  const flagged = (index: number, field: "available_quantity" | "unit_price") => {
    const row = draftLine(index);
    return Boolean(row && (!row.grounded || row.unverified_fields.includes(field)));
  };
  const review = "border-warn ring-2 ring-warn/30";

  const applyDraft = async () => {
    if (!onDraft) return;
    setDrafting(true); setDraftError(null);
    try {
      const result = await onDraft(pasted);
      requirements.forEach((requirement, index) => {
        const row = result.lines.find((candidate) => candidate.requirement_id === requirement.id);
        if (!row) return;
        form.setValue(`lines.${index}.item`, row.item, { shouldDirty: true });
        if (row.available_quantity !== null) form.setValue(`lines.${index}.available_quantity`, row.available_quantity, { shouldDirty: true });
        if (row.unit_price !== null) form.setValue(`lines.${index}.unit_price`, Number(row.unit_price), { shouldDirty: true });
        if (row.delivery_date) form.setValue(`lines.${index}.delivery_date`, toLocalInput(row.delivery_date), { shouldDirty: true });
      });
      if (result.shipping_cost !== null) form.setValue("shipping_cost", Number(result.shipping_cost), { shouldDirty: true });
      if (result.expires_at) form.setValue("expires_at", toLocalInput(result.expires_at), { shouldDirty: true });
      setDraft(result);
    } catch (error) {
      setDraftError(error instanceof Error ? error.message : "The quote assistant is unavailable; fill the form manually.");
    } finally { setDrafting(false); }
  };

  return (
    <form className="grid gap-4 sm:grid-cols-2" onSubmit={form.handleSubmit(async (values) => {
      const quoted = values.lines.filter((row) => row.available_quantity > 0);
      if (quoted.length === 0) { form.setError("lines", { message: "Quote at least one requirement" }); return; }
      if (quoted.some((row) => !row.delivery_date || row.unit_price <= 0)) { form.setError("lines", { message: "Each quoted line needs a unit price and delivery estimate" }); return; }
      await onSubmit({ ...values, lines: quoted });
    })}>
      {onDraft && (
        <div className="grid gap-2 rounded-lg border border-dashed p-3 sm:col-span-2">
          <Label htmlFor="pasted-quote">Paste an existing quote (optional)</Label>
          <Textarea id="pasted-quote" rows={4} maxLength={12000} placeholder="Paste the text of your emailed or PDF quote. Gemini pre-fills the form below; nothing is submitted until you review it." value={pasted} onChange={(event) => setPasted(event.target.value)} />
          <div className="flex flex-wrap items-center gap-3">
            <Button type="button" variant="outline" size="sm" disabled={drafting || pasted.trim().length < 20} onClick={() => void applyDraft()}>{drafting ? "Reading quote…" : "Pre-fill with Gemini"}</Button>
            <span className="text-xs text-muted-foreground">AI draft only. It cannot mark you eligible or change screening.</span>
          </div>
          {draftError && <p className="text-xs text-critical">{draftError}</p>}
          {draft && (
            <div className="rounded-md border border-warn/40 bg-warn/10 p-2 text-xs" role="status">
              <p className="font-medium">{draft.notice} <span className="font-mono text-muted-foreground">{draft.model}</span></p>
              <p className="mt-1">Filled {draft.lines.length} of {requirements.length} requirements. Highlighted values were not found in the quoted text. Check them.</p>
              {draft.unmatched_items.length > 0 && <p className="mt-1 text-muted-foreground">Not part of this RFQ: {draft.unmatched_items.join(", ")}</p>}
            </div>
          )}
        </div>
      )}
      <div><Label htmlFor="legal-name">Legal business name</Label><Input id="legal-name" className="mt-1" placeholder="As registered" {...form.register("legal_name")} />{form.formState.errors.legal_name && <p className="mt-1 text-xs text-critical">{form.formState.errors.legal_name.message}</p>}</div>
      <div><Label htmlFor="website">Company website (optional)</Label><Input id="website" className="mt-1" {...form.register("website")} /></div>
      <p className="text-xs text-muted-foreground sm:col-span-2">ReliefMesh screens the legal name against official public records (OFAC sanctions list, SAM.gov, openFDA recalls, USAspending awards). Free-text notes never affect eligibility.</p>
      {requirements.map((requirement, index) => (
        <fieldset key={requirement.id ?? requirement.item} className="grid gap-3 rounded-lg border p-3 sm:col-span-2 sm:grid-cols-2">
          <legend className="px-1 text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">Requirement {index + 1}: {requirement.quantity} {requirement.item} <span className="font-mono normal-case text-tertiary">{requirement.id}</span></legend>
          <input type="hidden" {...form.register(`lines.${index}.requirement_id`)} />
          <div><Label htmlFor={`item-${index}`}>{label(index, "Item")}</Label><Input id={`item-${index}`} className="mt-1" placeholder="Your product description" {...form.register(`lines.${index}.item`)} /></div>
          <div><Label htmlFor={`quantity-${index}`}>{label(index, "Available quantity")}</Label><Input id={`quantity-${index}`} className={`mt-1 ${flagged(index, "available_quantity") ? review : ""}`} type="number" {...form.register(`lines.${index}.available_quantity`, { valueAsNumber: true })} /></div>
          <div><Label htmlFor={`price-${index}`}>{label(index, "Unit price (USD)")}</Label><Input id={`price-${index}`} className={`mt-1 ${flagged(index, "unit_price") ? review : ""}`} type="number" step="0.01" {...form.register(`lines.${index}.unit_price`, { valueAsNumber: true })} /></div>
          <div><Label htmlFor={`delivery-${index}`}>{label(index, "Delivery estimate")}</Label><Input id={`delivery-${index}`} className="mt-1" type="datetime-local" {...form.register(`lines.${index}.delivery_date`)} /></div>
          {draftLine(index) && <p className="text-xs text-muted-foreground sm:col-span-2">From your text: <q className="italic">{draftLine(index)!.source_excerpt}</q>{!draftLine(index)!.grounded && <span className="text-warn"> (not found verbatim in the pasted quote)</span>}</p>}
        </fieldset>
      ))}
      {form.formState.errors.lines?.message && <p className="text-xs text-critical sm:col-span-2">{form.formState.errors.lines.message}</p>}
      <div><Label htmlFor="shipping">Shipping (USD)</Label><Input id="shipping" className="mt-1" type="number" step="0.01" {...form.register("shipping_cost", { valueAsNumber: true })} /></div>
      <div><Label htmlFor="expiration">Quote expiration</Label><Input id="expiration" className="mt-1" type="datetime-local" {...form.register("expires_at")} /></div>
      <Button className="sm:col-span-2" type="submit" disabled={form.formState.isSubmitting}>{form.formState.isSubmitting ? "Submitting…" : "Submit binding quote"}</Button>
    </form>
  );
}
