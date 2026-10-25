"use client";

import { useQuery } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Page, PageHeader } from "@/components/layout/page-header";
import { ApprovalTab } from "@/components/mission/approval-tab";
import { AuditTab } from "@/components/mission/audit-tab";
import { EmergencyPanel } from "@/components/mission/emergency-panel";
import { MissionMenu } from "@/components/mission/lifecycle-controls";
import { LeadsSection, MarketActions } from "@/components/mission/market-panel";
import { OrdersTab } from "@/components/mission/orders-tab";
import { ExplainDrawer, PlanTab, isReplan, rebuildSeconds, secondsText } from "@/components/mission/plan-tab";
import { SupplierEvidence } from "@/components/mission/supplier-evidence";
import { useMissionData } from "@/components/mission/use-mission-data";
import { showToast } from "@/components/patterns/toast";
import { TabPanel, UnderlineTabs } from "@/components/patterns/underline-tabs";
import { Provenance } from "@/components/status-badges";
import { RecoveryImpactPanel } from "@/components/mission/recovery-impact-panel";
import { Button } from "@/components/ui/button";
import { signInUrl } from "@/lib/session";
import { api } from "@/lib/api";
import { useAppConfig } from "@/hooks/use-config";
import { useOrganizations } from "@/hooks/use-organizations";
import { useHydrated, useSession } from "@/hooks/use-session";

const stages = ["context", "evidence", "plan", "approval", "orders", "audit"] as const;
const running = (status: string) => status === "queued" || status === "running";

