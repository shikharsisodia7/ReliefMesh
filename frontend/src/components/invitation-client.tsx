"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Page, PageHeader } from "@/components/layout/page-header";
import { QuoteForm } from "@/components/quote-form";
import { day, money, when } from "@/components/status-badges";
import type { SupplierMission, SupplierQuote } from "@/components/supplier/types";
import { Button, buttonVariants } from "@/components/ui/button";
import { useAppConfig } from "@/hooks/use-config";
import { useSession } from "@/hooks/use-session";
import { api } from "@/lib/api";
import { clearSession } from "@/lib/session";
import type { QuoteDraft } from "@/lib/types";

type Invitation = { supplier_email: string; status: string; mission: SupplierMission; buyer_organization?: string | null };

const needed = (mission: SupplierMission) => mission.requirements.map((row) => `${row.quantity.toLocaleString("en-US")} ${row.item}`).join(", ");

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><dt className="text-sm text-muted-foreground">{label}</dt><dd className="mt-1 text-lg tabular">{children}</dd></div>;
}

// The read-only quote once it's submitted, from the supplier's saved quote.
function Submitted({ quote }: { quote: SupplierQuote }) {
  return (
    <div className="grid gap-12 lg:grid-cols-[minmax(0,7fr)_minmax(0,3fr)]">
      <section aria-label="Your quote">
        <h2 className="text-xl font-semibold">Your quote<span className="font-normal text-muted-foreground"> · v{quote.version}</span>{quote.is_demo && <span className="font-normal text-muted-foreground"> · TEST data</span>}</h2>
        {quote.lines.map((line) => (
          <dl key={line.requirement_id ?? line.item} className="mt-6 grid gap-6 sm:grid-cols-2">
            {quote.lines.length > 1 && <p className="font-semibold sm:col-span-2">{line.item}</p>}
            <Fact label="Unit price">{money(line.unit_price)}</Fact>
            <Fact label="Available quantity">{line.available_quantity.toLocaleString("en-US")}</Fact>
            <Fact label="Delivery date">{when(line.delivery_date)}</Fact>
          </dl>
        ))}
        <dl className="mt-6 grid gap-6 sm:grid-cols-2">
          <Fact label="Shipping cost">{money(quote.shipping_cost)}</Fact>
          <Fact label="Quote expiry">{when(quote.expires_at)}</Fact>
        </dl>
      </section>
      <aside>
        <h2 className="text-base font-semibold">Quote submitted</h2>
        <p className="mt-3 text-sm leading-relaxed">This quote is binding. You can revise or withdraw it from My Quotes. The buyer&apos;s plan will update automatically.</p>
        <p className="mt-3 text-sm text-muted-foreground">Compliance screening runs automatically; the buyer optimizes only over screened quotes.</p>
        <Link href="/supplier?tab=quotes" className={buttonVariants({ size: "lg", className: "mt-6 w-full" })}>View in My Quotes</Link>
      </aside>
    </div>
  );
}

