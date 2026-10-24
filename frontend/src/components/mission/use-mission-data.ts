"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  Approval, AuditEvent, AuditVerification, Disruption, Job, Lead, Mission, MissionContext, Notification, Plan,
  PurchaseOrder, Quote, SupplierRow,
} from "@/lib/types";

export type Invitation = { id: string; supplier_email: string; status: string; delivery_status?: string; lead_id?: string | null; is_demo?: boolean; created_at: string };

export function useMissionData(missionId: string, token: string | undefined) {
  const client = useQueryClient();
  const enabled = Boolean(token);
  const get = <T,>(path: string) => () => api<T>(path, { token });
  const jobs = useQuery({ queryKey: ["jobs", missionId], enabled, queryFn: get<Job[]>(`/v1/missions/${missionId}/jobs`), refetchInterval: 1500 });
  const busy = (jobs.data ?? []).some((job) => job.status === "queued" || job.status === "running");
  // Poll quickly while background replans/evidence checks run; idle missions refresh slowly.
  const fast = busy ? 1500 : 4000;
  const slow = busy ? 2500 : 8000;
  const mission = useQuery({ queryKey: ["mission", missionId], enabled, queryFn: get<Mission>(`/v1/missions/${missionId}`) });
  const context = useQuery({ queryKey: ["context", missionId], enabled, queryFn: get<MissionContext>(`/v1/missions/${missionId}/context`), staleTime: 300_000 });
  const quotes = useQuery({ queryKey: ["quotes", missionId], enabled, refetchInterval: fast, queryFn: get<Quote[]>(`/v1/missions/${missionId}/quotes`) });
  const plans = useQuery({ queryKey: ["plans", missionId], enabled, refetchInterval: fast, queryFn: get<Plan[]>(`/v1/missions/${missionId}/plans`) });
  const approvals = useQuery({ queryKey: ["approvals", missionId], enabled, refetchInterval: fast, queryFn: get<Approval[]>(`/v1/missions/${missionId}/approvals`) });
  const suppliers = useQuery({ queryKey: ["suppliers", missionId], enabled, refetchInterval: slow, queryFn: get<SupplierRow[]>(`/v1/missions/${missionId}/suppliers`) });
  const notifications = useQuery({ queryKey: ["notifications", missionId], enabled, refetchInterval: fast, queryFn: get<Notification[]>(`/v1/missions/${missionId}/notifications`) });
  const audit = useQuery({ queryKey: ["audit", missionId], enabled, refetchInterval: slow, queryFn: get<AuditEvent[]>(`/v1/missions/${missionId}/audit`) });
  const verification = useQuery({ queryKey: ["audit-verify", missionId], enabled, refetchInterval: slow, queryFn: get<AuditVerification>(`/v1/missions/${missionId}/audit/verify`) });
  const leads = useQuery({ queryKey: ["leads", missionId], enabled, refetchInterval: slow, queryFn: get<Lead[]>(`/v1/missions/${missionId}/leads`) });
  const invitations = useQuery({ queryKey: ["invitations", missionId], enabled, refetchInterval: slow, queryFn: get<Invitation[]>(`/v1/missions/${missionId}/invitations`) });
  const disruptions = useQuery({ queryKey: ["disruptions", missionId], enabled, refetchInterval: fast, queryFn: get<Disruption[]>(`/v1/missions/${missionId}/disruptions`) });
  const orders = useQuery({
    queryKey: ["orders", missionId], enabled: enabled && Boolean(mission.data), refetchInterval: slow,
    queryFn: get<PurchaseOrder[]>(`/v1/purchase-orders?organization_id=${mission.data?.organization_id}&mission_id=${missionId}`),
  });
  const refresh = () => client.invalidateQueries({ predicate: (query) => Array.isArray(query.queryKey) && query.queryKey[1] === missionId });
  return { mission, context, quotes, plans, approvals, suppliers, notifications, audit, verification, leads, invitations, disruptions, orders, jobs, busy, refresh };
}
