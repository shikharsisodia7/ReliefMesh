"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Page, PageHeader } from "@/components/layout/page-header";
import { useMissionData } from "@/components/mission/use-mission-data";
import { Provenance, StatusText, money } from "@/components/status-badges";
import { useOrganizations } from "@/hooks/use-organizations";
import { useSession } from "@/hooks/use-session";
import { api } from "@/lib/api";
import type { Mission } from "@/lib/types";

// Continuity states as words; the API codes stay in the stored record.
const continuityWords: Record<string, string> = { NOT_READY: "Not run for the current plan yet", RUNNING: "Running", COMPLETE: "Current", STALE: "Out of date: inputs changed" };

const THESIS = "ReliefMesh does not just create a procurement plan. It determines whether that plan can survive disruption, shows exactly what breaks it, calculates the cheapest resilient alternative, and automatically rebuilds the plan when reality changes.";

const TRUTH: { title: string; items: string[] }[] = [
  { title: "What is live?", items: [
    "Disasters: NASA EONET events, NWS alerts, NASA FIRMS fire detections, OpenFEMA declarations",
    "Supplier screening: OFAC SDN list, SAM.gov registration, USAspending awards, openFDA recalls",
    "Supplier discovery: Apify Google Places runs (leads only, never auto-trusted)",
    "Suppliers, quotes and quote changes: submitted by real supplier accounts (USER_SUBMITTED)",
    "Email: RFQs and POs sent from procurement@reliefmesh.us (DKIM/SPF/DMARC pass), plus each organization's own Gmail, Calendar, Drive and Slack",
    "Plans, approvals, purchase orders and the audit chain: stored in MongoDB Atlas",
  ] },
  { title: "What is sandbox?", items: [
    "CRS identity verification of supplier signers: CRS sandbox with CRS test identities only (SANDBOX)",
    "x402 evidence payments: test USDC on Solana devnet (DEVNET TEST PAYMENT); no real money, no supplier is paid",
  ] },
  { title: "What is hypothetical?", items: [
    "Every Continuity Engine result: N-1 supplier-loss scenarios, price / delay / capacity breakpoints and the resilient alternative (HYPOTHETICAL STRESS TEST)",
    "These never change a quote, plan, approval or order, and are marked STALE the moment a real input changes",
  ] },
  { title: "What uses AI?", items: [
    "Quote drafting: Gemini turns a pasted supplier quote into a draft the supplier reviews; every value is cited from the text",
    "The Fetch.ai agent in ASI:One: explains stored results in plain language and starts allowed actions",
  ] },
  { title: "What does NOT use AI?", items: [
    "Policy eligibility (deterministic rules over cited evidence)",
    "The optimizer and every continuity number (MILP re-solves on exact quote copies)",
    "Approval, purchase orders and payments (humans only; the agent can never approve, order or pay)",
  ] },
];

type Step = { label: string; done: boolean; detail: string; provenance?: string };

