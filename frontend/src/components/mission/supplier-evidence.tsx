"use client";

import { ExternalLink } from "lucide-react";
import { useState, type ReactNode } from "react";

import { Dialog, Drawer } from "@/components/patterns/overlays";
import { PolicyText, Provenance, StatusText, amount, day, money, when } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import type { Decision, Evidence, Quote, SupplierRow } from "@/lib/types";
import { cn } from "@/lib/utils";

type Run = (operation: () => Promise<void>) => Promise<void>;

export const EVIDENCE_ORDER = [
  ["OFAC_SCREENING", "OFAC"],
  ["SAM_REGISTRATION", "SAM.gov"],
  ["FDA_RECALLS", "openFDA"],
  ["FEDERAL_AWARDS", "USAspending"],
  ["CRS_VERIFICATION", "CRS identity"],
  ["PAID_DOSSIER", "x402 dossier"],
] as const;
const CLEARABLE = new Set(["SANCTIONS_POTENTIAL_MATCH", "SANCTIONS_EXACT_MATCH", "PRODUCT_RECALL_MATCH", "CRS_VERIFICATION"]);

// Check results in plain words. Codes differ per check: SAM.gov "MATCH" means an active registration.
const RESULT_WORDS: Record<string, string> = {
  "OFAC_SCREENING:NO_MATCH": "No match", "OFAC_SCREENING:POTENTIAL_MATCH": "Potential match", "OFAC_SCREENING:EXACT_MATCH": "Exact match",
  "SAM_REGISTRATION:MATCH": "Active", "SAM_REGISTRATION:INACTIVE": "Inactive", "SAM_REGISTRATION:NO_MATCH": "No registration found",
  "FDA_RECALLS:NO_MATCH": "No recalls", "FDA_RECALLS:POTENTIAL_MATCH": "Potential recall match", "FDA_RECALLS:WEAK_MATCH": "Weak name overlap",
  "FEDERAL_AWARDS:FOUND": "Awards found", "FEDERAL_AWARDS:NOT_FOUND": "No awards",
};
// Results that need no attention. Anything else (including not configured or unavailable) keeps the row open.
const CLEAR = new Set(["OFAC_SCREENING:NO_MATCH", "SAM_REGISTRATION:MATCH", "FDA_RECALLS:NO_MATCH", "FEDERAL_AWARDS:FOUND", "FEDERAL_AWARDS:NOT_FOUND", "CRS_VERIFICATION:PASS", "CRS_VERIFICATION:VERIFIED"]);

const words = (code: string) => code.charAt(0).toUpperCase() + code.slice(1).toLowerCase().replace(/_/g, " ");
const SHARED_WORDS: Record<string, string> = { BLOCKED_EXTERNAL: "Not configured", UNAVAILABLE: "Unavailable" };
const resultWords = (record: Evidence) => RESULT_WORDS[`${record.type}:${record.status}`] ?? SHARED_WORDS[record.status] ?? words(record.status);
const isClear = (record: Evidence) => CLEAR.has(`${record.type}:${record.status}`) || (record.type === "PAID_DOSSIER" && !["UNAVAILABLE", "FAIL", "FAILED"].includes(record.status));
const checkLabel = (type: string) => EVIDENCE_ORDER.find(([key]) => key === type)?.[1] ?? type;
// "Not configured" and "unavailable" already say where the data came from.
const showsProvenance = (record: Evidence) => record.provenance !== "BLOCKED_EXTERNAL" && record.provenance !== "UNAVAILABLE";

type Review = { supplierId: string; supplier: string; action: "clear" | "block" | "unblock"; ruleId?: string; finding?: string };

const REVIEW_COPY = {
  clear: { title: "Clear finding", field: "Clear finding reason", submit: "Clear finding", note: "Clear a finding only after a documented human review. The reason is saved to the audit log, and the plan replans if eligibility changes." },
  block: { title: "Block supplier", field: "Block reason", submit: "Block supplier", note: "Blocked suppliers are excluded from every plan for this mission until unblocked. The plan replans without them." },
  unblock: { title: "Unblock supplier", field: "Unblock reason", submit: "Unblock supplier", note: "The supplier is evaluated by policy again, and the plan replans." },
};

