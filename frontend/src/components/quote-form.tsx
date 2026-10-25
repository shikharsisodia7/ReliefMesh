"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Sparkles } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { QuoteDraft, Requirement } from "@/lib/types";
import { cn } from "@/lib/utils";

// Number fields start blank; a blank field counts as 0, exactly as the old pre-filled 0 did.
const blankIsZero = <T extends z.ZodType>(schema: T) => z.preprocess((value) => (value === undefined || value === "" || Number.isNaN(value) ? 0 : value), schema);
const line = z.object({
  requirement_id: z.string(),
  item: z.string().min(1),
  unit_price: blankIsZero(z.number().nonnegative()),
  available_quantity: blankIsZero(z.number().int().nonnegative()),
  delivery_date: z.string(),
});
const schema = z.object({
  legal_name: z.string().min(2, "Enter the legal business name used for compliance screening"),
  website: z.string(),
  shipping_cost: blankIsZero(z.number().nonnegative()),
  expires_at: z.string().min(1),
  lines: z.array(line),
});
export type QuoteValues = z.output<typeof schema>;
type QuoteInput = z.input<typeof schema>;
type FieldName = Parameters<ReturnType<typeof useForm<QuoteInput, unknown, QuoteValues>>["register"]>[0];

// datetime-local inputs take local wall-clock time without a zone.
/** ISO timestamp -> value for a datetime-local input, in the viewer's local time. */
export const toLocalInput = (iso: string) => { const date = new Date(iso); return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16); };
/** Draft timestamp -> datetime-local value: a zoned instant is shown in local time; a naive wall-clock time as written. */
export const draftToInput = (value: string) => (/(?:[zZ]|[+-]\d{2}:?\d{2})$/.test(value) ? toLocalInput(value) : value.slice(0, 16));

// A field label with a small gray "AI draft" marker while the value is still Gemini's.
function FieldLabel({ htmlFor, ai, children }: { htmlFor: string; ai: boolean; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <Label htmlFor={htmlFor}>{children}</Label>
      {ai && <span className="inline-flex items-center gap-1 text-xs text-muted-foreground"><Sparkles className="size-3" aria-hidden />AI draft</span>}
    </div>
  );
}

