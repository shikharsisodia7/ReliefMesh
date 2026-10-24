"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const schema = z.object({ item: z.string().min(1), unit_price: z.number().positive(), available_quantity: z.number().int().positive(), shipping_cost: z.number().nonnegative(), delivery_date: z.string().min(1), expires_at: z.string().min(1) });
type Values = z.infer<typeof schema>;

export function QuoteForm({ item, onSubmit }: { item: string; onSubmit: (values: Values) => Promise<void> }) {
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { item, unit_price: 0, available_quantity: 0, shipping_cost: 0, delivery_date: "", expires_at: "" } });
  return <form className="grid gap-4 sm:grid-cols-2" onSubmit={form.handleSubmit(async (values) => { await onSubmit(values); })}>
    <div><Label htmlFor="item">Item</Label><Input id="item" className="mt-1" {...form.register("item")} /></div><div><Label htmlFor="quantity">Available quantity</Label><Input id="quantity" className="mt-1" type="number" {...form.register("available_quantity", { valueAsNumber: true })} /></div>
    <div><Label htmlFor="price">Unit price (USD)</Label><Input id="price" className="mt-1" type="number" step="0.01" {...form.register("unit_price", { valueAsNumber: true })} /></div><div><Label htmlFor="shipping">Shipping (USD)</Label><Input id="shipping" className="mt-1" type="number" step="0.01" {...form.register("shipping_cost", { valueAsNumber: true })} /></div>
    <div><Label htmlFor="delivery">Delivery estimate</Label><Input id="delivery" className="mt-1" type="datetime-local" {...form.register("delivery_date")} /></div><div><Label htmlFor="expiration">Quote expiration</Label><Input id="expiration" className="mt-1" type="datetime-local" {...form.register("expires_at")} /></div>
    <Button className="sm:col-span-2" type="submit" disabled={form.formState.isSubmitting}>{form.formState.isSubmitting ? "Submitting…" : "Submit binding quote"}</Button>
  </form>;
}
