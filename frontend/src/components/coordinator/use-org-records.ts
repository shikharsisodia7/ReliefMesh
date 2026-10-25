"use client";

import { useQueries, useQuery } from "@tanstack/react-query";

import { useOrganizations } from "@/hooks/use-organizations";
import { api } from "@/lib/api";
import type { Mission } from "@/lib/types";

// The current organization's missions plus one per-mission record type (e.g. "suppliers", "quotes", "plans").
// The API has no cross-mission endpoints yet, so these pages gather the organization's missions one by one.
export function useOrgMissions(token?: string) {
  const { organizations, current } = useOrganizations(token);
  const missions = useQuery({ queryKey: ["missions", current?.id ?? null], enabled: Boolean(token && current), queryFn: () => api<Mission[]>(`/v1/missions?organization_id=${current!.id}`, { token }) });
  return { organizations, current, missions };
}

export function usePerMission<T>(token: string | undefined, missions: Mission[] | undefined, resource: string) {
  const results = useQueries({
    queries: (missions ?? []).map((mission) => ({
      queryKey: [resource, mission.id],
      enabled: Boolean(token),
      queryFn: () => api<T[]>(`/v1/missions/${mission.id}/${resource}`, { token }),
    })),
  });
  return {
    // [mission, rows] pairs, only for missions whose rows have loaded.
    rows: (missions ?? []).flatMap((mission, index) => (results[index]?.data ? [[mission, results[index].data] as [Mission, T[]]] : [])),
    loading: results.some((result) => result.isLoading),
    error: results.find((result) => result.isError)?.error ?? null,
  };
}
