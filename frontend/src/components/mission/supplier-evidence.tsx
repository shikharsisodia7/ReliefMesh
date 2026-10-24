"use client";

import { ExternalLink, RefreshCw, ShieldAlert, ShieldCheck, X } from "lucide-react";
import { useState } from "react";

import { PolicyBadge, ProvenanceBadge, ago, money, when } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import type { Evidence, Quote, SupplierRow } from "@/lib/types";

type Run = (operation: () => Promise<void>) => Promise<void>;

const EVIDENCE_ORDER = [
  ["OFAC_SCREENING", "OFAC"],
  ["SAM_REGISTRATION", "SAM.gov"],
  ["FDA_RECALLS", "openFDA"],
  ["FEDERAL_AWARDS", "USAspending"],
  ["CRS_VERIFICATION", "CRS"],
  ["PAID_DOSSIER", "x402 dossier"],
] as const;
const CLEARABLE = new Set(["SANCTIONS_POTENTIAL_MATCH", "SANCTIONS_EXACT_MATCH", "PRODUCT_RECALL_MATCH", "CRS_VERIFICATION"]);

function evidenceTone(record?: Evidence) {
  if (!record) return "border-dashed border-border text-tertiary";
  if (["NO_MATCH", "MATCH", "PASS", "FOUND", "NOT_FOUND"].includes(record.status)) return "border-ok/30 text-ok";
  if (["POTENTIAL_MATCH", "EXACT_MATCH", "FAIL", "INACTIVE"].includes(record.status)) return "border-telemetry/50 text-telemetry";
  return "border-border text-muted-foreground";
}

