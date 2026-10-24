"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const schema = z.object({ name: z.string().min(2), delivery_location: z.string().min(2), delivery_deadline: z.string().min(1), budget: z.number().positive(), item: z.string().min(1), quantity: z.number().int().positive() });
type Values = z.infer<typeof schema>;

export function MissionForm({ onSubmit }: { onSubmit: (values: Values) => Promise<void> }) {
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { name: "", delivery_location: "", delivery_deadline: "", budget: 5000, item: "blankets", quantity: 100 } });
  return <form className="grid gap-4 sm:grid-cols-2" onSubmit={form.handleSubmit(async (values) => { await onSubmit(values); form.reset(); })}>
    <div><Label htmlFor="mission-name">Mission name</Label><Input id="mission-name" className="mt-1" placeholder="e.g. Storm shelter supplies" {...form.register("name")} /></div>
    <div><Label htmlFor="location">Delivery location</Label><Input id="location" className="mt-1" placeholder="City, state" {...form.register("delivery_location")} /></div>
    <div><Label htmlFor="deadline">Delivery deadline</Label><Input id="deadline" className="mt-1" type="datetime-local" {...form.register("delivery_deadline")} /></div>
    <div><Label htmlFor="budget">Budget (USD)</Label><Input id="budget" className="mt-1" type="number" step="0.01" {...form.register("budget", { valueAsNumber: true })} /></div>
    <div><Label htmlFor="item">Required item</Label><Input id="item" className="mt-1" {...form.register("item")} /></div>
    <div><Label htmlFor="quantity">Quantity</Label><Input id="quantity" className="mt-1" type="number" {...form.register("quantity", { valueAsNumber: true })} /></div>
    <Button className="sm:col-span-2" type="submit" disabled={form.formState.isSubmitting}>{form.formState.isSubmitting ? "Creating…" : "Create mission"}</Button>
  </form>;
}
