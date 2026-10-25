"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import { useFieldArray, useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { SlideOver } from "@/components/patterns/overlays";
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

const FORM_ID = "new-mission-form";
const defaults: MissionValues = { name: "", delivery_location: "", delivery_deadline: "", budget: 5000, item: "blankets", quantity: 100, extra: [], emergency_event_id: "", max_supplier_share: "" };

// The New mission slide-over. Field labels are unchanged from the old inline form; the tests rely on them.
export function NewMissionSlideOver({ open, onOpenChange, error, onSubmit }: {
  open: boolean; onOpenChange: (open: boolean) => void; error: string | null;
  onSubmit: (values: MissionValues, event: EmergencyEvent | null) => Promise<void>;
}) {
  const form = useForm<MissionValues>({ resolver: zodResolver(schema), defaultValues: defaults });
  const extra = useFieldArray({ control: form.control, name: "extra" });
  const events = useQuery({ queryKey: ["emergency-events"], queryFn: () => api<EmergencyEvent[]>("/v1/emergency-events"), staleTime: 120_000 });
  const selectedId = useWatch({ control: form.control, name: "emergency_event_id" });
  const selected = events.data?.find((event) => event.id === selectedId) ?? null;
  const submitting = form.formState.isSubmitting;
  return (
    <SlideOver
      open={open} onOpenChange={onOpenChange} title="New mission" subtitle="Link an event and define the supplies needed."
      footer={<Button type="submit" form={FORM_ID} disabled={submitting}>{submitting ? "Creating…" : "Create mission"}</Button>}
    >
      <form id={FORM_ID} className="grid gap-5" onSubmit={form.handleSubmit(async (values) => { await onSubmit(values, selected); })}>
        {error && <p role="alert" className="text-sm text-critical">{error}</p>}
        <div>
          <div className="flex items-baseline justify-between gap-2">
            <Label htmlFor="event">Real emergency (NASA EONET, open events)</Label>
            {events.data?.[0] && <span className="text-xs text-muted-foreground"><Provenance value={events.data[0].provenance} /> · {ago(events.data[0].retrieved_at)}</span>}
          </div>
          <select id="event" className="mt-1.5 h-9 w-full rounded-md border bg-background px-2 text-sm outline-none focus-visible:outline-2 focus-visible:outline-ring" {...form.register("emergency_event_id")}>
            <option value="">No linked event</option>
            {events.data?.map((event) => <option key={event.id} value={event.id}>{event.categories[0]?.title ?? "Event"} · {event.title}</option>)}
          </select>
          {events.isError && <p className="mt-1.5 text-xs text-critical">NASA EONET unavailable: {events.error.message}</p>}
          {selected && (
            <div className="mt-1.5 space-y-0.5 text-xs text-muted-foreground">
              <p>{selected.categories.map((category) => category.title).join(", ")}{selected.point ? ` · ${selected.point.lat.toFixed(3)}, ${selected.point.lon.toFixed(3)}` : ""}{selected.state ? ` · ${selected.state}` : ""} · last observed {when(selected.last_observed)}</p>
              {selected.sources.length > 0 && <p className="flex flex-wrap gap-3">{selected.sources.map((source) => <a key={source.url} href={source.url} target="_blank" rel="noreferrer" className="font-medium text-foreground hover:underline">{source.id} →</a>)}</p>}
              <p>Linking stores this event snapshot on the mission. Required supplies are never inferred automatically; enter them below.</p>
            </div>
          )}
        </div>
        <div><Label htmlFor="mission-name">Mission name</Label><Input id="mission-name" className="mt-1.5" placeholder="e.g. Emergency shelter supplies" {...form.register("name")} /></div>
        <div><Label htmlFor="location">Delivery location</Label><Input id="location" className="mt-1.5" placeholder="City, ST" {...form.register("delivery_location")} /></div>
        <div className="grid grid-cols-2 gap-4">
          <div><Label htmlFor="deadline">Delivery deadline</Label><Input id="deadline" className="mt-1.5" type="datetime-local" {...form.register("delivery_deadline")} /></div>
          <div><Label htmlFor="budget">Budget (USD)</Label><Input id="budget" className="mt-1.5" type="number" step="0.01" {...form.register("budget", { valueAsNumber: true })} /></div>
        </div>

        <fieldset>
          <legend className="text-base font-semibold">Items</legend>
          <div className="mt-3 grid grid-cols-[1fr_96px_36px] items-end gap-x-3 gap-y-2">
            <div><Label htmlFor="item">Required item</Label><Input id="item" className="mt-1.5" {...form.register("item")} /></div>
            <div><Label htmlFor="quantity">Quantity</Label><Input id="quantity" className="mt-1.5" type="number" {...form.register("quantity", { valueAsNumber: true })} /></div>
            <span />
            {extra.fields.map((field, index) => (
              <div key={field.id} className="contents">
                <div><Label className="sr-only" htmlFor={`extra-item-${index}`}>Additional line {index + 2} name</Label><Input id={`extra-item-${index}`} {...form.register(`extra.${index}.item`)} /></div>
                <div><Label className="sr-only" htmlFor={`extra-qty-${index}`}>Units</Label><Input id={`extra-qty-${index}`} type="number" {...form.register(`extra.${index}.quantity`, { valueAsNumber: true })} /></div>
                <Button type="button" variant="text" size="icon" aria-label={`Remove line ${index + 2}`} onClick={() => extra.remove(index)}><X /></Button>
              </div>
            ))}
          </div>
          <Button type="button" variant="text" size="sm" className="mt-2 -ml-3" onClick={() => extra.append({ item: "", quantity: 1 })}>Add item</Button>
        </fieldset>

        <div>
          <Label htmlFor="max-share">Max share per supplier (optional)</Label>
          <Input id="max-share" className="mt-1.5" placeholder="e.g. 0.7" {...form.register("max_supplier_share")} />
          <p className="mt-1.5 text-xs text-muted-foreground">A fraction of each item, e.g. 0.7 for 70%. Leave blank for no limit.</p>
        </div>
      </form>
    </SlideOver>
  );
}
