"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const schema = z.object({ name: z.string().min(2, "Enter your organization name") });

export function OrganizationForm({ onSubmit }: { onSubmit: (values: z.infer<typeof schema>) => Promise<void> }) {
  const form = useForm<z.infer<typeof schema>>({ resolver: zodResolver(schema), defaultValues: { name: "" } });
  return <form className="flex flex-wrap gap-3" onSubmit={form.handleSubmit(async (values) => { await onSubmit(values); form.reset(); })}><div className="min-w-60 flex-1"><Label className="sr-only" htmlFor="organization-name">Organization name</Label><Input id="organization-name" placeholder="Organization name" {...form.register("name")} /></div><Button type="submit" disabled={form.formState.isSubmitting}>{form.formState.isSubmitting ? "Creating…" : "Create organization"}</Button></form>;
}