function ReviewDialog({ review, onClose, onSubmit }: { review: Review | null; onClose: () => void; onSubmit: (review: Review, reason: string) => Promise<void> }) {
  const [reason, setReason] = useState("");
  const copy = REVIEW_COPY[review?.action ?? "clear"];
  return (
    <Dialog open={review !== null} onOpenChange={(open) => { if (!open) { onClose(); setReason(""); } }} title={copy.title} subtitle={review ? `${review.supplier}${review.finding ? ` · ${review.finding}` : ""}` : undefined}
      footer={<Button type="submit" form="review-form">{copy.submit}</Button>}>
      <form id="review-form" className="space-y-4" onSubmit={(event) => { event.preventDefault(); if (review) void onSubmit(review, reason).then(() => setReason("")); }}>
        <div><Label htmlFor="review-reason">{copy.field}</Label><Input id="review-reason" required minLength={3} className="mt-1.5" placeholder="Reviewer reason (audited)" value={reason} onChange={(event) => setReason(event.target.value)} /></div>
        <p className="text-muted-foreground">{copy.note}</p>
      </form>
    </Dialog>
  );
}

function rawExcerpt(raw: Record<string, unknown>) {
  return Object.entries(raw).filter(([, value]) => value !== null && ["string", "number", "boolean"].includes(typeof value)).slice(0, 8);
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return <><dt className="text-muted-foreground">{label}</dt><dd className="min-w-0 break-words">{children}</dd></>;
}