export function MissionWorkspace({ missionId }: { missionId: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const session = useSession();
  const hydrated = useHydrated();
  // A notice belongs to the plan version it was raised on, so it clears once a newer plan arrives.
  const [notice, setNoticeState] = useState<{ text: string; version?: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [explaining, setExplaining] = useState(false);
  useEffect(() => { if (hydrated && (!session || session.user.role !== "coordinator")) router.replace(signInUrl()); }, [hydrated, router, session]);
  const data = useMissionData(missionId, session?.token);
  const appConfig = useAppConfig();
  const { demoMode, approvalTtlMinutes } = appConfig;
  const { organizations } = useOrganizations(session?.token);
  const mission = data.mission.data;
  // Members give the requester's email for the approval chain.
  const members = useQuery({
    queryKey: ["members", mission?.organization_id], enabled: Boolean(session && mission),
    queryFn: () => api<{ members: { user_id: string; email: string | null }[] }>(`/v1/organizations/${mission!.organization_id}/members`, { token: session!.token }),
  });
  const latest = data.plans.data?.[0];
  const setTab = (next: string) => router.replace(`${pathname}?tab=${next}`, { scroll: false });
  const setNotice = (text: string) => setNoticeState({ text, version: latest?.version });

  // After an automatic replan, bring the user to the new plan with a quiet toast.
  const seenVersion = useRef<number | null>(null);
  useEffect(() => {
    if (!latest) return;
    const seen = seenVersion.current;
    seenVersion.current = latest.version;
    if (seen === null || latest.version <= seen || !isReplan(latest)) return;
    const seconds = rebuildSeconds(latest);
    showToast(`Plan v${latest.version} ready${seconds !== null ? ` · rebuilt in ${secondsText(seconds)} s` : ""}`);
    router.replace(`${pathname}?tab=plan`, { scroll: false });
    window.scrollTo({ top: 0, behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }, [latest, pathname, router]);

  if (!session || !mission) return <Page><p className="text-sm text-muted-foreground">{data.mission.error ? data.mission.error.message : "Loading procurement record…"}</p></Page>;
  const token = session.token;
  const run = async (operation: () => Promise<void>) => { setError(null); setNoticeState(null); try { await operation(); await data.refresh(); } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Request failed"); } };
  const plans = data.plans.data ?? [];
  const quotes = data.quotes.data ?? [];
  const suppliers = data.suppliers.data ?? [];
  const jobs = data.jobs.data ?? [];
  const eligible = suppliers.flatMap((row) => row.quotes).filter((quote) => quote.policy.eligible).length;
  const submitted = quotes.filter((quote) => quote.status === "submitted").length;
  const organization = organizations.data?.find((row) => row.id === mission.organization_id);
  const isAdmin = organization?.membership_role === "admin";
  // Segregation of duties: approvers are admins/approvers who did not request this mission (DEMO orgs excepted).
  const canApprove = (organization?.membership_role === "admin" || organization?.membership_role === "approver")
    && (mission.created_by !== session.user.id || Boolean(organization?.is_demo));
  const approvalBlocked = mission.created_by === session.user.id && !organization?.is_demo ? "You requested this mission, so another approver in your organization must approve its plan." : null;
  const requester = mission.created_by === session.user.id ? "you"
    : members.data?.members.find((member) => member.user_id === mission.created_by)?.email ?? (mission.created_via === "agent" ? "the Fetch.ai agent" : "the mission's requester");
  // Audit actors by email where the organization's member list knows them.
  const actorName = (id: string | null) => id === null ? "System" : id === session.user.id ? "You"
    : members.data?.members.find((member) => member.user_id === id)?.email ?? `User ${id.slice(0, 6)}`;
  const checking = jobs.some((job) => job.type === "evidence_refresh" && running(job.status));
  const replanning = jobs.some((job) => job.type === "replan" && running(job.status));
  const continuityRunning = jobs.some((job) => job.type === "continuity_analysis" && running(job.status));
  const cancelled = mission.status === "cancelled";
  const requested = params.get("tab");
  // Until a tab is chosen, open on the plan if there is one, otherwise on suppliers.
  const tab = stages.find((stage) => stage === requested) ?? (data.plans.isFetched ? (plans.length ? "plan" : "evidence") : null);
  const activity = [
    cancelled && "Cancelled. Plans are stale and no further replanning runs; issued purchase orders must be cancelled with each supplier.",
    replanning && "Replanning…",
    checking && "Evidence checks running…",
    continuityRunning && "Continuity analysis running…",
  ].filter(Boolean).join(" · ");
  const optimize = () => void run(async () => {
    const response = await api<{ plan_id: string; version: number }>(`/v1/missions/${missionId}/optimize`, { method: "POST", token });
    setNotice(`Plan v${response.version} computed from current policy-eligible quotes.`);
  });

  return (
    <Page>
      <PageHeader
        breadcrumb={[{ label: "Missions", href: "/dashboard" }, { label: mission.name }]}
        title={mission.name}
        meta={<>{organization?.name}{organization?.is_demo && " · DEMO ORG"}{mission.created_via === "agent" && " · created by Fetch.ai agent"}</>}
        activity={activity || undefined}
        actions={<>
          {latest && plans[1] && <Button variant="text" onClick={() => setExplaining(true)}>Explain changes</Button>}
          {!cancelled && (isAdmin || organization?.membership_role === "coordinator") && <MissionMenu mission={mission} token={token} run={run} setNotice={setNotice} />}
        </>}
      />
      {error && <p role="alert" className="mt-4 text-sm text-critical">{error}</p>}
      {notice && notice.version === latest?.version && <p className="mt-4 text-sm break-all">{notice.text}</p>}
      {latest && plans[1] && <ExplainDrawer open={explaining} onOpenChange={setExplaining} plan={latest} previous={plans[1]} suppliers={suppliers} />}

      {tab && (
        <div className="mt-8">
          <UnderlineTabs label="Mission stages" value={tab} onValueChange={setTab} items={[
            { value: "context", label: "Context" },
            { value: "evidence", label: "Suppliers & Evidence" },
            { value: "plan", label: <>Plan{latest?.status === "feasible" && <span className="font-normal text-muted-foreground"> · needs approval</span>}</> },
            { value: "approval", label: "Approval" },
            { value: "orders", label: "Orders" },
            { value: "audit", label: "Audit" },
          ]}>
            <TabPanel value="context"><EmergencyPanel mission={mission} context={data.context.data} loading={data.context.isLoading} /></TabPanel>
            <TabPanel value="evidence">
              <SupplierEvidence missionId={missionId} token={token} rows={suppliers} quotes={quotes} run={run} canReview={isAdmin} checking={checking}
                actions={<MarketActions mission={mission} token={token} invitations={data.invitations.data ?? []} jobs={jobs} run={run} setNotice={setNotice} canSeed={demoMode && !suppliers.some((row) => row.supplier.is_demo)} />} />
              <LeadsSection token={token} leads={data.leads.data ?? []} jobs={jobs} run={run} setNotice={setNotice} />
              <p className="mt-12 text-xs text-muted-foreground">Data labels: <Provenance value="LIVE" /> fetched from the public source · <Provenance value="CACHED" /> last-known-good copy · <Provenance value="SANDBOX" /> sponsor sandbox · <Provenance value="USER_SUBMITTED" /> supplier-entered{demoMode && <> · <Provenance value="TEST" /> / <Provenance value="SYNTHETIC" /> demo</>} fixtures</p>
            </TabPanel>
            <TabPanel value="plan">
              <div className="space-y-5">
              <PlanTab
                mission={mission} plans={plans} approvals={data.approvals.data ?? []} quotes={quotes} suppliers={suppliers} continuity={data.continuity.data} disruptions={data.disruptions.data ?? []}
                token={token} run={run} setNotice={setNotice} onTab={setTab} onOptimize={optimize}
                canApprove={canApprove} approvalBlocked={approvalBlocked} requester={requester} showDemo={demoMode && isAdmin && suppliers.length > 0} approvalTtlMinutes={approvalTtlMinutes}
                busy={replanning} continuityRunning={continuityRunning} eligibleCount={eligible} quoteCount={submitted}
              />
              <RecoveryImpactPanel mission={mission} plans={plans} approvals={data.approvals.data ?? []} jobs={jobs} orders={data.orders.data ?? []} verification={data.verification.data} loading={data.plans.isLoading} token={token} claudeEnabled={appConfig.data?.claude_recovery_explanation === true} />
              </div>
            </TabPanel>
            <TabPanel value="approval">
              <ApprovalTab plans={plans} approvals={data.approvals.data ?? []} demoOrg={Boolean(organization?.is_demo)} canApprove={canApprove} approvalBlocked={approvalBlocked} requester={requester} ttlMinutes={approvalTtlMinutes}
                token={token} run={run} setNotice={setNotice} onTab={setTab} />
            </TabPanel>
            <TabPanel value="orders">
              <OrdersTab missionId={missionId} organizationId={mission.organization_id} plans={plans} approvals={data.approvals.data ?? []} orders={data.orders.data ?? []} quotes={quotes} suppliers={suppliers}
                token={token} run={run} setNotice={setNotice} isAdmin={isAdmin} onTab={setTab} />
            </TabPanel>
            <TabPanel value="audit">
              <AuditTab audit={data.audit.data ?? []} verification={data.verification.data} jobs={jobs} notifications={data.notifications.data ?? []} payments={data.payments.data ?? []} actorName={actorName} />
            </TabPanel>
          </UnderlineTabs>
        </div>
      )}
    </Page>
  );
}
