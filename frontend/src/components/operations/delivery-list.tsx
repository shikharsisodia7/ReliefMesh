"use client";

import { CalendarDays, ExternalLink, FolderArchive, Mail, MessageSquare } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { StatusText, when, type Tone } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { DeliveryStatus, OperationsDelivery } from "@/lib/types";

const icons = { gmail: Mail, slack: MessageSquare, calendar: CalendarDays, drive: FolderArchive } as const;
const tone: Record<DeliveryStatus, Tone> = {
  SENT: "neutral", TEST: "muted", DISABLED: "muted", SUPPRESSED: "muted", SKIPPED: "muted", NOT_CONFIGURED: "muted",
  PENDING: "neutral", SENDING: "neutral", RETRYING: "warn", FAILED: "critical",
};
const eventLabel: Record<string, string> = {
  mission_created: "Mission created", mission_updated: "Mission updated", mission_cancelled: "Mission cancelled",
  approval_required: "Approval required", plan_replanned: "Plan rebuilt", supplier_disrupted: "Supplier disruption",
  plan_approved: "Plan approved", purchase_order_sent: "PO issued", purchase_order_accepted: "PO accepted",
  fulfillment_updated: "Fulfillment", integration_test: "Connection test",
};

export function DeliveryList({ deliveries, token, canRetry, onChanged, showMission = false }: {
  deliveries: OperationsDelivery[]; token: string; canRetry: boolean; onChanged: () => void; showMission?: boolean;
}) {
  const [error, setError] = useState<string | null>(null);
  if (deliveries.length === 0) return <p className="mt-2 text-sm text-muted-foreground">No external deliveries yet. They appear here as procurement events happen.</p>;
  const retry = async (id: string) => {
    setError(null);
    try { await api(`/v1/integrations/deliveries/${id}/retry`, { method: "POST", token }); onChanged(); }
    catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Retry failed"); }
  };
  return (
    <div className="mt-2">
      {error && <p role="alert" className="mb-2 text-sm text-critical">{error}</p>}
      <ol className="max-h-[28rem] overflow-y-auto">
        {deliveries.map((row) => {
          const Icon = icons[row.channel];
          return (
            <li key={row.id} className="grid gap-x-3 gap-y-0.5 border-b py-3 text-sm sm:grid-cols-[22px_1fr_auto]">
              <Icon className="mt-0.5 size-4 text-muted-foreground" aria-label={row.channel} />
              <div className="min-w-0">
                <p className="truncate"><span className="font-medium">{eventLabel[row.event_type] ?? row.event_type}</span> · <span className="text-muted-foreground">{row.subject ?? row.summary}</span></p>
                <p className="truncate text-xs text-muted-foreground">
                  {row.channel} → {row.target}{row.operation ? ` (${row.operation})` : ""} · {when(row.created_at)} · attempt {row.attempts}/{row.max_attempts}
                  {row.provider_id ? ` · id ${row.provider_id.slice(0, 18)}` : ""}
                  {showMission && row.mission_id && <> · <Link className="underline" href={`/missions/${row.mission_id}`}>mission</Link></>}
                </p>
                {row.last_error && <p className="text-xs text-critical">{row.last_error}</p>}
              </div>
              <div className="flex items-center gap-2 sm:justify-end">
                <StatusText tone={tone[row.status]} value={row.status} className="text-xs tracking-wide">{row.status.replace("_", " ")}</StatusText>
                {row.provider_url && <a className="text-muted-foreground hover:text-foreground" href={row.provider_url} target="_blank" rel="noreferrer" aria-label="Open in provider"><ExternalLink className="size-3.5" /></a>}
                {canRetry && (row.status === "FAILED" || row.status === "NOT_CONFIGURED") && row.event_type !== "integration_test" && <Button size="sm" variant="text" onClick={() => void retry(row.id)}>Retry</Button>}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
