"use client";

import { Copy } from "lucide-react";
import { useState } from "react";

import { Provenance, StatusText, money, signedAmount, when } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { AuditEvent, AuditVerification, Job, Notification, Payment } from "@/lib/types";

const shortHash = (hash?: string | null) => (hash ? `${hash.slice(0, 4)}…${hash.slice(-4)}` : "—");
// Plain words for the actions the API records; anything new falls back to "purchase_order.created" → "Purchase order created".
const EVENT_WORDS: Record<string, string> = {
  "approval.invalidated": "Approval revoked", "continuity.computed": "Stress test computed", "continuity.stale": "Stress test out of date",
  "demo.seeded": "TEST suppliers seeded", "evidence.collected": "Evidence collected", "fulfillment.updated": "Fulfillment updated",
  "job.failed": "Background job failed", "mission.cancelled": "Mission cancelled", "mission.created": "Mission created",
  "mission.deadline_changed": "Deadline changed", "plan.approved": "Plan approved", "plan.computed": "Plan computed", "plan.stale": "Plan went stale",
  "purchase_order.created": "Purchase order drafted", "purchase_order.sent": "Purchase order sent", "purchase_order.supplier_response": "Supplier responded to PO",
  "purchase_order.voided": "Purchase order voided", "quote.draft_extracted": "Quote drafted from pasted text", "quote.submitted": "Quote submitted",
  "quote.updated": "Quote revised", "quote.withdrawn": "Quote withdrawn", "rfq.accepted": "RFQ accepted", "rfq.invited": "RFQ sent",
  "supplier_discovery.completed": "Supplier leads discovered", "supply_chain.disrupted": "Supply chain disrupted (demo)",
};
const eventWords = (action: string) => {
  if (EVENT_WORDS[action]) return EVENT_WORDS[action];
  const text = action.replace(/[._]/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
};
// Suppliers aren't organization members, so their actions would otherwise show a bare user id.
const SUPPLIER_ACTIONS = new Set(["rfq.accepted", "quote.submitted", "quote.updated", "quote.withdrawn", "quote.draft_extracted", "purchase_order.supplier_response", "fulfillment.updated"]);
const NETWORKS: Record<string, string> = { "solana-devnet": "Solana devnet · test USDC" };
const severityWord: Record<string, string> = { warning: "Warning", critical: "Critical" };

const ISO_TIME = String.raw`\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})`;

// Rewrites the raw money and times in known API messages; anything else passes through unchanged.
// "Plan v2 approved for $3466.00 (expires 2026-10-25T10:53Z)." → "Plan v2 approved for $3,466.00 · expires Oct 25, 3:53 AM"
export function readableMessage(message: string) {
  return message
    // Unformatted amounts like "$3466.00"; amounts that already have commas are left alone.
    .replace(/\$(\d+(?:\.\d+)?)(?![\d,]|\.\d)/g, (_, value: string) => money(value))
    // The replan delta arrives without a dollar sign, signed or not: "(+195.00 vs prior plan)".
    .replace(/\(([+-]?\d+(?:\.\d+)?) vs prior plan\)/, (_, delta: string) => `(${signedAmount(delta, true)} vs prior plan)`)
    .replace(new RegExp(String.raw` \(expires (${ISO_TIME})\)\.?$`), (_, at: string) => ` · expires ${when(at)}`)
    .replace(new RegExp(ISO_TIME, "g"), (at) => when(at));
}

function CopyHash({ hash, sequence }: { hash: string; sequence: number }) {
  const [copied, setCopied] = useState(false);
  const copy = () => void navigator.clipboard?.writeText(hash).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); });
  return (
    <span className="inline-flex items-center gap-1">
      <span className="font-mono text-xs" title={hash}>{shortHash(hash)}</span>
      <Button variant="text" size="icon-xs" aria-label={`Copy hash for event #${sequence}`} onClick={copy}><Copy /></Button>
      {copied && <span className="text-xs text-muted-foreground" role="status">Copied</span>}
    </span>
  );
}

