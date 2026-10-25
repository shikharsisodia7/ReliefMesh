"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { Page, PageHeader } from "@/components/layout/page-header";
import { OrdersTab } from "@/components/supplier/orders-tab";
import { QuotesTab } from "@/components/supplier/quotes-tab";
import { RfqsTab } from "@/components/supplier/rfqs-tab";
import type { SupplierInvitation, SupplierMission, SupplierOrder, SupplierQuote } from "@/components/supplier/types";
import { useHydrated, useSession } from "@/hooks/use-session";
import { api } from "@/lib/api";
import { signInUrl } from "@/lib/session";

const titles: Record<string, string> = { rfqs: "RFQs", quotes: "My quotes", orders: "Purchase orders" };

export default function SupplierPage() {
  return <Suspense fallback={<Page><p className="text-sm text-muted-foreground">Loading supplier portal…</p></Page>}><SupplierPortal /></Suspense>;
}

// The tab comes from ?tab= and is switched by the supplier island (RFQs · My Quotes · Purchase Orders).
function SupplierPortal() {
  const router = useRouter();
  const session = useSession();
  const hydrated = useHydrated();
  const client = useQueryClient();
  const requested = useSearchParams().get("tab") ?? "rfqs";
  const tab = requested in titles ? requested : "rfqs";
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { if (hydrated && (!session || session.user.role !== "supplier")) router.replace(signInUrl()); }, [hydrated, router, session]);
  const token = session?.token;
  const get = <T,>(path: string) => () => api<T>(path, { token });
  const profile = useQuery({ queryKey: ["supplier-profile", token], enabled: Boolean(token), queryFn: get<{ legal_name?: string | null }>("/v1/supplier/profile") });
  const invitations = useQuery({ queryKey: ["supplier-invitations"], enabled: Boolean(token), queryFn: get<SupplierInvitation[]>("/v1/supplier/invitations") });
  const quotes = useQuery({ queryKey: ["supplier-quotes"], enabled: Boolean(token), queryFn: get<SupplierQuote[]>("/v1/supplier/quotes") });
  const orders = useQuery({ queryKey: ["supplier-orders"], enabled: Boolean(token), refetchInterval: 5000, queryFn: get<SupplierOrder[]>("/v1/purchase-orders") });
  if (!session) return <Page><p className="text-sm text-muted-foreground">Loading supplier portal…</p></Page>;

  // Runs a request, shows its API error as one line, and refreshes the supplier's records either way.
  const attempt = async (operation: () => Promise<unknown>) => {
    setError(null);
    try { await operation(); } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Request failed"); }
    await client.invalidateQueries({ predicate: (query) => String(query.queryKey[0]).startsWith("supplier-") });
  };
  const missions = new Map<string, SupplierMission>((invitations.data ?? []).map((row) => [row.mission.id, row.mission]));
  const failed = [invitations, quotes, orders].find((query) => query.isError);
  const loading = invitations.isLoading || quotes.isLoading || orders.isLoading;
  return (
    <Page>
      <PageHeader title={titles[tab]} meta={[profile.data?.legal_name, session.user.email].filter(Boolean).join(" · ")} />
      {error && <p role="alert" className="mt-4 text-sm text-critical">{error}</p>}
      {failed && <p className="mt-4 text-sm text-critical">{failed.error?.message} <button type="button" className="font-medium text-foreground hover:underline" onClick={() => void failed.refetch()}>Retry</button></p>}
      <div className="mt-10">
        {loading ? <div className="space-y-3" aria-label="Loading">{[0, 1].map((key) => <div key={key} className="h-16 animate-pulse rounded bg-muted motion-reduce:animate-none" />)}</div>
          : tab === "orders" ? <OrdersTab orders={orders.data ?? []} token={session.token} attempt={attempt} />
            : tab === "quotes" ? <QuotesTab quotes={quotes.data ?? []} missions={missions} token={session.token} attempt={attempt} />
              : <RfqsTab invitations={invitations.data ?? []} quotes={quotes.data ?? []} />}
      </div>
    </Page>
  );
}