function EvidenceDrawer({ record, history, onClose }: { record: Evidence; history: Evidence[]; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50" role="dialog" aria-label="Evidence detail" onClick={onClose}>
      <aside className="h-full w-full max-w-xl overflow-y-auto border-l bg-card p-5" onClick={(event) => event.stopPropagation()}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="font-mono text-xs text-muted-foreground">{record.type} · {record.provider}</p>
            <h3 className="mt-1 text-lg font-semibold">{record.subject_name}</h3>
          </div>
          <Button size="icon-sm" variant="ghost" onClick={onClose} aria-label="Close evidence"><X /></Button>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2"><span className="rounded border px-1.5 py-0.5 font-mono text-xs font-semibold">{record.status}</span><ProvenanceBadge value={record.provenance} />{record.confidence != null && <span className="font-mono text-xs text-muted-foreground">confidence {record.confidence}</span>}</div>
        <p className="mt-3 text-sm">{record.summary}</p>
        {record.adapter_error && <p className="mt-2 rounded border border-telemetry/40 bg-telemetry/10 p-2 text-xs text-telemetry">{record.adapter_error}</p>}
        <dl className="mt-4 grid grid-cols-[120px_1fr] gap-y-1 text-xs">
          <dt className="text-muted-foreground">Retrieved</dt><dd className="font-mono">{record.retrieved_at ?? "—"}</dd>
          <dt className="text-muted-foreground">Expires</dt><dd className="font-mono">{record.expires_at ?? "—"}</dd>
          <dt className="text-muted-foreground">Evidence id</dt><dd className="font-mono">{record.id}</dd>
          <dt className="text-muted-foreground">Source</dt><dd>{record.source_url ? <a href={record.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 break-all text-live hover:underline">{record.source_url}<ExternalLink className="size-3 shrink-0" /></a> : "—"}</dd>
        </dl>
        <h4 className="mt-5 text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Raw provider reference</h4>
        <pre className="mt-1 max-h-80 overflow-auto rounded bg-background p-3 font-mono text-[11px] leading-relaxed text-muted-foreground">{JSON.stringify(record.raw_reference, null, 2).slice(0, 6000)}</pre>
        <h4 className="mt-5 text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">History</h4>
        <ul className="mt-1 space-y-1 text-xs">
          {history.filter((row) => row.type === record.type).map((row) => <li key={row.id} className="flex justify-between gap-2 font-mono"><span>{row.status}</span><ProvenanceBadge value={row.provenance} /><span className="text-tertiary">{when(row.created_at)}</span></li>)}
        </ul>
      </aside>
    </div>
  );
}

function ReviewForm({ label, onSubmit }: { label: string; onSubmit: (reason: string) => Promise<void> }) {
  const [reason, setReason] = useState("");
  return (
    <form className="mt-1 flex gap-1" onSubmit={(event) => { event.preventDefault(); void onSubmit(reason).then(() => setReason("")); }}>
      <Input aria-label={`${label} reason`} className="h-7 text-xs" required minLength={3} placeholder="Reviewer reason (audited)" value={reason} onChange={(event) => setReason(event.target.value)} />
      <Button size="sm" variant="outline" type="submit">{label}</Button>
    </form>
  );
}

export function SupplierEvidence({ missionId, token, rows, quotes, run, canReview, checking }: {
  missionId: string; token: string; rows: SupplierRow[]; quotes: Quote[]; run: Run; canReview: boolean; checking: boolean;
}) {
  const [drawer, setDrawer] = useState<{ record: Evidence; history: Evidence[] } | null>(null);
  const quoteBySupplier = new Map(quotes.map((quote) => [quote.supplier_id, quote]));
  const review = (supplierId: string, body: Record<string, unknown>) => run(async () => { await api(`/v1/missions/${missionId}/suppliers/${supplierId}/review`, { method: "POST", token, body: JSON.stringify(body) }); });
  return (
    <section aria-label="Supplier evidence and policy" className="rounded-xl border bg-card p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-muted-foreground">Evidence & deterministic policy</h2>
          <p className="text-xs text-tertiary">Only PASS / WARN quotes reach the optimizer. Missing or unavailable screening is NEEDS REVIEW, never a pass. No language model makes these calls.</p>
        </div>
        <Button size="sm" variant="secondary" disabled={checking || rows.length === 0} onClick={() => void run(async () => { await api(`/v1/missions/${missionId}/evidence/refresh`, { method: "POST", token }); })}><RefreshCw className={checking ? "size-3.5 animate-spin" : "size-3.5"} />{checking ? "Checks running…" : "Run evidence checks"}</Button>
      </div>
      {rows.length === 0 ? <p className="text-sm text-muted-foreground">No supplier has submitted a quote yet.</p> : (
        <div className="grid gap-3 xl:grid-cols-2">
          {rows.map((row) => {
            const quote = quoteBySupplier.get(row.supplier.id);
            const open = row.policy.decisions.filter((decision) => decision.status === "NEEDS_REVIEW" || decision.status === "BLOCK");
            const quoteIssues = row.quotes.flatMap((entry) => entry.policy.decisions.filter((decision) => decision.status !== "PASS"));
            const blocked = row.reviews.find((entry) => entry.action === "block" || entry.action === "unblock")?.action === "block";
            return (
              <article key={row.supplier.id} className={`rounded-lg border p-3 ${row.policy.status === "BLOCK" ? "border-critical/50" : row.policy.status === "NEEDS_REVIEW" ? "border-telemetry/50" : ""}`} data-testid={`supplier-${row.supplier.legal_name ?? row.supplier.email}`}>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-1.5">
                      {row.policy.status === "PASS" || row.policy.status === "WARN" ? <ShieldCheck className="size-4 text-ok" /> : <ShieldAlert className="size-4 text-telemetry" />}
                      <h3 className="truncate font-semibold">{row.supplier.legal_name ?? "Legal name not provided"}</h3>
                      {row.supplier.is_demo ? <ProvenanceBadge value="TEST" /> : <ProvenanceBadge value="USER_SUBMITTED" />}
                    </div>
                    <p className="truncate text-xs text-muted-foreground">{row.supplier.email}</p>
                  </div>
                  <PolicyBadge value={row.policy.status} />
                </div>
                {quote && (
                  <p className="mt-2 font-mono text-xs">
                    <span className={quote.status === "submitted" ? "" : "text-critical line-through"}>{quote.lines.map((line) => `${line.available_quantity} ${line.item} @ ${money(line.unit_price)}`).join("; ")}</span>
                    <span className="text-muted-foreground"> · ship {money(quote.shipping_cost)} · ETA {when(quote.lines[0]?.delivery_date)} · v{quote.version}</span>
                    {quote.status !== "submitted" && <span className="ml-1 uppercase text-critical">{quote.status}</span>}
                    <ProvenanceBadge className="ml-1.5" value={quote.provenance} />
                  </p>
                )}
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {EVIDENCE_ORDER.map(([type, label]) => {
                    const record = row.latest_evidence[type];
                    if (!record && (type === "CRS_VERIFICATION" || type === "PAID_DOSSIER")) return null;
                    return (
                      <button key={type} type="button" disabled={!record} onClick={() => record && setDrawer({ record, history: row.evidence_history })} className={`rounded border px-1.5 py-0.5 text-left font-mono text-[10px] ${evidenceTone(record)} ${record ? "hover:bg-accent" : ""}`} title={record?.summary ?? "not checked"}>
                        <span className="font-semibold">{label}</span> {record ? record.status : "NOT CHECKED"} {record && <span className="text-tertiary">· {record.provenance === "LIVE" ? ago(record.retrieved_at) : record.provenance}</span>}
                      </button>
                    );
                  })}
                </div>
                {(open.length > 0 || quoteIssues.length > 0) && (
                  <ul className="mt-2 space-y-1.5">
                    {[...open, ...quoteIssues.filter((decision) => decision.status !== "WARN")].map((decision) => (
                      <li key={`${decision.rule_id}-${decision.subject_id}`} className="text-xs">
                        <span className="flex items-start gap-1.5"><PolicyBadge value={decision.status} /><span><span className="font-mono text-[10px] text-muted-foreground">{decision.rule_id}</span> {decision.reason}</span></span>
                        {canReview && CLEARABLE.has(decision.rule_id) && decision.status !== "PASS" && <ReviewForm label="Clear finding" onSubmit={(reason) => review(row.supplier.id, { action: "clear", rule_id: decision.rule_id, reason })} />}
                      </li>
                    ))}
                  </ul>
                )}
                <details className="mt-2 text-xs">
                  <summary className="cursor-pointer text-muted-foreground">All policy decisions ({row.policy.decisions.length})</summary>
                  <ul className="mt-1 space-y-1">{row.policy.decisions.map((decision) => <li key={decision.rule_id} className="flex gap-1.5"><PolicyBadge value={decision.status} /><span><span className="font-mono text-[10px] text-muted-foreground">{decision.rule_id}</span> {decision.reason}</span></li>)}</ul>
                  {row.reviews.length > 0 && <ul className="mt-2 space-y-0.5 border-t pt-1">{row.reviews.map((entry) => <li key={entry.id} className="text-tertiary">{when(entry.created_at)} · {entry.action}{entry.rule_id ? ` ${entry.rule_id}` : ""}: {entry.reason}</li>)}</ul>}
                </details>
                {canReview && row.supplier.legal_name && !row.latest_evidence.PAID_DOSSIER && <Button size="xs" variant="outline" className="mt-2 border-violet-400/40 text-violet-300" onClick={() => void run(async () => { await api(`/v1/missions/${missionId}/suppliers/${row.supplier.id}/premium-dossier`, { method: "POST", token }); })}>Buy signed dossier · 0.01 devnet USDC (x402)</Button>}
                {canReview && (blocked
                  ? <ReviewForm label="Unblock" onSubmit={(reason) => review(row.supplier.id, { action: "unblock", reason })} />
                  : <details className="mt-1 text-xs"><summary className="cursor-pointer text-critical/80">Block supplier</summary><ReviewForm label="Block" onSubmit={(reason) => review(row.supplier.id, { action: "block", reason })} /></details>)}
              </article>
            );
          })}
        </div>
      )}
      {drawer && <EvidenceDrawer record={drawer.record} history={drawer.history} onClose={() => setDrawer(null)} />}
    </section>
  );
}