function EvidenceDrawer({ open, record, row, blocking, canReview, onClose, onReview, onDossier }: {
  open: boolean; record: Evidence; row: SupplierRow; blocking: Decision[]; canReview: boolean;
  onClose: () => void; onReview: (review: Review) => void; onDossier: () => void;
}) {
  const supplier = row.supplier.legal_name ?? row.supplier.email ?? "Supplier";
  const why = blocking.filter((decision) => decision.evidence_ids.includes(record.id));
  const excerpt = rawExcerpt(record.raw_reference ?? {});
  const history = row.evidence_history.filter((entry) => entry.type === record.type && entry.id !== record.id);
  return (
    <Drawer open={open} onOpenChange={(next) => { if (!next) onClose(); }} label="Evidence detail" closeLabel="Close evidence" title={`${checkLabel(record.type)} evidence`} subtitle="Evidence record · read-only">
      <p className="text-base">{supplier}</p>
      <p className="mt-1"><PolicyText value={row.policy.status} /></p>
      <dl className="mt-5 grid grid-cols-[110px_1fr] gap-x-4 gap-y-2.5 text-sm">
        <Fact label="Result">{resultWords(record)}{record.confidence != null && <span className="text-muted-foreground"> · score {record.confidence}</span>}</Fact>
        <Fact label="Provenance"><Provenance value={record.provenance} /></Fact>
        <Fact label="Retrieved">{when(record.retrieved_at)}</Fact>
        <Fact label="Source">{record.source_url ? <a href={record.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-medium hover:underline">{record.provider} source record<ExternalLink className="size-3.5 shrink-0" /></a> : "—"}</Fact>
      </dl>
      <p className="mt-4 text-sm text-muted-foreground">{record.summary}</p>
      {record.adapter_error && <p className="mt-2 text-sm text-muted-foreground">Adapter: {record.adapter_error}</p>}

      <section className="mt-6 border-t pt-5">
        <h3 className="text-sm font-semibold">Raw record excerpt</h3>
        <p className="text-xs text-muted-foreground">From the API&apos;s stored response</p>
        {excerpt.length > 0 && <dl className="mt-3 grid grid-cols-[140px_1fr] gap-x-3 gap-y-1.5 font-mono text-xs">{excerpt.map(([key, value]) => <Fact key={key} label={`${key}:`}>{String(value)}</Fact>)}</dl>}
        <details className="mt-3 text-xs">
          <summary className="cursor-pointer text-muted-foreground">Full record</summary>
          <pre className="mt-2 max-h-72 overflow-auto rounded-md bg-muted p-3 font-mono text-[11px] leading-relaxed text-muted-foreground">{JSON.stringify(record.raw_reference, null, 2).slice(0, 6000)}</pre>
        </details>
      </section>

      {why.length > 0 && (
        <section className="mt-6 border-t pt-5">
          <h3 className="text-sm font-semibold">Why allocation is blocked</h3>
          <ul className="mt-2 space-y-2 text-sm">{why.map((decision) => <li key={decision.rule_id}>{decision.reason}</li>)}</ul>
          <p className="mt-2 text-xs text-muted-foreground">Rules decide eligibility; price never overrides it. Clear the finding only after a documented human review.</p>
        </section>
      )}

      {history.length > 0 && (
        <section className="mt-6 border-t pt-5">
          <h3 className="text-sm font-semibold">Earlier results</h3>
          <ul className="mt-2 text-sm">{history.map((entry) => <li key={entry.id} className="flex justify-between gap-3 py-1"><span>{resultWords(entry)}</span><span className="text-muted-foreground">{when(entry.created_at)}</span></li>)}</ul>
        </section>
      )}

      {canReview && (
        <div className="mt-6 flex flex-wrap items-center gap-x-4 gap-y-2 border-t pt-5">
          {why.filter((decision) => CLEARABLE.has(decision.rule_id)).map((decision) => <Button key={decision.rule_id} variant="text" className="px-0" onClick={() => onReview({ supplierId: row.supplier.id, supplier, action: "clear", ruleId: decision.rule_id, finding: words(decision.rule_id) })}>Clear finding</Button>)}
          <Button variant="text" className="px-0" onClick={() => onReview({ supplierId: row.supplier.id, supplier, action: "block" })}>Block supplier</Button>
          {row.supplier.legal_name && !row.latest_evidence.PAID_DOSSIER && <Button variant="secondary" size="sm" onClick={onDossier}>Buy signed dossier · 0.01 devnet USDC (x402)</Button>}
        </div>
      )}
    </Drawer>
  );
}

function CheckLine({ record, onOpen }: { record: Evidence; onOpen: () => void }) {
  return (
    <button type="button" data-check={record.type} data-result={record.status} onClick={onOpen} className="block w-full py-0.5 text-left text-sm hover:underline">
      {/* Only real findings get weight; "not configured" and "unavailable" stay plain. */}
      {checkLabel(record.type)} · <span className={!isClear(record) && showsProvenance(record) ? "font-medium" : ""}>{resultWords(record)}</span>
      {showsProvenance(record) && <> · <Provenance value={record.provenance} at={record.retrieved_at} /></>}
    </button>
  );
}

// The Suppliers & Evidence tab: one row per supplier with its quote, evidence checks, and policy verdict.
export function SupplierEvidence({ missionId, token, rows, quotes, run, canReview, checking, actions }: {
  missionId: string; token: string; rows: SupplierRow[]; quotes: Quote[]; run: Run; canReview: boolean; checking: boolean; actions: ReactNode;
}) {
  // The last record stays set while the drawer slides closed.
  const [drawer, setDrawer] = useState<{ record: Evidence; supplierId: string } | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [review, setReview] = useState<Review | null>(null);
  const latestQuote = new Map<string, Quote>();
  for (const quote of quotes) {
    const seen = latestQuote.get(quote.supplier_id);
    if (!seen || (seen.status !== "submitted" && quote.status === "submitted")) latestQuote.set(quote.supplier_id, quote);
  }
  const allTest = rows.length > 0 && rows.every((row) => row.supplier.is_demo);
  const blockingFor = (row: SupplierRow) => [
    ...row.policy.decisions.filter((decision) => decision.status === "NEEDS_REVIEW" || decision.status === "BLOCK"),
    ...row.quotes.flatMap((entry) => entry.policy.decisions.filter((decision) => decision.status === "NEEDS_REVIEW" || decision.status === "BLOCK")),
  ];
  const submitReview = (item: Review, reason: string) => run(async () => {
    await api(`/v1/missions/${missionId}/suppliers/${item.supplierId}/review`, { method: "POST", token, body: JSON.stringify(item.action === "clear" ? { action: "clear", rule_id: item.ruleId, reason } : { action: item.action, reason }) });
    setReview(null);
  });
  const drawerRow = drawer && rows.find((row) => row.supplier.id === drawer.supplierId);
  return (
    <section aria-label="Supplier evidence and policy">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h2 className="text-xl font-semibold">Suppliers{allTest && <span className="font-normal text-muted-foreground"> · TEST data</span>}</h2>
        <div className="flex flex-wrap items-center gap-3">{actions}</div>
      </div>
      <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
        Only eligible quotes reach the optimizer. Missing or unavailable screening means Needs review, never a pass. No language model makes these calls.{" "}
        <button type="button" className="font-medium text-foreground hover:underline disabled:opacity-50" disabled={checking || rows.length === 0} onClick={() => void run(async () => { await api(`/v1/missions/${missionId}/evidence/refresh`, { method: "POST", token }); })}>{checking ? "Checks running…" : "Run evidence checks"}</button>
      </p>

      {rows.length === 0 ? <p className="mt-8 text-sm text-muted-foreground">No suppliers have quoted yet. Send an RFQ or discover leads; evidence is collected once a supplier quotes.</p> : (
        <div className="mt-6">
          <div className="hidden grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)_minmax(0,0.9fr)] gap-8 border-b pb-2 text-xs font-medium text-muted-foreground md:grid">
            <span>Supplier &amp; quote</span><span>Evidence checks</span><span>Policy</span>
          </div>
          {rows.map((row) => {
            const supplier = row.supplier.legal_name ?? row.supplier.email ?? "Supplier";
            const quote = latestQuote.get(row.supplier.id);
            const withdrawn = quote && quote.status !== "submitted";
            const records = EVIDENCE_ORDER.map(([type]) => row.latest_evidence[type]).filter((record): record is Evidence => Boolean(record));
            const clear = records.filter(isClear).length;
            const allClear = records.length > 0 && clear === records.length;
            const blocking = blockingFor(row);
            const blocked = row.reviews.find((entry) => entry.action === "block" || entry.action === "unblock")?.action === "block";
            const open = (record: Evidence) => { setDrawer({ record, supplierId: row.supplier.id }); setDrawerOpen(true); };
            const line = quote?.lines[0];
            return (
              <article key={row.supplier.id} data-testid={`supplier-${row.supplier.legal_name ?? row.supplier.email}`} className={cn("grid gap-3 border-b py-5 md:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)_minmax(0,0.9fr)] md:gap-8", withdrawn && "text-tertiary")}>
                <div className="min-w-0">
                  <h3 className="text-base">{supplier}</h3>
                  {!row.supplier.is_demo && <p className="text-xs text-muted-foreground">{row.supplier.email} · <Provenance value="USER_SUBMITTED" /></p>}
                  {quote && line ? (
                    <p className={cn("mt-1 text-sm tabular", !withdrawn && "text-muted-foreground")}>
                      {quote.lines.map((entry) => `${entry.available_quantity} @ ${money(entry.unit_price)}`).join("; ")} · Ship {amount(quote.shipping_cost)}
                      <span className="block">ETA {day(line.delivery_date)} · v{quote.version}</span>
                    </p>
                  ) : <p className="mt-1 text-sm text-muted-foreground">No quote yet</p>}
                </div>
                <div className="min-w-0">
                  {records.length === 0 ? <p className="text-sm text-muted-foreground">Checks start once the supplier quotes.</p>
                    : allClear ? (
                      <details>
                        <summary className="cursor-pointer text-sm">{clear} of {records.length} checks clear · <span className="font-medium">View checks</span></summary>
                        <div className="mt-1">{records.map((record) => <CheckLine key={record.id} record={record} onOpen={() => open(record)} />)}</div>
                      </details>
                    ) : records.map((record) => <CheckLine key={record.id} record={record} onOpen={() => open(record)} />)}
                </div>
                <div className="min-w-0 text-sm">
                  {withdrawn ? <StatusText tone="muted">{words(quote.status)}</StatusText> : (
                    <>
                      <p><PolicyText value={row.policy.status} />{blocked && <span className="text-muted-foreground"> · blocked by a reviewer</span>}</p>
                      {blocking.map((decision) => (
                        <div key={`${decision.rule_id}-${decision.subject_id}`} className="mt-1.5">
                          <p className="text-muted-foreground">{words(decision.rule_id)}</p>
                          {canReview && CLEARABLE.has(decision.rule_id) && <Button variant="text" size="sm" className="mt-0.5 px-0" onClick={() => setReview({ supplierId: row.supplier.id, supplier, action: "clear", ruleId: decision.rule_id, finding: words(decision.rule_id) })}>Clear finding</Button>}
                        </div>
                      ))}
                      <details className="mt-2">
                        <summary className="cursor-pointer text-muted-foreground">All policy decisions ({row.policy.decisions.length})</summary>
                        <ul className="mt-1 space-y-1 text-xs">{row.policy.decisions.map((decision) => <li key={decision.rule_id}><PolicyText scope="rule" value={decision.status} /> · {words(decision.rule_id)}: <span className="text-muted-foreground">{decision.reason}</span></li>)}</ul>
                        {row.reviews.length > 0 && <ul className="mt-2 space-y-0.5 border-t pt-1 text-xs text-muted-foreground">{row.reviews.map((entry) => <li key={entry.id}>{when(entry.created_at)} · {entry.action}{entry.rule_id ? ` ${words(entry.rule_id)}` : ""}: {entry.reason}</li>)}</ul>}
                      </details>
                      {canReview && <Button variant="text" size="sm" className="mt-1 px-0" onClick={() => setReview({ supplierId: row.supplier.id, supplier, action: blocked ? "unblock" : "block" })}>{blocked ? "Unblock supplier" : "Block supplier"}</Button>}
                    </>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}
      {drawer && drawerRow && (
        <EvidenceDrawer open={drawerOpen} record={drawer.record} row={drawerRow} blocking={blockingFor(drawerRow)} canReview={canReview} onClose={() => setDrawerOpen(false)}
          onReview={(item) => { setDrawerOpen(false); setReview(item); }}
          onDossier={() => void run(async () => { await api(`/v1/missions/${missionId}/suppliers/${drawerRow.supplier.id}/premium-dossier`, { method: "POST", token }); })} />
      )}
      <ReviewDialog review={review} onClose={() => setReview(null)} onSubmit={submitReview} />
    </section>
  );
}
