"use client";

import { ExternalLink, FlaskConical, Search, Send } from "lucide-react";
import { useState } from "react";

import { Provenance, ago } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import type { Job, Lead, Mission } from "@/lib/types";
import type { Invitation } from "./use-mission-data";

type Run = (operation: () => Promise<void>) => Promise<void>;

const leadTone: Record<Lead["status"], string> = { lead: "text-muted-foreground", invited: "text-telemetry", onboarded: "text-ok", dismissed: "text-tertiary line-through" };

type RfqResponse = { supplier_email: string; delivery_status: string; delivery?: { provider?: string | null; message_id?: string | null; error?: string | null }; invitation_url?: string; link_reason?: "development" | "email_not_sent" };

// Never imply delivery: a sent email cites the provider's message id; anything else says it was NOT sent.
export function rfqNotice(response: RfqResponse) {
  if (response.link_reason === "development") return `Development invitation: ${response.invitation_url}`;
  if (response.delivery_status === "sent") return `RFQ emailed to ${response.supplier_email} via ${response.delivery?.provider ?? "email"} (message ${response.delivery?.message_id ?? "accepted"}).`;
  return `Email NOT sent to ${response.supplier_email} (${response.delivery?.error ?? response.delivery_status}). Share this secure RFQ link with them yourself; only that address can accept it: ${response.invitation_url}`;
}

export function MarketPanel({ mission, token, leads, invitations, jobs, run, setNotice, demoMode, hasDemo }: {
  mission: Mission; token: string; leads: Lead[]; invitations: Invitation[]; jobs: Job[]; run: Run; setNotice: (value: string) => void; demoMode: boolean; hasDemo: boolean;
}) {
  const [supplierEmail, setSupplierEmail] = useState("");
  const [query, setQuery] = useState(`${mission.requirements[0]?.item ?? "relief supplies"} wholesale supplier`);
  const [leadEmails, setLeadEmails] = useState<Record<string, string>>({});
  const discovery = jobs.find((job) => job.type === "supplier_discovery");
  const discoveryRunning = discovery && (discovery.status === "queued" || discovery.status === "running");
  return (
    <section aria-label="Supplier market" className="space-y-4 rounded-xl border bg-card p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-muted-foreground">Supplier market</h2>
        {demoMode && !hasDemo && <Button size="sm" variant="secondary" onClick={() => void run(async () => { await api(`/v1/missions/${mission.id}/demo/seed`, { method: "POST", token }); setNotice("Seeded four labeled TEST suppliers with synthetic quotes. Live OFAC / openFDA / USAspending checks are running on their names."); })}><FlaskConical className="size-3.5" />Seed TEST suppliers</Button>}
      </div>

      <form className="flex gap-2" onSubmit={(event) => { event.preventDefault(); void run(async () => { const response = await api<RfqResponse>(`/v1/missions/${mission.id}/invitations`, { method: "POST", token, body: JSON.stringify({ supplier_email: supplierEmail }) }); setNotice(rfqNotice(response)); setSupplierEmail(""); }); }}>
        <div className="flex-1"><Label className="sr-only" htmlFor="supplier-email">Supplier email</Label><Input id="supplier-email" type="email" required value={supplierEmail} onChange={(event) => setSupplierEmail(event.target.value)} placeholder="supplier@example.com" /></div>
        <Button type="submit"><Send className="size-3.5" />Send RFQ</Button>
      </form>

      <div className="rounded-lg border border-dashed p-3">
        <form className="flex gap-2" onSubmit={(event) => { event.preventDefault(); void run(async () => { await api(`/v1/missions/${mission.id}/discovery`, { method: "POST", token, body: JSON.stringify({ query, location: mission.delivery_location, max_results: 8 }) }); setNotice("Apify discovery run started. Results arrive as supplier leads; leads never carry binding prices."); }); }}>
          <div className="flex-1"><Label className="sr-only" htmlFor="discovery-query">Discovery query</Label><Input id="discovery-query" value={query} onChange={(event) => setQuery(event.target.value)} /></div>
          <Button type="submit" variant="secondary" disabled={Boolean(discoveryRunning)}><Search className="size-3.5" />{discoveryRunning ? "Apify running…" : "Discover leads"}</Button>
        </form>
        <p className="mt-1.5 text-[11px] text-tertiary">Apify actor searches public business listings near {mission.delivery_location}. A lead becomes a supplier only after it accepts an RFQ and submits its own quote.</p>
        {discovery?.status === "failed" && <p className="mt-1 text-xs text-critical">Last discovery failed: {discovery.last_error}</p>}
        {discovery?.result && (discovery.result as { status?: string }).status === "BLOCKED_EXTERNAL" && <p className="mt-1 text-xs text-muted-foreground">Apify is not configured on this server.</p>}
        {leads.length > 0 && (
          <ul className="mt-3 divide-y divide-border/60">
            {leads.map((lead) => (
              <li key={lead.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                <div className="min-w-48 flex-1">
                  <div className="flex items-center gap-2"><span className="font-medium">{lead.name}</span><Provenance value={lead.provenance} /><span className={`font-mono text-[10px] uppercase ${leadTone[lead.status]}`}>{lead.status}</span></div>
                  <p className="text-xs text-muted-foreground">{[lead.category, lead.phone, lead.address].filter(Boolean).join(" · ")}</p>
                  <p className="font-mono text-[10px] text-tertiary">apify run {lead.apify_run_id?.slice(0, 10)} · dataset {lead.apify_dataset_id?.slice(0, 10)} · {ago(lead.retrieved_at)}</p>
                </div>
                <div className="flex items-center gap-2">
                  {lead.website && <a className="text-live" href={lead.website} target="_blank" rel="noreferrer" aria-label={`${lead.name} website`}><ExternalLink className="size-3.5" /></a>}
                  {lead.status === "lead" && (
                    <form className="flex gap-1" onSubmit={(event) => { event.preventDefault(); void run(async () => { const response = await api<{ invitation: RfqResponse }>(`/v1/leads/${lead.id}/invite`, { method: "POST", token, body: JSON.stringify({ supplier_email: leadEmails[lead.id] }) }); setNotice(rfqNotice(response.invitation)); }); }}>
                      <Input aria-label={`RFQ email for ${lead.name}`} className="h-7 w-48 text-xs" type="email" required placeholder="verified sales email" value={leadEmails[lead.id] ?? ""} onChange={(event) => setLeadEmails({ ...leadEmails, [lead.id]: event.target.value })} />
                      <Button size="sm" type="submit">Invite</Button>
                    </form>
                  )}
                  {lead.status === "invited" && <span className="text-xs text-muted-foreground">RFQ → {lead.invited_email}</span>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {invitations.length > 0 && (
        <div>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">RFQ invitations</h3>
          <ul className="grid gap-1 text-xs sm:grid-cols-2">
            {invitations.map((invitation) => (
              <li key={invitation.id} className="flex items-center justify-between gap-2 rounded border border-border/60 px-2 py-1">
                <span className="truncate">{invitation.supplier_email}</span>
                <span className="flex items-center gap-1.5">{invitation.is_demo && <Provenance value="TEST" />}<span className="font-mono text-[10px] uppercase text-muted-foreground">{invitation.status}{invitation.delivery_status && invitation.delivery_status !== "sent" && invitation.delivery_status !== "not_sent_test_supplier" ? ` · email ${invitation.delivery_status}` : ""}</span></span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
