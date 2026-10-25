"use client";

import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Page, PageHeader } from "@/components/layout/page-header";
import { MissionForm } from "@/components/mission-form";
import { OrganizationForm } from "@/components/organization-form";
import { money, when } from "@/components/status-badges";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { signInUrl } from "@/lib/session";
import { api } from "@/lib/api";
import type { Mission } from "@/lib/types";
import { useCreateOrganization, useOrganizations } from "@/hooks/use-organizations";
import { useHydrated, useSession } from "@/hooks/use-session";

export default function DashboardPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const session = useSession();
  const [error, setError] = useState<string | null>(null);
  const hydrated = useHydrated();
  useEffect(() => { if (hydrated && (!session || session.user.role !== "coordinator")) router.replace(signInUrl()); }, [hydrated, router, session]);
  const { organizations, current } = useOrganizations(session?.token);
  const createOrganization = useCreateOrganization(session?.token);
  const selectedOrganizationId = current?.id ?? null;
  const missions = useQuery({ queryKey: ["missions", selectedOrganizationId], enabled: Boolean(session && selectedOrganizationId), queryFn: () => api<Mission[]>(`/v1/missions?organization_id=${selectedOrganizationId}`, { token: session!.token }) });
  if (!session) return <Page><p className="text-sm text-muted-foreground">Loading your workspace…</p></Page>;
  // Someone with no organization yet gets a single prompt; more organizations are created in Settings.
  if (organizations.data?.length === 0) return (
    <Page className="grid place-items-center pt-24">
      <section className="w-full max-w-md text-center">
        <h1 className="text-xl font-semibold">Create your organization to start a mission</h1>
        {error && <p role="alert" className="mt-3 text-sm text-critical">{error}</p>}
        <div className="mt-6 text-left"><OrganizationForm onSubmit={async (values) => { setError(null); try { await createOrganization(values); } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Could not create organization"); } }} /></div>
      </section>
    </Page>
  );
  return (
    <Page className="space-y-8">
      <PageHeader title="Missions" meta={current ? <>{current.name}{current.is_demo && " · DEMO ORG"}</> : undefined} />
      {error && <p role="alert" className="text-sm text-critical">{error}</p>}
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
            <div><div className="flex items-center gap-2"><h3 className="font-semibold">{mission.name}</h3><span className="rounded border px-1.5 font-mono text-[10px] uppercase text-muted-foreground">{mission.status}</span>{mission.created_via === "agent" && <span className="text-xs font-medium tracking-wide text-muted-foreground">FETCH AGENT</span>}</div>
              <p className="mt-1 text-sm text-muted-foreground">{mission.requirements.map((requirement) => `${requirement.quantity} ${requirement.item}`).join(", ")} · {mission.delivery_location} · {money(mission.budget)} · by {when(mission.delivery_deadline)}</p>
              {mission.emergency_event && <p className="mt-0.5 text-xs text-live">{mission.emergency_event.title}</p>}</div>
            <Link className="inline-flex h-8 items-center rounded-lg bg-primary px-3 text-sm font-medium text-primary-foreground" href={`/missions/${mission.id}`}>Open workflow</Link>
          </CardContent></Card>))}</div>
          : <Card><CardContent className="py-8 text-sm text-muted-foreground">Create your first mission to begin sourcing.</CardContent></Card>}
      </section>
    </Page>
  );
}
