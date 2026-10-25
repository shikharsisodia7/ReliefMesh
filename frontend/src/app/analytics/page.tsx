"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { useOrgMissions, usePerMission } from "@/components/coordinator/use-org-records";
import { Page, PageHeader } from "@/components/layout/page-header";
import { isReplan, rebuildSeconds, secondsText } from "@/components/mission/plan-tab";
import { useHydrated, useSession } from "@/hooks/use-session";
import { api } from "@/lib/api";
import { signInUrl } from "@/lib/session";
import type { Approval, Plan, PurchaseOrder, Quote } from "@/lib/types";

function Figure({ value, label, note }: { value: ReactNode; label: string; note?: string }) {
  return (
    <div className="border-t pt-4">
      <p className="text-4xl font-semibold tracking-tight tabular">{value}</p>
      <p className="mt-1 text-sm font-medium">{label}</p>
      {note && <p className="mt-0.5 text-sm text-muted-foreground">{note}</p>}
    </div>
  );
}

// A few figures computed from this organization's real records. A figure with nothing to compute from is left out.
export default function AnalyticsPage() {
  const router = useRouter();
  const session = useSession();
  const hydrated = useHydrated();
  useEffect(() => { if (hydrated && (!session || session.user.role !== "coordinator")) router.replace(signInUrl()); }, [hydrated, router, session]);
  const token = session?.token;
  const { current, missions } = useOrgMissions(token);
  const quotes = usePerMission<Quote>(token, missions.data, "quotes");
  const plans = usePerMission<Plan>(token, missions.data, "plans");
  const approvals = usePerMission<Approval>(token, missions.data, "approvals");
  const orders = useQuery({ queryKey: ["org-orders", current?.id], enabled: Boolean(token && current), queryFn: () => api<PurchaseOrder[]>(`/v1/purchase-orders?organization_id=${current!.id}`, { token }) });
  const loading = missions.isLoading || quotes.loading || plans.loading || approvals.loading || orders.isLoading;
  const error = missions.error ?? quotes.error ?? plans.error ?? approvals.error ?? orders.error;

  const allMissions = missions.data ?? [];
  const allQuotes = quotes.rows.flatMap(([, rows]) => rows);
  const replans = plans.rows.flatMap(([, rows]) => rows).filter(isReplan).map(rebuildSeconds).filter((seconds): seconds is number => seconds !== null);
  const revoked = approvals.rows.flatMap(([, rows]) => rows).filter((approval) => approval.status === "invalidated").length;
  const sentOrders = (orders.data ?? []).filter((order) => order.status !== "draft");
  const delivered = sentOrders.filter((order) => order.status === "completed").length;
  const average = replans.length ? secondsText(replans.reduce((sum, seconds) => sum + seconds, 0) / replans.length) : null;
  const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

  return (
    <Page>
      <PageHeader title="Analytics" meta={current ? <>{current.name}{current.is_demo && " · DEMO ORG"} · from this organization&apos;s records</> : undefined} />
      <div className="mt-10">
        {error ? <p className="text-sm text-critical">{error.message}</p>
          : loading ? <div className="grid gap-8 sm:grid-cols-3" aria-label="Loading figures">{[0, 1, 2].map((key) => <div key={key} className="h-20 animate-pulse rounded bg-muted motion-reduce:animate-none" />)}</div>
            : allMissions.length === 0 ? <p className="text-sm text-muted-foreground">No missions yet, so there&apos;s nothing to measure.</p>
              : (
                <div className="grid gap-x-12 gap-y-10 sm:grid-cols-2 lg:grid-cols-3">
                  <Figure value={allMissions.length} label="Missions" note={`${allMissions.filter((mission) => mission.status === "open").length} open`} />
                  <Figure value={allQuotes.length} label="Quotes received" note={`${allQuotes.filter((quote) => quote.status === "submitted").length} still active`} />
                  {average && <Figure value={`${average} s`} label="Average replan time" note={`Over ${plural(replans.length, "automatic replan")}, from the change to the new plan`} />}
                  <Figure value={revoked} label="Approvals revoked" note="Approvals never carry over to a changed plan" />
                  {sentOrders.length > 0 && <Figure value={delivered} label="POs delivered" note={`Of ${plural(sentOrders.length, "sent purchase order")}`} />}
                </div>
              )}
        <p className="mt-12 max-w-2xl text-sm text-muted-foreground">Coming soon: trends over time and supplier response times, once the API keeps that history.</p>
      </div>
    </Page>
  );
}
