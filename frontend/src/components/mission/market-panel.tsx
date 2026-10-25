"use client";

import { ExternalLink } from "lucide-react";
import { useState } from "react";

import { Dialog, Drawer } from "@/components/patterns/overlays";
import { Provenance, StatusText, ago } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import type { Job, Lead, Mission } from "@/lib/types";
import type { Invitation } from "./use-mission-data";

type Run = (operation: () => Promise<void>) => Promise<void>;

type RfqResponse = { supplier_email: string; delivery_status: string; delivery?: { provider?: string | null; message_id?: string | null; error?: string | null }; invitation_url?: string; link_reason?: "development" | "email_not_sent" };

// Never imply delivery: a sent email cites the provider's message id; anything else says it was NOT sent.
export function rfqNotice(response: RfqResponse) {
  if (response.link_reason === "development") return `Development invitation: ${response.invitation_url}`;
  if (response.delivery_status === "sent") return `RFQ emailed to ${response.supplier_email} via ${response.delivery?.provider ?? "email"} (message ${response.delivery?.message_id ?? "accepted"}).`;
  return `Email NOT sent to ${response.supplier_email} (${response.delivery?.error ?? response.delivery_status}). Share this secure RFQ link with them yourself; only that address can accept it: ${response.invitation_url}`;
}

const words = (code: string) => code.charAt(0).toUpperCase() + code.slice(1).toLowerCase().replace(/_/g, " ");

// Header actions of the Suppliers & Evidence tab: invitations drawer, Send RFQ and Discover leads dialogs,
// and the demo-only seeding of labeled TEST suppliers.
export function MarketActions({ mission, token, invitations, jobs, run, setNotice, canSeed }: {
  mission: Mission; token: string; invitations: Invitation[]; jobs: Job[]; run: Run; setNotice: (value: string) => void; canSeed: boolean;
}) {
  const [open, setOpen] = useState<"invitations" | "rfq" | "discover" | null>(null);
  const [supplierEmail, setSupplierEmail] = useState("");
  const [query, setQuery] = useState(`${mission.requirements[0]?.item ?? "relief supplies"} wholesale supplier`);
  const discovery = jobs.find((job) => job.type === "supplier_discovery");
  const discovering = discovery?.status === "queued" || discovery?.status === "running";
  const close = (next: boolean) => { if (!next) setOpen(null); };
  const sendRfq = () => run(async () => {
    const response = await api<RfqResponse>(`/v1/missions/${mission.id}/invitations`, { method: "POST", token, body: JSON.stringify({ supplier_email: supplierEmail }) });
    setNotice(rfqNotice(response)); setSupplierEmail(""); setOpen(null);
  });
  const discover = () => run(async () => {
    await api(`/v1/missions/${mission.id}/discovery`, { method: "POST", token, body: JSON.stringify({ query, location: mission.delivery_location, max_results: 8 }) });
    setNotice("Apify discovery run started. Results arrive as supplier leads below; leads never carry binding prices."); setOpen(null);
  });
  const seed = () => run(async () => {
    await api(`/v1/missions/${mission.id}/demo/seed`, { method: "POST", token });
    setNotice("Seeded four labeled TEST suppliers with synthetic quotes. Live OFAC / openFDA / USAspending checks are running on their names.");
  });
  return (
    <>
      <button type="button" className="text-sm font-medium hover:underline" onClick={() => setOpen("invitations")}>RFQ invitations →</button>
      {canSeed && <Button variant="secondary" onClick={() => void seed()}>Seed TEST suppliers</Button>}
      <Button variant="secondary" onClick={() => setOpen("rfq")}>Send RFQ</Button>
      <Button variant="secondary" onClick={() => setOpen("discover")} disabled={discovering}>{discovering ? "Apify running…" : "Discover leads"}</Button>

      <Drawer open={open === "invitations"} onOpenChange={close} title="RFQ invitations" subtitle={`${invitations.length} sent for this mission`}>
        {invitations.length === 0 ? <p className="text-sm text-muted-foreground">No RFQs sent yet.</p> : (
          <ul>
            {invitations.map((invitation) => (
              <li key={invitation.id} className="border-b py-3 text-sm last:border-0">
                <div className="flex items-baseline justify-between gap-3"><span className="truncate">{invitation.supplier_email}</span><span className="shrink-0">{words(invitation.status)}</span></div>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {invitation.is_demo && <><Provenance value="TEST" /> · </>}sent {ago(invitation.created_at)}
                  {invitation.delivery_status && invitation.delivery_status !== "sent" && invitation.delivery_status !== "not_sent_test_supplier" ? ` · email ${invitation.delivery_status.replace(/_/g, " ")}` : ""}
                </p>
              </li>
            ))}
          </ul>
        )}
      </Drawer>

      <Dialog open={open === "rfq"} onOpenChange={close} title="Send RFQ" footer={<Button type="submit" form="rfq-form">Send RFQ</Button>}>
        <form id="rfq-form" className="space-y-4" onSubmit={(event) => { event.preventDefault(); void sendRfq(); }}>
          <div><Label htmlFor="supplier-email">Supplier email</Label><Input id="supplier-email" type="email" required className="mt-1.5" value={supplierEmail} onChange={(event) => setSupplierEmail(event.target.value)} placeholder="supplier@example.com" /></div>
          <p className="text-muted-foreground">Only this address can accept the RFQ and submit a binding quote. If the email can&apos;t be delivered, you&apos;ll get a secure link to share yourself.</p>
        </form>
      </Dialog>

      <Dialog open={open === "discover"} onOpenChange={close} title="Discover leads" subtitle="Apify · public business listings" footer={<Button type="submit" form="discover-form">Discover leads</Button>}>
        <form id="discover-form" className="space-y-4" onSubmit={(event) => { event.preventDefault(); void discover(); }}>
          <div><Label htmlFor="discovery-query">Discovery query</Label><Input id="discovery-query" className="mt-1.5" value={query} onChange={(event) => setQuery(event.target.value)} /></div>
          <p className="text-muted-foreground">Searches listings near {mission.delivery_location}. A lead becomes a supplier only after it accepts an RFQ and submits its own quote.</p>
        </form>
      </Dialog>
    </>
  );
}

