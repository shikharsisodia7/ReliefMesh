"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { api } from "@/lib/api";
import type { Mission, Plan, PurchaseOrder, Quote } from "@/lib/types";
import type { Invitation } from "@/components/mission/use-mission-data";

type State = { sentence: string; detail?: string; action: string; tab: string };

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

// Counts orders by the stage people care about on the dashboard: "1 PO in fulfillment · 1 draft", "2 draft POs".
function orderSummary(orders: PurchaseOrder[]) {
  const count = (statuses: string[]) => orders.filter((order) => statuses.includes(order.status)).length;
  const parts: [number, string][] = [
    [count(["supplier_accepted", "in_fulfillment"]), "in fulfillment"],
    [count(["sent"]), "awaiting the supplier"],
    [count(["completed"]), "delivered"],
    [count(["draft"]), "draft"],
  ];
  return parts.filter(([n]) => n > 0).map(([n, words], index) => {
    if (index > 0) return `${n} ${words}`;
    return words === "draft" ? `${n} draft ${n === 1 ? "PO" : "POs"}` : `${plural(n, "PO")} ${words}`;
  }).join(" · ");
}

// One state sentence and one next action, from the same records the mission workspace shows.
export function missionState(mission: Mission, plans: Plan[], orders: PurchaseOrder[], quotes: Quote[], invitations: Invitation[]): State {
  if (mission.status !== "open") return { sentence: mission.status.charAt(0).toUpperCase() + mission.status.slice(1), action: "View mission", tab: "context" };
  const [plan] = plans;
  if (plan?.status === "approved") {
    const drafts = orders.filter((order) => order.status === "draft").length;
    if (orders.length === 0) return { sentence: `Plan v${plan.version} approved`, detail: "No purchase orders yet", action: "Generate POs", tab: "plan" };
    return { sentence: `Plan v${plan.version} approved`, detail: orderSummary(orders), action: drafts > 0 ? "Review draft PO" : "View orders", tab: "orders" };
  }
  if (plan?.status === "feasible") return { sentence: "Needs approval", detail: `Plan v${plan.version}`, action: "Review plan", tab: "plan" };
  if (plan?.status === "stale") return { sentence: "Replanning", detail: `Plan v${plan.version} is stale`, action: "Review plan", tab: "plan" };
  if (plan?.status === "infeasible") return { sentence: "No feasible plan", detail: `Plan v${plan.version}`, action: "Review plan", tab: "plan" };
  const submitted = quotes.filter((quote) => quote.status === "submitted");
  const responded = new Set(submitted.map((quote) => quote.supplier_id)).size;
  if (invitations.length === 0 && responded === 0) return { sentence: "No suppliers invited yet", action: "Invite suppliers", tab: "evidence" };
  const invited = Math.max(invitations.length, responded);
  return { sentence: "Awaiting quotes", detail: `${responded} of ${plural(invited, "supplier")} responded`, action: "Review responses", tab: "evidence" };
}

export function MissionRow({ mission, token }: { mission: Mission; token: string }) {
  const get = <T,>(path: string) => () => api<T>(path, { token });
  const plans = useQuery({ queryKey: ["plans", mission.id], queryFn: get<Plan[]>(`/v1/missions/${mission.id}/plans`) });
  const quotes = useQuery({ queryKey: ["quotes", mission.id], queryFn: get<Quote[]>(`/v1/missions/${mission.id}/quotes`) });
  const invitations = useQuery({ queryKey: ["invitations", mission.id], queryFn: get<Invitation[]>(`/v1/missions/${mission.id}/invitations`) });
  const orders = useQuery({ queryKey: ["orders", mission.id], queryFn: get<PurchaseOrder[]>(`/v1/purchase-orders?organization_id=${mission.organization_id}&mission_id=${mission.id}`) });
  const failed = [plans, quotes, invitations, orders].find((query) => query.isError);
  const ready = plans.data && quotes.data && invitations.data && orders.data;
  const state = ready ? missionState(mission, plans.data!, orders.data!, quotes.data!, invitations.data!) : null;
  const href = `/missions/${mission.id}${state ? `?tab=${state.tab}` : ""}`;
  const source = [mission.emergency_event ? mission.emergency_event.title : "No linked event", mission.created_via === "agent" ? "Created by Fetch.ai agent" : null].filter(Boolean).join(" · ");
  return (
    <li data-testid={`mission-${mission.name}`} className="grid gap-x-6 gap-y-3 border-b py-6 sm:grid-cols-[1fr_auto] sm:items-center">
      <div className="min-w-0">
        <h3 className="text-2xl font-semibold tracking-tight"><Link href={`/missions/${mission.id}`} className="hover:underline">{mission.name}</Link></h3>
        <p className="mt-1 text-base text-muted-foreground">{mission.delivery_location} · {mission.requirements.map((row) => `${row.quantity.toLocaleString("en-US")} ${row.item}`).join(", ")}</p>
        <div className="mt-3 text-sm">
          {failed ? <p className="text-critical">{failed.error?.message ?? "Could not load this mission's status."}</p>
            : state ? <p>{state.sentence}{state.detail && <span className="text-muted-foreground"> · {state.detail}</span>}</p>
              : <p className="h-5 w-56 animate-pulse rounded bg-muted motion-reduce:animate-none" aria-label="Loading status" />}
          <p className="mt-0.5 text-muted-foreground">{source}</p>
        </div>
      </div>
      {state && <Link href={href} className="text-sm font-medium whitespace-nowrap hover:underline">{state.action} →</Link>}
    </li>
  );
}