export function InvitationClient({ token }: { token: string }) {
  const router = useRouter();
  const client = useQueryClient();
  const session = useSession();
  const config = useAppConfig();
  const [accepted, setAccepted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const supplier = session?.user.role === "supplier" ? session.token : undefined;
  const invitation = useQuery({ queryKey: ["invitation", token], queryFn: () => api<Invitation>(`/v1/supplier-invitations/${token}`) });
  const profile = useQuery({ queryKey: ["supplier-profile", supplier], enabled: Boolean(supplier), queryFn: () => api<{ legal_name?: string | null }>("/v1/supplier/profile", { token: supplier }) });
  const quotes = useQuery({ queryKey: ["supplier-quotes"], enabled: Boolean(supplier), queryFn: () => api<SupplierQuote[]>("/v1/supplier/quotes", { token: supplier }) });
  if (invitation.isLoading) return <Page><p className="text-sm text-muted-foreground">Loading RFQ…</p></Page>;
  if (!invitation.data) return <Page><p className="text-sm text-critical">{invitation.error?.message ?? "This RFQ invitation is unavailable."}</p></Page>;
  const { mission, supplier_email: email } = invitation.data;
  const active = accepted || invitation.data.status === "accepted";
  const next = encodeURIComponent(`/invitations/${token}`);
  const buyer = invitation.data.buyer_organization;
  const summary = `${buyer ? `${buyer} · ` : ""}${needed(mission)} needed · Deliver to ${mission.delivery_location} by ${day(mission.delivery_deadline)}`;
  const quote = quotes.data?.find((row) => row.mission_id === mission.id && row.status === "submitted");

  // Before the quote form: a centered column with the request and one action.
  if (!session || session.user.role !== "supplier" || !active) {
    return (
      <Page className="grid place-items-center pt-16">
        <section className="w-full max-w-[440px]">
          <p className="text-sm text-muted-foreground">Request for quotation</p>
          <h1 className="mt-1 text-[28px] leading-tight font-semibold tracking-tight">{mission.name}</h1>
          <dl className="mt-6 space-y-2 text-sm">
            {buyer && <div className="flex justify-between gap-4"><dt className="text-muted-foreground">Buyer</dt><dd>{buyer}</dd></div>}
            <div className="flex justify-between gap-4"><dt className="text-muted-foreground">Needed</dt><dd>{needed(mission)}</dd></div>
            <div className="flex justify-between gap-4"><dt className="text-muted-foreground">Deliver to</dt><dd>{mission.delivery_location}</dd></div>
            <div className="flex justify-between gap-4"><dt className="text-muted-foreground">Deliver by</dt><dd>{when(mission.delivery_deadline)}</dd></div>
            <div className="flex justify-between gap-4"><dt className="text-muted-foreground">Sent to</dt><dd>{email}</dd></div>
          </dl>
          {error && <p role="alert" className="mt-4 text-sm text-critical">{error}</p>}
          <div className="mt-8">
            {!session ? (
              <>
                <Link href={`/sign-up?role=supplier&next=${next}`} className={buttonVariants({ size: "lg", className: "w-full" })}>Register as supplier</Link>
                <p className="mt-3 text-center text-sm text-muted-foreground">Already registered? <Link className="font-medium text-foreground hover:underline" href={`/sign-in?next=${next}`}>Sign in</Link> with {email}.</p>
              </>
            ) : session.user.role !== "supplier" ? (
              <>
                <p className="text-sm">This link must be accepted with a supplier account. You are signed in as {session.user.email ?? "a coordinator"}.</p>
                <Button variant="secondary" className="mt-4 w-full" onClick={() => { clearSession(); router.push(`/sign-up?role=supplier&next=${next}`); }}>Sign out and continue as {email}</Button>
              </>
            ) : (
              <>
                <Button size="lg" className="w-full" onClick={() => void (async () => { setError(null); try { await api(`/v1/supplier-invitations/${token}/accept`, { method: "POST", token: session.token }); setAccepted(true); } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Could not accept invitation"); } })()}>Accept RFQ</Button>
                <p className="mt-3 text-center text-sm text-muted-foreground">Accepting lets you submit a binding quote. It doesn&apos;t commit you to anything yet.</p>
              </>
            )}
          </div>
        </section>
      </Page>
    );
  }

  // Wait for the supplier's quotes, so a saved quote never flashes the empty form first.
  if (quotes.isLoading) return <Page><p className="text-sm text-muted-foreground">Loading your quote…</p></Page>;
  return (
    <Page>
      <PageHeader title={mission.name} meta={summary} activity={[profile.data?.legal_name, session.user.email].filter(Boolean).join(" · ")} />
      <div className="mt-8 border-t pt-8">
        {error && <p role="alert" className="mb-6 text-sm text-critical">{error}</p>}
        {quote ? <Submitted quote={quote} /> : (
          <QuoteForm
            key={profile.data?.legal_name ?? "new"} requirements={mission.requirements} legalName={profile.data?.legal_name}
            assistant={config.data ? (config.data.quote_assistant ? "on" : "off") : "unknown"}
            onDraft={config.data?.quote_assistant ? (text) => api<QuoteDraft>(`/v1/supplier-invitations/${token}/quote-draft`, { method: "POST", token: session.token, body: JSON.stringify({ text }) }) : undefined}
            onSubmit={async (values) => {
              setError(null);
              try {
                await api("/v1/quotes", { method: "POST", token: session.token, body: JSON.stringify({ invitation_token: token, expires_at: new Date(values.expires_at).toISOString(), currency: "USD", shipping_cost: values.shipping_cost.toFixed(2), supplier_profile: { legal_name: values.legal_name, website: values.website || null }, lines: values.lines.map((line) => ({ requirement_id: line.requirement_id || null, item: line.item, unit_price: line.unit_price.toFixed(2), available_quantity: line.available_quantity, delivery_date: new Date(line.delivery_date).toISOString() })) }) });
                await client.invalidateQueries({ queryKey: ["supplier-quotes"] });
              } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Quote submission failed"); }
            }}
          />
        )}
      </div>
    </Page>
  );
}
