"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { QuoteForm } from "@/components/quote-form";
import { when } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useSession } from "@/hooks/use-session";
import { api } from "@/lib/api";

type Invitation = { supplier_email: string; status: string; mission: { id: string; name: string; delivery_location: string; delivery_deadline: string; requirements: { id?: string; item: string; quantity: number }[] } };

export function InvitationClient({ token }: { token: string }) {
  const router = useRouter();
  const session = useSession();
  const [accepted, setAccepted] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const invitation = useQuery({ queryKey: ["invitation", token], queryFn: () => api<Invitation>(`/v1/supplier-invitations/${token}`) });
  const profile = useQuery({ queryKey: ["supplier-profile", session?.token], enabled: session?.user.role === "supplier", queryFn: () => api<{ legal_name?: string | null }>("/v1/supplier/profile", { token: session!.token }) });
  if (invitation.isLoading) return <main className="grid min-h-screen place-items-center bg-background text-muted-foreground">Loading RFQ…</main>;
  if (!invitation.data) return <main className="grid min-h-screen place-items-center bg-background text-muted-foreground">{invitation.error?.message ?? "This RFQ invitation is unavailable."}</main>;
  const active = accepted || invitation.data.status === "accepted";
  return (
    <main className="min-h-screen bg-background px-5 py-12"><div className="mx-auto max-w-2xl space-y-5">
      <Link href="/" className="font-mono text-sm font-bold tracking-[0.2em]">RELIEF<span className="text-live">MESH</span></Link>
      <Card><CardHeader><CardTitle>Request for quotation: {invitation.data.mission.name}</CardTitle><CardDescription>Deliver to {invitation.data.mission.delivery_location} by {when(invitation.data.mission.delivery_deadline)}.</CardDescription></CardHeader><CardContent>
        <ul className="mb-6 list-disc pl-5 text-sm">{invitation.data.mission.requirements.map((requirement) => <li key={requirement.item}>{requirement.quantity} {requirement.item}</li>)}</ul>
        {error && <p className="mb-4 rounded-md border border-critical/40 bg-critical/10 p-3 text-sm text-critical">{error}</p>}
        {notice && <p className="mb-4 rounded-md border border-live/30 bg-live/10 p-3 text-sm text-live">{notice}</p>}
        {!session ? <p className="text-sm">Sign in with <strong>{invitation.data.supplier_email}</strong> to securely accept this RFQ. <Link className="underline" href="/sign-in">Sign in</Link> or <Link className="underline" href="/sign-up?role=supplier">register as supplier</Link>.</p>
          : session.user.role !== "supplier" ? <p className="text-sm text-critical">This link must be accepted with a supplier account.</p>
          : !active ? <Button onClick={() => void (async () => { try { await api(`/v1/supplier-invitations/${token}/accept`, { method: "POST", token: session.token }); setAccepted(true); } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Could not accept invitation"); } })()}>Accept RFQ</Button>
          : <QuoteForm key={profile.data?.legal_name ?? "new"} requirements={invitation.data.mission.requirements} legalName={profile.data?.legal_name} onSubmit={async (values) => { try {
              await api("/v1/quotes", { method: "POST", token: session.token, body: JSON.stringify({ invitation_token: token, expires_at: new Date(values.expires_at).toISOString(), currency: "USD", shipping_cost: values.shipping_cost.toFixed(2), supplier_profile: { legal_name: values.legal_name, website: values.website || null }, lines: values.lines.map((line) => ({ requirement_id: line.requirement_id || null, item: line.item, unit_price: line.unit_price.toFixed(2), available_quantity: line.available_quantity, delivery_date: new Date(line.delivery_date).toISOString() })) }) });
              setNotice("Quote submitted. Compliance screening runs automatically; the coordinator optimizes only over screened quotes."); router.push("/supplier");
            } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Quote submission failed"); } }} />}
      </CardContent></Card>
    </div></main>
  );
}
