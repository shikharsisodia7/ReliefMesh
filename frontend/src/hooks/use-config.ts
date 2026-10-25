"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

export type AppConfig = { app_env: string; demo_mode: boolean; email: "configured" | "not_configured"; quote_assistant: boolean; approval_ttl_minutes?: number };

// Deployment capabilities. Demo tooling renders only when the API itself says it is a demo deployment.
export function useAppConfig() {
  const config = useQuery({ queryKey: ["app-config"], staleTime: 5 * 60_000, queryFn: () => api<AppConfig>("/v1/config") });
  // The API doesn't send the approval window yet; 240 minutes is the backend's default (approval_ttl_minutes).
  return { ...config, demoMode: config.data?.demo_mode === true, approvalTtlMinutes: config.data?.approval_ttl_minutes ?? 240 };
}
