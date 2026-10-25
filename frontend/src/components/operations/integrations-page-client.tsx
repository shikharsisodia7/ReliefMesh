"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { AppHeader } from "@/components/app-header";
import { IntegrationsSettings } from "@/components/operations/integrations-settings";
import { Button } from "@/components/ui/button";
import { api, type ApiError } from "@/lib/api";
import { clearSession, signInUrl } from "@/lib/session";
import { useHydrated, useSession } from "@/hooks/use-session";

type Organization = { id: string; name: string; membership_role: string };

function oauthNotice(params: URLSearchParams): string | null {
  for (const provider of ["google", "slack"] as const) {
    const outcome = params.get(provider);
    const name = provider === "google" ? "Google" : "Slack";
    if (outcome === "connected") return `${name} connected. Use “Send test” to make a first real call.`;
    if (outcome === "error") return `${name} connection was not completed: ${params.get("reason") ?? "unknown error"}`;
  }
  return null;
}

export function IntegrationsPageClient() {
  const router = useRouter();
  const params = useSearchParams();
  const session = useSession();
  const hydrated = useHydrated();
  const [organizationId, setOrganizationId] = useState<string | null>(params.get("org"));
  useEffect(() => { if (hydrated && (!session || session.user.role !== "coordinator")) router.replace(signInUrl()); }, [hydrated, router, session]);
  const organizations = useQuery({ queryKey: ["organizations", session?.token], enabled: Boolean(session), queryFn: () => api<Organization[]>("/v1/organizations", { token: session!.token }) });
  const selected = organizationId ?? organizations.data?.[0]?.id ?? null;
  const expired = (organizations.error as ApiError | null)?.status === 401;
  // A token for a deleted or revoked account must not leave a blank settings page: start a fresh sign-in.
  useEffect(() => { if (expired) { clearSession(); router.replace(signInUrl()); } }, [expired, router]);
  if (!session) return <main className="grid min-h-screen place-items-center bg-background text-muted-foreground">Loading…</main>;
  return (
    <main className="min-h-screen bg-background">
      <AppHeader email={session.user.email} home="/dashboard" label="Coordinator" />
      <div className="mx-auto max-w-5xl space-y-6 px-5 py-8">
        <section>
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-live">Organization settings</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight">Operations integrations</h1>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">Carry the procurement workflow into the tools your team already uses: RFQs and purchase orders by Gmail, deadlines on Google Calendar, alerts in Slack, and document copies in Drive. These are notification layers only — ReliefMesh remains the record, and money moves only after approval inside ReliefMesh.</p>
        </section>
        {(organizations.data?.length ?? 0) > 1 && (
          <div className="flex flex-wrap gap-2">{organizations.data!.map((row) => <Button key={row.id} size="sm" variant={row.id === selected ? "primary" : "secondary"} onClick={() => setOrganizationId(row.id)}>{row.name} · {row.membership_role}</Button>)}</div>
        )}
        {organizations.isError && !expired && <p role="alert" className="rounded-md border border-critical/40 bg-critical/10 p-3 text-sm text-critical">{organizations.error.message}</p>}
        {organizations.data?.length === 0 && <p className="text-muted-foreground">Create an organization on the dashboard first.</p>}
        {selected && <IntegrationsSettings key={selected} organizationId={selected} token={session.token} notice={selected === params.get("org") ? oauthNotice(params) : null} />}
      </div>
    </main>
  );
}
