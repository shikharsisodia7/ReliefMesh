"use client";

import { Menu } from "@base-ui/react/menu";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { MissionRow } from "@/components/dashboard/mission-row";
import { MissionsMap } from "@/components/dashboard/missions-map";
import { Page, PageHeader } from "@/components/layout/page-header";
import { NewMissionSlideOver } from "@/components/mission-form";
import { OrganizationForm } from "@/components/organization-form";
import { Button } from "@/components/ui/button";
import { useCreateOrganization, useOrganizations } from "@/hooks/use-organizations";
import { useHydrated, useSession } from "@/hooks/use-session";
import { api } from "@/lib/api";
import { signInUrl } from "@/lib/session";
import type { Mission, Organization } from "@/lib/types";

const itemClass = "flex w-full cursor-default items-center gap-2 px-3 py-2 text-left text-sm text-foreground outline-hidden select-none data-[highlighted]:bg-muted";

// The organization as plain text with a chevron; the menu switches between the user's organizations.
function OrganizationSwitcher({ rows, current, select }: { rows: Organization[]; current: Organization; select: (id: string) => void }) {
  return (
    <Menu.Root>
      <Menu.Trigger className="inline-flex items-center gap-1 rounded-sm text-muted-foreground outline-hidden hover:text-foreground focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring" aria-label={`${current.name}${current.is_demo ? " · DEMO ORG" : ""}, switch organization`}>
        {current.name}{current.is_demo && " · DEMO ORG"}<ChevronDown className="size-4" />
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Positioner align="start" sideOffset={6} className="z-50">
          <Menu.Popup className="w-72 rounded-lg border bg-background py-1.5 shadow-lg outline-hidden">
            <Menu.RadioGroup value={current.id} onValueChange={(value) => select(String(value))}>
              {rows.map((row) => (
                <Menu.RadioItem key={row.id} value={row.id} className={itemClass}>
                  <span className="min-w-0 flex-1 truncate">{row.name}{row.is_demo && <span className="ml-2 text-xs text-muted-foreground">DEMO ORG</span>}</span>
                  <Menu.RadioItemIndicator><Check className="size-4" /></Menu.RadioItemIndicator>
                </Menu.RadioItem>
              ))}
            </Menu.RadioGroup>
            <Menu.Separator className="my-1.5 h-px bg-border" />
            <Menu.LinkItem closeOnClick render={<Link href="/settings" />} className={itemClass}>Manage organizations in Settings</Menu.LinkItem>
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
  );
}

export default function DashboardPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const session = useSession();
  const hydrated = useHydrated();
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  useEffect(() => { if (hydrated && (!session || session.user.role !== "coordinator")) router.replace(signInUrl()); }, [hydrated, router, session]);
  const { organizations, current, select } = useOrganizations(session?.token);
  const createOrganization = useCreateOrganization(session?.token);
  const organizationId = current?.id ?? null;
  const missions = useQuery({ queryKey: ["missions", organizationId], enabled: Boolean(session && organizationId), queryFn: () => api<Mission[]>(`/v1/missions?organization_id=${organizationId}`, { token: session!.token }) });
  if (!session) return <Page><p className="text-sm text-muted-foreground">Loading your workspace…</p></Page>;

  // Someone with no organization yet gets a single prompt; more organizations are created in Settings.
  if (organizations.data?.length === 0) return (
    <Page className="grid place-items-center pt-24">
      <section className="w-full max-w-md text-center">
        <h1 className="text-xl font-semibold">Create your organization to start a mission</h1>
        <p className="mt-2 text-sm text-muted-foreground">Missions, quotes, evidence, and plans stay scoped to it. You can add members in Settings.</p>
        {error && <p role="alert" className="mt-3 text-sm text-critical">{error}</p>}
        <div className="mt-6 text-left"><OrganizationForm onSubmit={async (values) => { setError(null); try { await createOrganization(values); } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Could not create organization"); } }} /></div>
      </section>
    </Page>
  );

  const rows = missions.data ?? [];
  return (
    <Page>
      <PageHeader
        title="Missions"
        meta={current && <OrganizationSwitcher rows={organizations.data ?? []} current={current} select={select} />}
        actions={organizationId && <Button size="lg" onClick={() => { setError(null); setCreating(true); }}>New mission</Button>}
      />
      <div className="mt-10 grid gap-12 lg:grid-cols-[minmax(0,55fr)_minmax(0,40fr)] lg:justify-between">
        <section aria-label="Active missions">
          <h2 className="border-b pb-3 text-sm font-medium text-muted-foreground">Active missions</h2>
          {missions.isError ? <p className="mt-4 text-sm text-critical">{missions.error.message} <button type="button" className="font-medium text-foreground hover:underline" onClick={() => void missions.refetch()}>Retry</button></p>
            : missions.isLoading ? <div className="mt-6 space-y-3" aria-label="Loading missions">{[0, 1].map((key) => <div key={key} className="h-16 animate-pulse rounded bg-muted motion-reduce:animate-none" />)}</div>
              : rows.length === 0 ? <p className="mt-6 text-sm text-muted-foreground">No missions yet. Start one with New mission.</p>
                : <ul>{rows.map((mission) => <MissionRow key={mission.id} mission={mission} token={session.token} />)}</ul>}
        </section>
        <MissionsMap missions={rows} />
      </div>
      {organizationId && (
        <NewMissionSlideOver
          open={creating} onOpenChange={setCreating} error={error}
          onSubmit={async (values) => {
            setError(null);
            try {
              const requirements = [{ item: values.item, quantity: values.quantity }, ...values.extra];
              const created = await api<Mission>("/v1/missions", { method: "POST", token: session.token, body: JSON.stringify({
                organization_id: organizationId, name: values.name, delivery_location: values.delivery_location,
                delivery_deadline: new Date(values.delivery_deadline).toISOString(), budget: values.budget.toFixed(2), currency: "USD", requirements,
                emergency_event_id: values.emergency_event_id || null, max_supplier_share: values.max_supplier_share ? values.max_supplier_share : null,
              }) });
              await queryClient.invalidateQueries({ queryKey: ["missions", organizationId] });
              router.push(`/missions/${created.id}`);
            } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Could not create mission"); }
          }}
        />
      )}
    </Page>
  );
}
