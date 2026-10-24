"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { QuoteForm } from "@/components/quote-form";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useSession } from "@/hooks/use-session";
import { api } from "@/lib/api";

type Invitation = { supplier_email: string; status: string; mission: { id: string; name: string; delivery_location: string; delivery_deadline: string; requirements: { item: string; quantity: number }[] } };

export function InvitationClient({ token }: { token: string }) {
  const router = useRouter();
  const session = useSession();
  const [accepted, setAccepted] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const invitation = useQuery({ queryKey: ["invitation", token], queryFn: () => api<Invitation>(`/v1/supplier-invitations/${token}`) });
  if (invitation.isLoading) return <main className="grid min-h-screen place-items-center">Loading RFQ…</main>;
  if (!invitation.data) return <main className="grid min-h-screen place-items-center">This RFQ invitation is unavailable.</main>;
  const active = accepted || invitation.data.status === "accepted";
  return <main className="min-h-screen bg-slate-50 px-5 py-12"><div className="mx-auto max-w-2xl space-y-5"><Link href="/" className="text-sm font-semibold">RELIEFMESH</Link><Card><CardHeader><CardTitle>Request for quotation: {invitation.data.mission.name}</CardTitle><CardDescription>Deliver to {invitation.data.mission.delivery_location} by {new Date(invitation.data.mission.delivery_deadline).toLocaleString()}.</CardDescription></CardHeader><CardContent><ul className="mb-6 list-disc pl-5 text-sm">{invitation.data.mission.requirements.map((requirement) => <li key={requirement.item}>{requirement.quantity} {requirement.item}</li>)}</ul>{error && <p className="mb-4 rounded-md bg-destructive/10 p-3 text-sm text-destructive">{error}</p>}{notice && <p className="mb-4 rounded-md bg-cyan-50 p-3 text-sm text-cyan-950">{notice}</p>}{!session ? <p className="text-sm">Sign in with <strong>{invitation.data.supplier_email}</strong> to securely accept this RFQ. <Link className="underline" href="/sign-in">Sign in</Link> or <Link className="underline" href="/sign-up?role=supplier">register as supplier</Link>.</p> : session.user.role !== "supplier" ? <p className="text-sm text-destructive">This link must be accepted with a supplier account.</p> : !active ? <Button onClick={() => void (async () => { try { await api(`/v1/supplier-invitations/${token}/accept`, { method: "POST", token: session.token }); setAccepted(true); } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Could not accept invitation"); } })()}>Accept RFQ</Button> : <QuoteForm item={invitation.data.mission.requirements[0]?.item ?? ""} onSubmit={async (values) => { try { await api("/v1/quotes", { method: "POST", token: session.token, body: JSON.stringify({ invitation_token: token, expires_at: new Date(values.expires_at).toISOString(), shipping_cost: values.shipping_cost.toFixed(2), lines: [{ item: values.item, unit_price: values.unit_price.toFixed(2), available_quantity: values.available_quantity, delivery_date: new Date(values.delivery_date).toISOString() }] }) }); setNotice("Quote submitted. The coordinator can now optimize using this real submission."); router.push("/supplier"); } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Quote submission failed"); } }} />}</CardContent></Card></div></main>;
}
