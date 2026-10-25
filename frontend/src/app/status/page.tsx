"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { useState } from "react";

import { ProvenanceBadge, StatusDot, ago } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import { API_BASE_URL, api } from "@/lib/api";
import type { IntegrationCheck } from "@/lib/types";

type StatusPayload = { checked_at: string; environment: string; integrations: IntegrationCheck[] };
type X402Proof = { notice: string; proof: { transaction: string; explorer_url: string; amount_display: string; payer: string; pay_to: string; network_label: string; created_at: string } | null; reused?: boolean };
type CrsProof = { provider: string; notice: string; checked_at: string; results: { persona_id: string; test_identity: string; outcome: "verified" | "flagged" | "unavailable" | "not_configured"; expected?: string; messages: { code: string; text: string }[]; error?: string | null }[] };

const tone = { ok: "ok", degraded: "warn", not_configured: "idle", error: "critical" } as const;
const label = { ok: "OPERATIONAL", degraded: "DEGRADED", not_configured: "NOT CONFIGURED", error: "ERROR" } as const;

export default function StatusPage() {
  const [refresh, setRefresh] = useState(0);
  const status = useQuery({ queryKey: ["integration-status", refresh], queryFn: () => api<StatusPayload>(`/v1/integrations/status${refresh ? "?refresh=true" : ""}`), refetchInterval: 60_000 });
  const x402Proof = useQuery({ queryKey: ["x402-proof"], queryFn: () => api<X402Proof>("/v1/sandbox/x402-proof") });
  const [paying, setPaying] = useState(false);
  const [payError, setPayError] = useState<string | null>(null);
  const runPayment = async () => {
    setPaying(true); setPayError(null);
    try { await api<X402Proof>("/v1/sandbox/x402-proof", { method: "POST" }); await x402Proof.refetch(); }
    catch (error) { setPayError(error instanceof Error ? error.message : "Payment failed"); }
    finally { setPaying(false); }
  };
  const crsProof = useQuery({ queryKey: ["crs-proof"], queryFn: () => api<CrsProof>("/v1/sandbox/crs-proof"), staleTime: 5 * 60_000 });
  const groups = new Map<string, IntegrationCheck[]>();
  for (const check of status.data?.integrations ?? []) groups.set(check.category, [...(groups.get(check.category) ?? []), check]);
  return (
    <main className="min-h-screen bg-background panel-grid">
      <div className="mx-auto max-w-5xl space-y-6 px-5 py-10">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <Link className="font-mono text-sm font-bold tracking-[0.2em]" href="/">RELIEF<span className="text-live">MESH</span></Link>
            <h1 className="mt-3 text-3xl font-semibold">Integration status</h1>
            <p className="mt-1 text-sm text-muted-foreground">Each row is a real request made by the API just now (cached for 60 s). Green only appears when that request succeeded. API: <span className="font-mono">{API_BASE_URL}</span></p>
          </div>
          <Button variant="outline" size="sm" disabled={status.isFetching} onClick={() => setRefresh((value) => value + 1)}><RefreshCw className={status.isFetching ? "size-3.5 animate-spin" : "size-3.5"} />Re-check now</Button>
        </div>
        {status.isError && <p className="rounded border border-critical/40 bg-critical/10 p-3 text-sm text-critical">The ReliefMesh API is unreachable: {status.error.message}</p>}
        {status.isLoading && <p className="text-muted-foreground">Running live checks…</p>}
        {[...groups.entries()].map(([category, checks]) => (
          <section key={category} className="rounded-xl border bg-card">
            <h2 className="border-b px-4 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">{category}</h2>
            <ul className="divide-y divide-border/60">
              {checks.map((check) => (
                <li key={check.id} className="grid gap-1 px-4 py-3 sm:grid-cols-[220px_150px_1fr_80px] sm:items-center">
                  <span className="flex items-center gap-2 font-medium"><StatusDot tone={tone[check.status]} />{check.name}</span>
                  <span className="flex items-center gap-2 font-mono text-[11px]"><span className={check.status === "ok" ? "text-ok" : check.status === "error" ? "text-critical" : check.status === "degraded" ? "text-warn" : "text-muted-foreground"}>{label[check.status]}</span>{check.provenance && <ProvenanceBadge value={check.provenance} />}</span>
                  <span className="text-sm text-muted-foreground">{check.detail}</span>
                  <span className="font-mono text-[11px] text-tertiary sm:text-right">{check.latency_ms} ms</span>
                </li>
              ))}
            </ul>
          </section>
        ))}
        <section aria-label="Sponsor sandbox proof" className="rounded-xl border bg-card">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-2">
            <h2 className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Sponsor sandbox proof · {crsProof.data?.provider ?? "CRS Credit API sandbox"}</h2>
            <ProvenanceBadge value="SANDBOX" />
          </div>
          <p className="px-4 pt-3 text-xs text-muted-foreground">{crsProof.data?.notice ?? "Live identity check on CRS-published test identities."}</p>
          {crsProof.isLoading && <p className="px-4 py-3 text-sm text-muted-foreground">Running the CRS sandbox check…</p>}
          {crsProof.isError && <p className="px-4 py-3 text-sm text-critical">CRS sandbox check failed: {crsProof.error.message}</p>}
          <ul className="divide-y divide-border/60">
            {crsProof.data?.results.map((row) => (
              <li key={row.persona_id} className="grid gap-1 px-4 py-3 sm:grid-cols-[220px_150px_1fr] sm:items-center">
                <span className="font-medium">Test identity {row.persona_id} <span className="font-mono text-[11px] text-tertiary">{row.test_identity}</span></span>
                <span className={`font-mono text-[11px] ${row.outcome === "verified" ? "text-ok" : row.outcome === "flagged" ? "text-warn" : "text-critical"}`}>{row.outcome.toUpperCase()}{row.expected && row.outcome === row.expected ? " · as expected" : ""}</span>
                <span className="text-sm text-muted-foreground">{row.messages.length ? row.messages.map((m) => `${m.code}: ${m.text}`).join("; ") : row.error ?? (row.outcome === "verified" ? "Name, SSN, DOB and address belong together; no fraud flags" : "")}</span>
              </li>
            ))}
          </ul>
        </section>
        <section aria-label="Devnet payment proof" className="rounded-xl border bg-card">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-2">
            <h2 className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Sponsor sandbox proof · Coinbase x402 on Solana devnet</h2>
            <span className="flex gap-1.5"><ProvenanceBadge value="SANDBOX" /><span className="rounded border border-violet-400/40 px-1.5 py-0.5 font-mono text-[10px] text-violet-300">DEVNET · TEST PAYMENT</span></span>
          </div>
          <p className="px-4 pt-3 text-xs text-muted-foreground">{x402Proof.data?.notice ?? "HTTP 402 → signed USDC transfer → facilitator settlement on Solana devnet."}</p>
          <div className="flex flex-wrap items-center gap-3 px-4 py-3">
            <Button variant="outline" size="sm" disabled={paying} onClick={() => void runPayment()}>{paying ? "Paying over HTTP 402…" : "Run a devnet x402 payment"}</Button>
            {x402Proof.data?.proof ? (
              <span className="text-sm text-muted-foreground">Last settled {ago(x402Proof.data.proof.created_at)}: {x402Proof.data.proof.amount_display} · {x402Proof.data.proof.payer.slice(0, 6)}… → {x402Proof.data.proof.pay_to.slice(0, 6)}… · <a className="font-mono text-live hover:underline" href={x402Proof.data.proof.explorer_url} target="_blank" rel="noreferrer">tx {x402Proof.data.proof.transaction.slice(0, 16)}… ↗</a></span>
            ) : <span className="text-sm text-muted-foreground">No devnet payment run on this deployment yet.</span>}
          </div>
          {payError && <p className="px-4 pb-3 text-sm text-critical">{payError}</p>}
        </section>
        {status.data && <p className="text-xs text-tertiary">Environment {status.data.environment} · checked {ago(status.data.checked_at)}</p>}
      </div>
    </main>
  );
}
