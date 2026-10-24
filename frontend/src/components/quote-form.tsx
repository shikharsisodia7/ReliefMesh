"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Requirement } from "@/lib/types";

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

// One block per mission requirement; each submitted line is pinned to that requirement's stable ID.
export function QuoteForm({ requirements, legalName, onSubmit }: { requirements: Requirement[]; legalName?: string | null; onSubmit: (values: QuoteValues) => Promise<void> }) {
  const form = useForm<QuoteValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      legal_name: legalName ?? "", website: "", shipping_cost: 0, expires_at: "",
      lines: requirements.map((requirement) => ({ requirement_id: requirement.id ?? "", item: requirement.item, unit_price: 0, available_quantity: 0, delivery_date: "" })),
    },
  });
  const label = (index: number, base: string) => (index === 0 ? base : `${requirements[index].item}: ${base.toLowerCase()}`);
  return (
    <form className="grid gap-4 sm:grid-cols-2" onSubmit={form.handleSubmit(async (values) => {
      const quoted = values.lines.filter((row) => row.available_quantity > 0);
      if (quoted.length === 0) { form.setError("lines", { message: "Quote at least one requirement" }); return; }
      if (quoted.some((row) => !row.delivery_date || row.unit_price <= 0)) { form.setError("lines", { message: "Each quoted line needs a unit price and delivery estimate" }); return; }
      await onSubmit({ ...values, lines: quoted });
    })}>
      <div><Label htmlFor="legal-name">Legal business name</Label><Input id="legal-name" className="mt-1" placeholder="As registered" {...form.register("legal_name")} />{form.formState.errors.legal_name && <p className="mt-1 text-xs text-critical">{form.formState.errors.legal_name.message}</p>}</div>
      <div><Label htmlFor="website">Company website (optional)</Label><Input id="website" className="mt-1" {...form.register("website")} /></div>
      <p className="text-xs text-muted-foreground sm:col-span-2">ReliefMesh screens the legal name against official public records (OFAC sanctions list, SAM.gov, openFDA recalls, USAspending awards). Free-text notes never affect eligibility.</p>
      {requirements.map((requirement, index) => (
        <fieldset key={requirement.id ?? requirement.item} className="grid gap-3 rounded-lg border p-3 sm:col-span-2 sm:grid-cols-2">
          <legend className="px-1 text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">Requirement {index + 1}: {requirement.quantity} {requirement.item} <span className="font-mono normal-case text-tertiary">{requirement.id}</span></legend>
          <input type="hidden" {...form.register(`lines.${index}.requirement_id`)} />
          <div><Label htmlFor={`item-${index}`}>{label(index, "Item")}</Label><Input id={`item-${index}`} className="mt-1" placeholder="Your product description" {...form.register(`lines.${index}.item`)} /></div>
          <div><Label htmlFor={`quantity-${index}`}>{label(index, "Available quantity")}</Label><Input id={`quantity-${index}`} className="mt-1" type="number" {...form.register(`lines.${index}.available_quantity`, { valueAsNumber: true })} /></div>
          <div><Label htmlFor={`price-${index}`}>{label(index, "Unit price (USD)")}</Label><Input id={`price-${index}`} className="mt-1" type="number" step="0.01" {...form.register(`lines.${index}.unit_price`, { valueAsNumber: true })} /></div>
          <div><Label htmlFor={`delivery-${index}`}>{label(index, "Delivery estimate")}</Label><Input id={`delivery-${index}`} className="mt-1" type="datetime-local" {...form.register(`lines.${index}.delivery_date`)} /></div>
        </fieldset>
      ))}
      {form.formState.errors.lines?.message && <p className="text-xs text-critical sm:col-span-2">{form.formState.errors.lines.message}</p>}
      <div><Label htmlFor="shipping">Shipping (USD)</Label><Input id="shipping" className="mt-1" type="number" step="0.01" {...form.register("shipping_cost", { valueAsNumber: true })} /></div>
      <div><Label htmlFor="expiration">Quote expiration</Label><Input id="expiration" className="mt-1" type="datetime-local" {...form.register("expires_at")} /></div>
      <Button className="sm:col-span-2" type="submit" disabled={form.formState.isSubmitting}>{form.formState.isSubmitting ? "Submitting…" : "Submit binding quote"}</Button>
    </form>
  );
}
