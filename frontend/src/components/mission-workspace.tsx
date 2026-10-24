"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { AppHeader } from "@/components/app-header";
import { EmergencyPanel } from "@/components/mission/emergency-panel";
import { MarketPanel } from "@/components/mission/market-panel";
import { DisruptionConsole, OptimizerPanel, OrdersPanel, PlanComparison, PlanVersions, Timeline } from "@/components/mission/planning-panels";
import { SupplierEvidence } from "@/components/mission/supplier-evidence";
import { useMissionData } from "@/components/mission/use-mission-data";
import { ProvenanceBadge, money, when } from "@/components/status-badges";
import { api } from "@/lib/api";
import { useHydrated, useSession } from "@/hooks/use-session";

type Organization = { id: string; membership_role: string };

export function MissionWorkspace({ missionId }: { missionId: string }) {
  const router = useRouter();
  const session = useSession();
  const hydrated = useHydrated();
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { if (hydrated && (!session || session.user.role !== "coordinator")) router.replace("/sign-in"); }, [hydrated, router, session]);
  const data = useMissionData(missionId, session?.token);
  const organizations = useQuery({ queryKey: ["organizations", session?.token], enabled: Boolean(session), queryFn: () => api<Organization[]>("/v1/organizations", { token: session!.token }) });
  const supplierOrder = useMemo(() => {
    const order: string[] = [];
    for (const plan of [...(data.plans.data ?? [])].reverse()) for (const row of plan.allocations) if (!order.includes(row.supplier_id)) order.push(row.supplier_id);
    for (const row of data.suppliers.data ?? []) if (!order.includes(row.supplier.id)) order.push(row.supplier.id);
    return order;
  }, [data.plans.data, data.suppliers.data]);
  const mission = data.mission.data;
  if (!session || !mission) return <main className="grid min-h-screen place-items-center bg-background text-muted-foreground">{data.mission.error ? data.mission.error.message : "Loading procurement record…"}</main>;
  const token = session.token;
  const run = async (operation: () => Promise<void>) => { setError(null); setNotice(null); try { await operation(); await data.refresh(); } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Request failed"); } };
  const plans = data.plans.data ?? [];
  const latest = plans[0];
  const quotes = data.quotes.data ?? [];
  const suppliers = data.suppliers.data ?? [];
  const jobs = data.jobs.data ?? [];
  const eligible = suppliers.flatMap((row) => row.quotes).filter((quote) => quote.policy.eligible).length;
  const isAdmin = organizations.data?.find((organization) => organization.id === mission.organization_id)?.membership_role === "admin";
  const checking = jobs.some((job) => job.type === "evidence_refresh" && (job.status === "queued" || job.status === "running"));
  const replanning = jobs.some((job) => job.type === "replan" && (job.status === "queued" || job.status === "running"));
  return (
    <main className="min-h-screen bg-background">
      <AppHeader email={session.user.email} home="/dashboard" label="Coordinator" />
      <div className="mx-auto max-w-7xl space-y-5 px-5 py-6">
        <section className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-live">Mission · {mission.delivery_location}</p>
            <h1 className="mt-1 text-3xl font-semibold tracking-tight">{mission.name}</h1>
            <p className="mt-1 text-muted-foreground">Need {mission.requirements.map((item) => `${item.quantity} ${item.item}`).join(", ")} by {when(mission.delivery_deadline)} · Budget {money(mission.budget)}{mission.created_via === "agent" ? " · created by Fetch.ai agent" : ""}</p>
          </div>
          <div className="flex flex-wrap gap-2 font-mono text-xs">
            <span className="rounded border px-2 py-1">quotes <span className="text-telemetry">{quotes.filter((quote) => quote.status === "submitted").length}</span></span>
            <span className="rounded border px-2 py-1">eligible <span className="text-ok">{eligible}</span></span>
            <span className="rounded border px-2 py-1">plan <span className="text-live">{latest ? `v${latest.version} ${latest.status}` : "—"}</span></span>
            {replanning && <span className="rounded border border-live/50 px-2 py-1 text-live">replanning…</span>}
            {checking && <span className="rounded border border-telemetry/50 px-2 py-1 text-telemetry">evidence checks…</span>}
          </div>
        </section>
        {error && <p role="alert" className="rounded-md border border-critical/40 bg-critical/10 p-3 text-sm text-critical">{error}</p>}
        {notice && <p className="rounded-md border border-live/30 bg-live/10 p-3 text-sm text-live">{notice}</p>}

        <EmergencyPanel mission={mission} context={data.context.data} loading={data.context.isLoading} />
        <div className="grid gap-5 xl:grid-cols-[1fr_1.4fr]">
          <MarketPanel mission={mission} token={token} leads={data.leads.data ?? []} invitations={data.invitations.data ?? []} jobs={jobs} run={run} setNotice={setNotice} hasDemo={suppliers.some((row) => row.supplier.is_demo)} />
          <SupplierEvidence missionId={missionId} token={token} rows={suppliers} quotes={quotes} run={run} canReview={isAdmin} checking={checking} />
        </div>
        <OptimizerPanel mission={mission} plan={latest} eligibleCount={eligible} quoteCount={quotes.filter((quote) => quote.status === "submitted").length} busy={replanning} onOptimize={() => void run(async () => { const response = await api<{ plan_id: string; version: number }>(`/v1/missions/${missionId}/optimize`, { method: "POST", token }); setNotice(`Plan v${response.version} computed from current policy-eligible quotes.`); })} />
        {isAdmin && suppliers.length > 0 && <DisruptionConsole missionId={missionId} token={token} rows={suppliers} plan={latest} run={run} disruptions={data.disruptions.data ?? []} setNotice={setNotice} />}
        <PlanComparison plans={plans} approvals={data.approvals.data ?? []} order={supplierOrder} />
        <PlanVersions plans={plans} approvals={data.approvals.data ?? []} token={token} run={run} setNotice={setNotice} order={supplierOrder} isAdmin={isAdmin} />
        <OrdersPanel orders={data.orders.data ?? []} token={token} run={run} setNotice={setNotice} />
        <Timeline notifications={data.notifications.data ?? []} audit={data.audit.data ?? []} verification={data.verification.data} jobs={jobs} />
        <p className="pb-6 text-center text-[11px] text-tertiary">Data labels: <ProvenanceBadge value="LIVE" /> fetched from the public source · <ProvenanceBadge value="CACHED" /> last-known-good copy · <ProvenanceBadge value="SANDBOX" /> sponsor sandbox · <ProvenanceBadge value="USER_SUBMITTED" /> supplier-entered · <ProvenanceBadge value="TEST" /> / <ProvenanceBadge value="SYNTHETIC" /> demo fixtures</p>
      </div>
    </main>
  );
}
