"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink, Plus, Trash2 } from "lucide-react";
import { useFieldArray, useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { Provenance, ago, when } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import type { EmergencyEvent } from "@/lib/types";

const schema = z.object({
  name: z.string().min(2),
  delivery_location: z.string().min(2),
  delivery_deadline: z.string().min(1),
  budget: z.number().positive(),
  item: z.string().min(1),
  quantity: z.number().int().positive(),
  extra: z.array(z.object({ item: z.string().min(1), quantity: z.number().int().positive() })),
  emergency_event_id: z.string(),
  max_supplier_share: z.string(),
});
export type MissionValues = z.infer<typeof schema>;

export function MissionForm({ onSubmit }: { onSubmit: (values: MissionValues, event: EmergencyEvent | null) => Promise<void> }) {
  const form = useForm<MissionValues>({ resolver: zodResolver(schema), defaultValues: { name: "", delivery_location: "", delivery_deadline: "", budget: 5000, item: "blankets", quantity: 100, extra: [], emergency_event_id: "", max_supplier_share: "" } });
  const extra = useFieldArray({ control: form.control, name: "extra" });
  const events = useQuery({ queryKey: ["emergency-events"], queryFn: () => api<EmergencyEvent[]>("/v1/emergency-events"), staleTime: 120_000 });
  const selectedId = useWatch({ control: form.control, name: "emergency_event_id" });
  const selected = events.data?.find((event) => event.id === selectedId) ?? null;
  return (
    <form className="grid gap-4" onSubmit={form.handleSubmit(async (values) => { await onSubmit(values, selected); form.reset(); })}>
      <div className="rounded-lg border bg-background/40 p-3">
        <div className="flex items-center justify-between gap-2"><Label htmlFor="event">Real emergency (NASA EONET, open events)</Label>{events.data?.[0] && <span className="flex items-center gap-2"><Provenance value={events.data[0].provenance} /><span className="font-mono text-[10px] text-tertiary">{ago(events.data[0].retrieved_at)}</span></span>}</div>
        <select id="event" className="mt-1 h-9 w-full rounded-lg border bg-background px-2 text-sm" {...form.register("emergency_event_id")}>
          <option value="">No linked event</option>
          {events.data?.map((event) => <option key={event.id} value={event.id}>{event.categories[0]?.title ?? "Event"} · {event.title}</option>)}
        </select>
        {events.isError && <p className="mt-1 text-xs text-critical">NASA EONET unavailable: {events.error.message}</p>}
        {selected && (
          <div className="mt-2 text-xs text-muted-foreground">
            <p>{selected.categories.map((category) => category.title).join(", ")}{selected.point ? ` · ${selected.point.lat.toFixed(3)}, ${selected.point.lon.toFixed(3)}` : ""}{selected.state ? ` · ${selected.state}` : ""} · last observed {when(selected.last_observed)}</p>
            <p className="mt-0.5 flex flex-wrap gap-3">{selected.sources.map((source) => <a key={source.url} href={source.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-live">{source.id}<ExternalLink className="size-3" /></a>)}</p>
            <p className="mt-1 text-tertiary">Linking stores this event snapshot on the mission. Required supplies are never inferred automatically; enter them below.</p>
          </div>
        )}
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div><Label htmlFor="mission-name">Mission name</Label><Input id="mission-name" className="mt-1" placeholder="e.g. Storm shelter supplies" {...form.register("name")} /></div>
        <div><Label htmlFor="location">Delivery location</Label><Input id="location" className="mt-1" placeholder="City, ST" {...form.register("delivery_location")} /></div>
        <div><Label htmlFor="deadline">Delivery deadline</Label><Input id="deadline" className="mt-1" type="datetime-local" {...form.register("delivery_deadline")} /></div>
        <div><Label htmlFor="budget">Budget (USD)</Label><Input id="budget" className="mt-1" type="number" step="0.01" {...form.register("budget", { valueAsNumber: true })} /></div>
        <div><Label htmlFor="item">Required item</Label><Input id="item" className="mt-1" {...form.register("item")} /></div>
        <div><Label htmlFor="quantity">Quantity</Label><Input id="quantity" className="mt-1" type="number" {...form.register("quantity", { valueAsNumber: true })} /></div>
        {extra.fields.map((field, index) => (
          <div key={field.id} className="grid grid-cols-[1fr_120px_auto] items-end gap-2 sm:col-span-2">
            <div><Label htmlFor={`extra-item-${index}`}>Additional line {index + 2} name</Label><Input id={`extra-item-${index}`} className="mt-1" {...form.register(`extra.${index}.item`)} /></div>
            <div><Label htmlFor={`extra-qty-${index}`}>Units</Label><Input id={`extra-qty-${index}`} className="mt-1" type="number" {...form.register(`extra.${index}.quantity`, { valueAsNumber: true })} /></div>
            <Button type="button" variant="text" size="icon" aria-label={`Remove line ${index + 2}`} onClick={() => extra.remove(index)}><Trash2 /></Button>
          </div>
        ))}
        <div className="flex items-end gap-3 sm:col-span-2">
          <Button type="button" variant="secondary" size="sm" onClick={() => extra.append({ item: "", quantity: 1 })}><Plus className="size-3.5" />Add supply line</Button>
          <div className="w-56"><Label htmlFor="max-share">Max share per supplier (optional)</Label><Input id="max-share" className="mt-1" placeholder="e.g. 0.7" {...form.register("max_supplier_share")} /></div>
        </div>
      </div>
      <Button type="submit" disabled={form.formState.isSubmitting}>{form.formState.isSubmitting ? "Creating…" : "Create mission"}</Button>
    </form>
  );
}