// Audit tab: the SHA-256 hash chain, every recorded event, mission messages, and x402 evidence payments.
export function AuditTab({ audit, verification, jobs, notifications, payments, actorName }: {
  audit: AuditEvent[]; verification?: AuditVerification; jobs: Job[]; notifications: Notification[]; payments: Payment[]; actorName: (id: string | null) => string;
}) {
  const failed = jobs.filter((job) => job.status === "failed").slice(0, 2);
  const events = [...audit].reverse();
  const actor = (event: AuditEvent) => {
    const name = actorName(event.actor_id);
    return name.startsWith("User ") && SUPPLIER_ACTIONS.has(event.action) ? `Supplier · ${name.slice(5)}` : name;
  };
  return (
    <div className="space-y-12">
      <section aria-label="Audit trail">
        {verification && (verification.valid
          ? <p className="text-sm">Hash chain verified · {verification.length} events · head <span className="font-mono text-xs" title={verification.head_hash}>{shortHash(verification.head_hash)}</span></p>
          : <p role="alert" className="text-sm text-critical">Hash chain broken at event #{verification.broken_at}{verification.reason ? `: ${verification.reason}` : ""}</p>)}
        {failed.map((job) => <p key={job.id} className="mt-1 text-sm text-critical">{eventWords(job.type)} failed: {job.last_error}</p>)}
        <p className="mt-1 text-xs text-muted-foreground">Each event hashes its predecessor, so any edit breaks the chain. This is application audit chaining, not blockchain storage.</p>
        {events.length === 0 ? <p className="mt-6 text-sm text-muted-foreground">No events recorded yet.</p> : (
          <Table className="mt-4">
            <TableHeader><TableRow><TableHead className="w-12">#</TableHead><TableHead>Time</TableHead><TableHead>Event</TableHead><TableHead>Actor</TableHead><TableHead>Hash</TableHead></TableRow></TableHeader>
            <TableBody>
              {events.map((event) => (
                <TableRow key={event.id} className="h-9 [&>td]:py-2">
                  <TableCell className="tabular text-muted-foreground">{event.sequence}</TableCell>
                  <TableCell>{when(event.created_at)}</TableCell>
                  <TableCell className="whitespace-normal">{eventWords(event.action)}</TableCell>
                  <TableCell>{actor(event)}</TableCell>
                  <TableCell><CopyHash hash={event.event_hash} sequence={event.sequence} /></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </section>

      {notifications.length > 0 && (
        <section aria-label="Mission messages">
          <h3 className="text-base font-semibold">Messages</h3>
          <ul tabIndex={0} aria-label="Mission messages, scrollable" className="mt-2 max-h-96 overflow-y-auto">
            {notifications.map((notification) => (
              <li key={notification.id} className="grid gap-x-6 border-b py-2.5 text-sm sm:grid-cols-[140px_1fr]">
                <span className="text-muted-foreground">{when(notification.created_at)}</span>
                <span>{severityWord[notification.severity] && <StatusText value={notification.severity}>{severityWord[notification.severity]} · </StatusText>}{readableMessage(notification.message)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {payments.length > 0 && (
        <section aria-label="Machine payments">
          <h3 className="text-base font-semibold">Payments <span className="font-normal text-muted-foreground">· x402</span> <Provenance className="ml-1" value="SANDBOX" /></h3>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">HTTP 402 → signed USDC transfer → facilitator verification and settlement → evidence unlocked. Devnet test USDC only: no supplier is paid and procurement funds never move through x402.</p>
          <Table className="mt-3">
            <TableHeader><TableRow><TableHead>Supplier</TableHead><TableHead>Amount</TableHead><TableHead>Network</TableHead><TableHead>Transaction</TableHead><TableHead>Verified</TableHead></TableRow></TableHeader>
            <TableBody>
              {payments.map((payment) => (
                <TableRow key={payment.id}>
                  <TableCell>{payment.subject_name}</TableCell>
                  <TableCell className="tabular">{payment.amount_display}</TableCell>
                  <TableCell>{NETWORKS[payment.network_label] ?? payment.network_label}</TableCell>
                  <TableCell><a className="font-medium hover:underline" href={payment.explorer_url} target="_blank" rel="noreferrer"><span className="font-mono text-xs">{shortHash(payment.transaction)}</span> →</a></TableCell>
                  <TableCell>{payment.verified ? "Verified" : <StatusText tone="muted">{payment.status}</StatusText>}<span className="block text-xs text-muted-foreground">{when(payment.created_at)} · dossier <span className="font-mono">{payment.dossier_sha256.slice(0, 12)}</span></span></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </section>
      )}
    </div>
  );
}
