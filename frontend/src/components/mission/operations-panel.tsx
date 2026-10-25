"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { DeliveryList } from "@/components/operations/delivery-list";
import { api } from "@/lib/api";
import type { OperationsDelivery } from "@/lib/types";

// Gmail / Slack / Calendar / Drive deliveries this mission's events produced, with their real provider outcome.
export function OperationsPanel({ missionId, organizationId, token, isAdmin }: { missionId: string; organizationId: string; token: string; isAdmin: boolean }) {
  const deliveries = useQuery({
    queryKey: ["mission-operations", missionId], refetchInterval: 5000,
    queryFn: () => api<OperationsDelivery[]>(`/v1/missions/${missionId}/operations`, { token }),
  });
  const all = deliveries.data ?? [];
  // Deliveries for channels the organization never connected are kept (they can be retried after connecting),
  // but collapsed into one line so they do not drown out real sends and failures.
  const notConnected = all.filter((row) => row.status === "NOT_CONFIGURED");
  const rows = all.filter((row) => row.status !== "NOT_CONFIGURED");
  const channels = [...new Set(notConnected.map((row) => row.channel))].map((channel) => ({ gmail: "Gmail", slack: "Slack", calendar: "Google Calendar", drive: "Google Drive" })[channel] ?? channel);
  const failed = rows.filter((row) => row.status === "FAILED").length;
  return (
    <section aria-label="External notifications" className="rounded-xl border bg-card p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-muted-foreground">External notifications</h2>
        <span className="text-xs text-muted-foreground">
          {rows.filter((row) => row.status === "SENT").length} sent{failed ? ` · ${failed} failed` : ""} · <Link className="underline" href={`/settings/integrations?org=${organizationId}`}>Gmail · Calendar · Slack · Drive settings</Link>
        </span>
      </div>
      {deliveries.isError ? <p className="mt-2 text-sm text-critical">{deliveries.error.message}</p>
        : <>
            {(rows.length > 0 || notConnected.length === 0) && <DeliveryList deliveries={rows} token={token} canRetry={isAdmin} onChanged={() => void deliveries.refetch()} />}
            {notConnected.length > 0 && (
              <details className="mt-2 rounded-md border border-dashed px-3 py-2 text-sm">
                <summary className="cursor-pointer text-muted-foreground">{notConnected.length} notification{notConnected.length === 1 ? "" : "s"} not sent: {channels.join(", ")} {channels.length === 1 ? "is" : "are"} not connected for this organization. <Link className="underline" href={`/settings/integrations?org=${organizationId}`}>Connect</Link>, then retry.</summary>
                <DeliveryList deliveries={notConnected} token={token} canRetry={isAdmin} onChanged={() => void deliveries.refetch()} />
              </details>
            )}
          </>}
    </section>
  );
}
