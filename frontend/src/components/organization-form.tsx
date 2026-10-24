"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAppConfig } from "@/hooks/use-config";

const schema = z.object({ name: z.string().min(2, "Enter your organization name"), demo: z.boolean() });

export function OrganizationForm({ onSubmit }: { onSubmit: (values: z.infer<typeof schema>) => Promise<void> }) {
  const form = useForm<z.infer<typeof schema>>({ resolver: zodResolver(schema), defaultValues: { name: "", demo: false } });
  const { demoMode } = useAppConfig();
  return (
    <form className="flex flex-wrap items-center gap-3" onSubmit={form.handleSubmit(async (values) => { await onSubmit(values); form.reset(); })}>
      <div className="min-w-60 flex-1"><Label className="sr-only" htmlFor="organization-name">Organization name</Label><Input id="organization-name" placeholder="Organization name" {...form.register("name")} /></div>
      {demoMode && <label className="flex items-center gap-2 text-xs text-muted-foreground" title="Demo organizations may self-approve; every approval is labeled DEMO override. Real organizations require an independent approver.">
        <input type="checkbox" className="size-4 accent-[var(--telemetry)]" {...form.register("demo")} />Demo organization (labeled self-approval)
      </label>}
      <Button type="submit" disabled={form.formState.isSubmitting}>{form.formState.isSubmitting ? "Creating…" : "Create organization"}</Button>
    </form>
  );
}
