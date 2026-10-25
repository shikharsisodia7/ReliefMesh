"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSyncExternalStore } from "react";

import { api } from "@/lib/api";
import type { Organization } from "@/lib/types";

// The chosen organization is a per-browser convenience, shared by the avatar menu, dashboard, and settings.
const key = "reliefmesh.organization";
const changed = "reliefmesh-organization";
// Used when storage is blocked, so a selection still lasts until the page reloads.
let memory: string | null = null;

function readSelected() {
  try { return localStorage.getItem(key) ?? memory; } catch { return memory; }
}

function subscribe(onChange: () => void) {
  window.addEventListener("storage", onChange);
  window.addEventListener(changed, onChange);
  return () => { window.removeEventListener("storage", onChange); window.removeEventListener(changed, onChange); };
}

export function selectOrganization(id: string) {
  memory = id;
  try { localStorage.setItem(key, id); } catch { /* storage blocked: memory keeps it */ }
  window.dispatchEvent(new Event(changed));
}

export function useOrganizations(token?: string) {
  const organizations = useQuery({ queryKey: ["organizations", token], enabled: Boolean(token), queryFn: () => api<Organization[]>("/v1/organizations", { token: token! }) });
  const selected = useSyncExternalStore(subscribe, readSelected, () => null);
  // Fall back to the first organization when nothing (or a stale id) is stored.
  const current = organizations.data?.find((row) => row.id === selected) ?? organizations.data?.[0] ?? null;
  return { organizations, current, select: selectOrganization };
}

// Creates an organization and makes it the current one. Callers show any error.
export function useCreateOrganization(token?: string) {
  const queryClient = useQueryClient();
  return async (values: { name: string; demo: boolean }) => {
    const created = await api<Organization>("/v1/organizations", { method: "POST", body: JSON.stringify(values), token });
    await queryClient.invalidateQueries({ queryKey: ["organizations"] });
    selectOrganization(created.id);
  };
}