function MissionLoop({ missionId, token }: { missionId: string; token: string }) {
  const data = useMissionData(missionId, token);
  const mission = data.mission.data;
  const plans = [...(data.plans.data ?? [])].sort((a, b) => a.version - b.version);
  const first = plans[0];
  const latest = plans[plans.length - 1];
  const view = data.continuity.data;
  const quotes = data.quotes.data ?? [];
  const suppliers = data.suppliers.data ?? [];
  const approvals = data.approvals.data ?? [];
  const orders = data.orders.data ?? [];
  const disruptions = data.disruptions.data ?? [];
  const reality = view?.reality_check ?? [];
  const analysis = view?.analysis;
  const event = mission?.emergency_event;
  const revoked = approvals.filter((row) => row.status === "invalidated").length;
  const steps: Step[] = [
    { label: "Live disaster", done: Boolean(event), detail: event ? event.title : "No disaster event linked to this mission", provenance: event?.provenance ?? undefined },
    { label: "Supplier quote", done: quotes.length > 0, detail: `${quotes.length} quote${quotes.length === 1 ? "" : "s"} submitted by supplier accounts`, provenance: quotes.length ? "USER_SUBMITTED" : undefined },
    { label: "Evidence", done: suppliers.length > 0, detail: suppliers.length ? `${suppliers.length} supplier${suppliers.length === 1 ? "" : "s"} screened by deterministic policy` : "No suppliers screened yet" },
    { label: "Cheapest plan (V1)", done: Boolean(first), detail: first ? `Plan v${first.version} · ${first.status} · ${money(first.total_cost)}` : "Not optimized yet" },
    { label: "Continuity analysis", done: view?.state === "COMPLETE" || view?.state === "STALE",
      detail: analysis ? `N-1 ${analysis.metrics.n1_survivability.survives}/${analysis.metrics.n1_survivability.tested} for plan v${analysis.plan_version} · ${continuityWords[view?.state ?? "NOT_READY"]}` : continuityWords[view?.state ?? "NOT_READY"], provenance: analysis ? "HYPOTHETICAL" : undefined },
    { label: "Stress test + resilient alternative", done: Boolean(analysis),
      detail: analysis ? `${analysis.metrics.critical_supplier ? `Single point of failure: ${analysis.metrics.critical_supplier.supplier}` : "No single point of failure"} · ${analysis.resilient_alternative.status === "AVAILABLE" ? `resilient alternative ${money(analysis.resilient_alternative.total_cost)} (+${money(analysis.resilient_alternative.added_cost)})` : "no feasible resilient alternative"}` : "Runs automatically for every feasible plan", provenance: analysis ? "HYPOTHETICAL" : undefined },
    { label: "Actual disruption", done: disruptions.length > 0 || reality.length > 0,
      detail: reality.length ? `${reality.length} real change${reality.length === 1 ? "" : "s"} compared with the earlier stress test` : disruptions.length ? `${disruptions.length} real supplier change${disruptions.length === 1 ? "" : "s"}` : "No real supplier change yet", provenance: reality.length || disruptions.length ? "USER_SUBMITTED" : undefined },
    { label: "Plan V2", done: Boolean(latest && first && latest.version > first.version),
      detail: latest && first && latest.version > first.version ? `Plan v${latest.version} · ${latest.status} · ${money(latest.total_cost)} (V1 ${first.status})` : "Only one plan version so far" },
    { label: "Approval", done: approvals.some((row) => row.status === "active" || row.status === "consumed"),
      detail: approvals.length ? `${approvals.length} approval${approvals.length === 1 ? "" : "s"}${revoked ? ` · ${revoked} revoked when its plan went stale` : ""}` : "Awaiting an independent approver" },
    { label: "Purchase order", done: orders.length > 0, detail: orders.length ? orders.map((row) => `${row.po_number} ${row.status}`).join(" · ") : "No purchase order yet" },
    { label: "Audit", done: Boolean(data.verification.data?.valid),
      detail: data.verification.data ? `${data.verification.data.length} event${data.verification.data.length === 1 ? "" : "s"} · hash chain ${data.verification.data.valid ? "verifies (tamper-evident)" : `BROKEN: ${data.verification.data.reason}`}` : "Loading" },
  ];
  return (
    <section aria-label="The loop on this mission" className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="text-base font-semibold">{mission?.name ?? "Mission"}: the loop, step by step</h2>
        <Link className="text-sm underline" href={`/missions/${missionId}`}>Open the mission</Link>
      </div>
      <ol className="divide-y border-y">
        {steps.map((step, index) => (
          <li key={step.label} className="grid gap-x-4 py-2.5 sm:grid-cols-[2rem_14rem_minmax(0,1fr)_auto]">
            <span className="tabular text-sm text-muted-foreground">{index + 1}</span>
            <span className="text-sm font-medium">{step.label}</span>
            <span className="text-sm text-muted-foreground">{step.detail}</span>
            <span className="flex items-center gap-2">
              {step.provenance && <Provenance value={step.provenance} />}
              <StatusText tone={step.done ? "ok" : "neutral"}>{step.done ? "Done" : "Not yet"}</StatusText>
            </span>
          </li>
        ))}
      </ol>
      <p className="text-xs text-tertiary">Every row above is read from this mission&apos;s stored records. Nothing on this page is pre-filled or simulated.</p>
    </section>
  );
}

export default function JudgePage() {
  const session = useSession();
  const token = session?.token;
  const { current } = useOrganizations(token);
  const orgId = current?.id;
  const missions = useQuery({
    queryKey: ["judge-missions", orgId], enabled: Boolean(token && orgId),
    queryFn: () => api<Mission[]>(`/v1/missions?organization_id=${orgId}`, { token }),
  });
  const [picked, setPicked] = useState<string | null>(null);
  const missionId = picked ?? missions.data?.[0]?.id ?? null;

  return (
    <Page className="space-y-8">
      <PageHeader title="Judge guide" meta="What ReliefMesh does, what is real, and where to see it." />
      <section aria-label="Why this matters" className="space-y-2">
        <h2 className="text-base font-semibold">Why this matters</h2>
        <p className="max-w-3xl text-sm">{THESIS}</p>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Live disaster → supplier quote → Plan V1 → continuity analysis → resilient alternative → real supplier change → V1 stale →
          approval revoked → Plan V2 → fresh approval → PO.
        </p>
      </section>

      {token ? (
        <section className="space-y-3">
          {missions.data && missions.data.length > 1 && (
            <label className="flex max-w-full items-center gap-3 text-sm">
              Mission
              <select className="h-9 min-w-0 flex-1 rounded-md border bg-background px-3 text-sm sm:flex-none" value={missionId ?? ""} onChange={(event) => setPicked(event.target.value)}>
                {missions.data.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
              </select>
            </label>
          )}
          {missionId ? <MissionLoop missionId={missionId} token={token} /> : (
            <p className="text-sm text-muted-foreground">
              {missions.isLoading ? "Loading missions…" : <>No missions in this organization yet. <Link className="underline" href="/dashboard">Create one from a live disaster</Link> to walk the loop.</>}
            </p>
          )}
        </section>
      ) : (
        <section className="space-y-2">
          <h2 className="text-base font-semibold">Walk the loop on a real mission</h2>
          <p className="max-w-3xl text-sm text-muted-foreground">
            Nothing here is pre-seeded. <Link className="underline" href="/sign-up">Create a coordinator account</Link>, start a mission from a
            live disaster, and invite suppliers by email; this page then checks each step against that mission&apos;s stored records.
            The <Link className="underline" href="/status">status page</Link> shows every integration&apos;s live check right now.
          </p>
        </section>
      )}

      <section aria-label="Data truth" className="grid gap-x-10 gap-y-6 md:grid-cols-2">
        {TRUTH.map((block) => (
          <div key={block.title}>
            <h2 className="text-base font-semibold">{block.title}</h2>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
              {block.items.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
        ))}
      </section>
    </Page>
  );
}