// Leads found by Apify discovery, each invitable with a verified sales email.
export function LeadsSection({ token, leads, jobs, run, setNotice }: { token: string; leads: Lead[]; jobs: Job[]; run: Run; setNotice: (value: string) => void }) {
  const [emails, setEmails] = useState<Record<string, string>>({});
  const discovery = jobs.find((job) => job.type === "supplier_discovery");
  const notConfigured = (discovery?.result as { status?: string } | null | undefined)?.status === "BLOCKED_EXTERNAL";
  if (leads.length === 0 && discovery?.status !== "failed" && !notConfigured) return null;
  return (
    <section aria-label="Supplier leads" className="mt-12">
      <h3 className="text-base font-semibold">Leads <span className="font-normal text-muted-foreground">· Apify discovery</span></h3>
      {discovery?.status === "failed" && <p className="mt-2 text-sm text-critical">Last discovery failed: {discovery.last_error}</p>}
      {notConfigured && <p className="mt-2 text-sm text-muted-foreground">Apify is not configured on this server.</p>}
      <ul className="mt-2">
        {leads.map((lead) => (
          <li key={lead.id} className="flex flex-wrap items-center justify-between gap-3 border-b py-3 text-sm">
            <div className="min-w-56 flex-1">
              <p>{lead.name} <span className="ml-1 text-muted-foreground">· {words(lead.status)}</span></p>
              <p className="mt-0.5 text-xs text-muted-foreground">{[lead.category, lead.phone, lead.address].filter(Boolean).join(" · ")}{lead.retrieved_at && <> · <Provenance value={lead.provenance} at={lead.retrieved_at} /></>}</p>
            </div>
            <div className="flex items-center gap-3">
              {lead.website && <a className="inline-flex items-center gap-1 text-sm hover:underline" href={lead.website} target="_blank" rel="noreferrer">Website<ExternalLink className="size-3.5" /></a>}
              {lead.status === "lead" && (
                <form className="flex gap-2" onSubmit={(event) => { event.preventDefault(); void run(async () => { const response = await api<{ invitation: RfqResponse }>(`/v1/leads/${lead.id}/invite`, { method: "POST", token, body: JSON.stringify({ supplier_email: emails[lead.id] }) }); setNotice(rfqNotice(response.invitation)); }); }}>
                  <Input aria-label={`RFQ email for ${lead.name}`} className="h-8 w-52" type="email" required placeholder="verified sales email" value={emails[lead.id] ?? ""} onChange={(event) => setEmails({ ...emails, [lead.id]: event.target.value })} />
                  <Button size="sm" variant="secondary" type="submit">Invite</Button>
                </form>
              )}
              {lead.status === "invited" && <StatusText tone="muted">RFQ sent to {lead.invited_email}</StatusText>}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
