"use client";

import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { AppHeader } from "@/components/app-header";
import { MembersPanel } from "@/components/members-panel";
import { MissionForm } from "@/components/mission-form";
import { OrganizationForm } from "@/components/organization-form";
import { money, when } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { signInUrl } from "@/lib/session";
import { api } from "@/lib/api";
import type { Mission } from "@/lib/types";
import { useHydrated, useSession } from "@/hooks/use-session";

type Organization = { id: string; name: string; membership_role: string; is_demo?: boolean };

export default function DashboardPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const session = useSession();
  const [organizationId, setOrganizationId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const hydrated = useHydrated();
  useEffect(() => { if (hydrated && (!session || session.user.role !== "coordinator")) router.replace(signInUrl()); }, [hydrated, router, session]);
  const organizations = useQuery({ queryKey: ["organizations", session?.token], enabled: Boolean(session), queryFn: () => api<Organization[]>("/v1/organizations", { token: session!.token }) });
  const selectedOrganizationId = organizationId ?? organizations.data?.[0]?.id ?? null;
  const missions = useQuery({ queryKey: ["missions", selectedOrganizationId], enabled: Boolean(session && selectedOrganizationId), queryFn: () => api<Mission[]>(`/v1/missions?organization_id=${selectedOrganizationId}`, { token: session!.token }) });
  if (!session) return <main className="grid min-h-screen place-items-center bg-background text-muted-foreground">Loading your workspace…</main>;
  return (
    <main className="min-h-screen bg-background">
      <AppHeader email={session.user.email} home="/dashboard" label="Coordinator" />
      <div className="mx-auto max-w-6xl space-y-7 px-5 py-8">
        <section><p className="font-mono text-xs uppercase tracking-[0.2em] text-live">Coordinator workspace</p><h1 className="mt-1 text-3xl font-semibold tracking-tight">Missions that stay defensible under change.</h1></section>
        {error && <p role="alert" className="rounded-md border border-critical/40 bg-critical/10 p-3 text-sm text-critical">{error}</p>}
        <Card><CardHeader><CardTitle>Organization</CardTitle><CardDescription>Create or choose the buyer organization that owns this procurement record.</CardDescription></CardHeader><CardContent className="space-y-4">
          <OrganizationForm onSubmit={async (values) => { try { const created = await api<Organization>("/v1/organizations", { method: "POST", body: JSON.stringify(values), token: session.token }); await queryClient.invalidateQueries({ queryKey: ["organizations"] }); setOrganizationId(created.id); } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Could not create organization"); } }} />
          <div className="flex flex-wrap gap-2">{organizations.data?.map((organization) => <Button key={organization.id} size="sm" variant={organization.id === selectedOrganizationId ? "default" : "outline"} onClick={() => setOrganizationId(organization.id)}>{organization.name}{organization.is_demo ? " · DEMO" : ""} · {organization.membership_role}</Button>)}</div>
          {selectedOrganizationId && <MembersPanel organizationId={selectedOrganizationId} token={session.token} isAdmin={organizations.data?.find((organization) => organization.id === selectedOrganizationId)?.membership_role === "admin"} />}
        </CardContent></Card>
        {selectedOrganizationId && <Card><CardHeader><CardTitle>New mission</CardTitle><CardDescription>Link a real emergency, then state exactly what must be bought. Quotes, evidence, and plans stay scoped to this organization.</CardDescription></CardHeader><CardContent>
          <MissionForm onSubmit={async (values) => { try {
            const requirements = [{ item: values.item, quantity: values.quantity }, ...values.extra];
            const created = await api<Mission>("/v1/missions", { method: "POST", token: session.token, body: JSON.stringify({
              organization_id: selectedOrganizationId, name: values.name, delivery_location: values.delivery_location,
              delivery_deadline: new Date(values.delivery_deadline).toISOString(), budget: values.budget.toFixed(2), currency: "USD", requirements,
              emergency_event_id: values.emergency_event_id || null, max_supplier_share: values.max_supplier_share ? values.max_supplier_share : null,
            }) });
            await queryClient.invalidateQueries({ queryKey: ["missions", selectedOrganizationId] });
            router.push(`/missions/${created.id}`);
          } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Could not create mission"); } }} />
        </CardContent></Card>}
        <section><div className="mb-3 flex items-center justify-between"><h2 className="text-xl font-semibold">Active missions</h2>{missions.isFetching && <span className="text-sm text-muted-foreground">Refreshing…</span>}</div>
          {missions.data?.length ? <div className="grid gap-3">{missions.data.map((mission) => (
            <Card key={mission.id}><CardContent className="flex flex-col gap-4 py-5 sm:flex-row sm:items-center sm:justify-between">
              <div><div className="flex items-center gap-2"><h3 className="font-semibold">{mission.name}</h3><span className="rounded border px-1.5 font-mono text-[10px] uppercase text-muted-foreground">{mission.status}</span>{mission.created_via === "agent" && <span className="rounded border border-violet-400/40 px-1.5 font-mono text-[10px] text-violet-300">FETCH AGENT</span>}</div>
                <p className="mt-1 text-sm text-muted-foreground">{mission.requirements.map((requirement) => `${requirement.quantity} ${requirement.item}`).join(", ")} · {mission.delivery_location} · {money(mission.budget)} · by {when(mission.delivery_deadline)}</p>
                {mission.emergency_event && <p className="mt-0.5 text-xs text-live">{mission.emergency_event.title}</p>}</div>
              <Link className="inline-flex h-8 items-center rounded-lg bg-primary px-3 text-sm font-medium text-primary-foreground" href={`/missions/${mission.id}`}>Open workflow</Link>
            </CardContent></Card>))}</div>
            : <Card><CardContent className="py-8 text-sm text-muted-foreground">Create your first mission to begin sourcing.</CardContent></Card>}
        </section>
      </div>
    </main>
  );
}