// One row per mission requirement; each submitted line is pinned to that requirement's stable ID.
export function QuoteForm({ requirements, legalName, onSubmit, onDraft, assistant }: {
  requirements: Requirement[]; legalName?: string | null; onSubmit: (values: QuoteValues) => Promise<void>;
  onDraft?: (text: string) => Promise<QuoteDraft>; assistant: "on" | "off" | "unknown";
}) {
  const form = useForm<QuoteInput, unknown, QuoteValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      legal_name: legalName ?? "", website: "", expires_at: "",
      lines: requirements.map((requirement) => ({ requirement_id: requirement.id ?? "", item: requirement.item, delivery_date: "" })),
    },
  });
  const [pasted, setPasted] = useState("");
  const [drafting, setDrafting] = useState(false);
  const [draft, setDraft] = useState<QuoteDraft | null>(null);
  const [draftError, setDraftError] = useState<string | null>(null);
  const [aiFields, setAiFields] = useState<Set<string>>(new Set());
  const [reviewed, setReviewed] = useState(false);
  const label = (index: number, base: string) => (index === 0 ? base : `${requirements[index].item}: ${base.toLowerCase()}`);
  const draftLine = (index: number) => draft?.lines.find((row) => row.requirement_id === requirements[index].id);
  const flagged = (index: number, field: "available_quantity" | "unit_price") => {
    const row = draftLine(index);
    return Boolean(row && (!row.grounded || row.unverified_fields.includes(field)));
  };
  // Editing a field makes it the supplier's own value, so its "AI draft" marker goes away.
  const field = (name: FieldName, options: { valueAsNumber?: boolean } = {}) => form.register(name, {
    ...options,
    onChange: () => setAiFields((current) => { if (!current.has(name)) return current; const next = new Set(current); next.delete(name); return next; }),
  });

  const applyDraft = async () => {
    if (!onDraft) return;
    setDrafting(true); setDraftError(null);
    try {
      const result = await onDraft(pasted);
      const filled = new Set<string>();
      const fill = (name: FieldName, value: string | number) => { form.setValue(name, value as never, { shouldDirty: true }); filled.add(name); };
      requirements.forEach((requirement, index) => {
        const row = result.lines.find((candidate) => candidate.requirement_id === requirement.id);
        if (!row) return;
        fill(`lines.${index}.item`, row.item);
        if (row.available_quantity !== null) fill(`lines.${index}.available_quantity`, row.available_quantity);
        if (row.unit_price !== null) fill(`lines.${index}.unit_price`, Number(row.unit_price));
        if (row.delivery_date) fill(`lines.${index}.delivery_date`, draftToInput(row.delivery_date));
      });
      if (result.shipping_cost !== null) fill("shipping_cost", Number(result.shipping_cost));
      if (result.expires_at) fill("expires_at", draftToInput(result.expires_at));
      setAiFields(filled);
      setDraft(result);
    } catch (error) {
      setDraftError(error instanceof Error ? error.message : "The quote assistant is unavailable; fill the form manually.");
    } finally { setDrafting(false); }
  };

  const review = "border-warn";
  return (
    <div className="grid gap-12 lg:grid-cols-[minmax(0,7fr)_minmax(0,3fr)]">
      <form className="grid gap-5 sm:grid-cols-2" onSubmit={form.handleSubmit(async (values) => {
        const quoted = values.lines.filter((row) => row.available_quantity > 0);
        if (quoted.length === 0) { form.setError("lines", { message: "Quote at least one requirement" }); return; }
        if (quoted.some((row) => !row.delivery_date || row.unit_price <= 0)) { form.setError("lines", { message: "Each quoted line needs a unit price and delivery estimate" }); return; }
        await onSubmit({ ...values, lines: quoted });
      })}>
        <div className="sm:col-span-2">
          <h2 className="text-xl font-semibold">Your quote</h2>
          {draft && <p className="mt-1 inline-flex items-center gap-1 text-sm text-muted-foreground"><Sparkles className="size-3.5" aria-hidden />AI draft · review before submitting</p>}
        </div>
        <div><Label htmlFor="legal-name">Legal business name</Label><Input id="legal-name" className="mt-1.5" placeholder="As registered" {...form.register("legal_name")} />{form.formState.errors.legal_name && <p className="mt-1 text-xs text-critical">{form.formState.errors.legal_name.message}</p>}</div>
        <div><Label htmlFor="website">Company website (optional)</Label><Input id="website" className="mt-1.5" {...form.register("website")} /></div>
        <p className="text-xs text-muted-foreground sm:col-span-2">ReliefMesh screens the legal name against official public records (OFAC sanctions list, SAM.gov, openFDA recalls, USAspending awards). Free-text notes never affect eligibility.</p>
        {requirements.map((requirement, index) => (
          <fieldset key={requirement.id ?? requirement.item} className="grid gap-5 border-t pt-5 sm:col-span-2 sm:grid-cols-2">
            <legend className="float-left text-base font-semibold sm:col-span-2">{requirement.quantity.toLocaleString("en-US")} {requirement.item} needed</legend>
            <input type="hidden" {...form.register(`lines.${index}.requirement_id`)} />
            <div><FieldLabel htmlFor={`item-${index}`} ai={aiFields.has(`lines.${index}.item`)}>{label(index, "Item")}</FieldLabel><Input id={`item-${index}`} className="mt-1.5" placeholder="Your product description" {...field(`lines.${index}.item`)} /></div>
            <div><FieldLabel htmlFor={`quantity-${index}`} ai={aiFields.has(`lines.${index}.available_quantity`)}>{label(index, "Available quantity")}</FieldLabel><Input id={`quantity-${index}`} className={cn("mt-1.5", flagged(index, "available_quantity") && review)} type="number" placeholder="0" {...field(`lines.${index}.available_quantity`, { valueAsNumber: true })} /></div>
            <div><FieldLabel htmlFor={`price-${index}`} ai={aiFields.has(`lines.${index}.unit_price`)}>{label(index, "Unit price (USD)")}</FieldLabel><Input id={`price-${index}`} className={cn("mt-1.5", flagged(index, "unit_price") && review)} type="number" step="0.01" placeholder="0.00" {...field(`lines.${index}.unit_price`, { valueAsNumber: true })} /></div>
            <div><FieldLabel htmlFor={`delivery-${index}`} ai={aiFields.has(`lines.${index}.delivery_date`)}>{label(index, "Delivery estimate")}</FieldLabel><Input id={`delivery-${index}`} className="mt-1.5" type="datetime-local" {...field(`lines.${index}.delivery_date`)} /></div>
            {draftLine(index) && <p className="text-xs text-muted-foreground sm:col-span-2">From your text: <q className="italic">{draftLine(index)!.source_excerpt}</q>{!draftLine(index)!.grounded && <span className="text-warn"> (not found verbatim in the pasted quote)</span>}</p>}
          </fieldset>
        ))}
        {form.formState.errors.lines?.message && <p className="text-xs text-critical sm:col-span-2">{form.formState.errors.lines.message}</p>}
        <div className="border-t pt-5"><FieldLabel htmlFor="shipping" ai={aiFields.has("shipping_cost")}>Shipping (USD)</FieldLabel><Input id="shipping" className="mt-1.5" type="number" step="0.01" placeholder="0.00" {...field("shipping_cost", { valueAsNumber: true })} /></div>
        <div className="sm:border-t sm:pt-5"><FieldLabel htmlFor="expiration" ai={aiFields.has("expires_at")}>Quote expiration</FieldLabel><Input id="expiration" className="mt-1.5" type="datetime-local" {...field("expires_at")} /></div>
        <div className="mt-2 sm:col-span-2">
          <label className="flex items-center gap-3 text-sm">
            <input type="checkbox" required className="size-4 accent-[var(--foreground)]" checked={reviewed} onChange={(event) => setReviewed(event.target.checked)} />
            I reviewed the values and confirm they are correct.
          </label>
          <Button className="mt-5" size="lg" type="submit" disabled={!reviewed || form.formState.isSubmitting}>{form.formState.isSubmitting ? "Submitting…" : "Submit binding quote"}</Button>
          {!reviewed && <p className="mt-2 text-sm text-muted-foreground">Confirm review to submit.</p>}
        </div>
      </form>

      <aside aria-label="Draft from an existing quote">
        <h2 className="text-base font-semibold">Draft from an existing quote</h2>
        <p className="mt-0.5 inline-flex items-center gap-1 text-sm text-muted-foreground"><Sparkles className="size-3.5" aria-hidden />AI · Gemini · pasted text</p>
        {onDraft ? (
          <div className="mt-4 grid gap-3">
            <Label htmlFor="pasted-quote">Paste an existing quote (optional)</Label>
            <Textarea id="pasted-quote" rows={8} maxLength={12000} placeholder="Paste the text of your emailed or PDF quote. Gemini pre-fills the form; nothing is submitted until you review it." value={pasted} onChange={(event) => setPasted(event.target.value)} />
            <Button type="button" variant="secondary" className="justify-self-start" disabled={drafting || pasted.trim().length < 20} onClick={() => void applyDraft()}>{drafting ? "Reading quote…" : "Pre-fill with Gemini"}</Button>
            <p className="text-xs text-muted-foreground">AI draft only. It cannot mark you eligible or change screening.</p>
            {draftError && <p role="alert" className="text-sm text-critical">{draftError}</p>}
            {draft && (
              <div className="space-y-1 border-t pt-3 text-sm" role="status">
                <p>{draft.notice} <span className="font-mono text-xs text-muted-foreground">{draft.model}</span></p>
                <p className="text-muted-foreground">Filled {draft.lines.length} of {requirements.length} requirements. Values outlined in amber were not found in your text. Check them.</p>
                {draft.unmatched_items.length > 0 && <p className="text-muted-foreground">Not part of this RFQ: {draft.unmatched_items.join(", ")}</p>}
              </div>
            )}
          </div>
        ) : (
          <p className="mt-4 text-sm text-muted-foreground">{assistant === "off" ? "Drafting from a pasted quote isn't available because Gemini isn't configured on this server. Fill the form by hand." : "Checking whether the quote assistant is available…"}</p>
        )}
      </aside>
    </div>
  );
}
