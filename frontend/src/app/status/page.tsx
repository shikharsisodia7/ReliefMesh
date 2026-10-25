"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight } from "lucide-react";
import Link from "next/link";
import { Fragment, useState } from "react";

import { Page, PageHeader } from "@/components/layout/page-header";
import { Provenance, StatusText, ago, clock, when } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import { Table } from "@/components/ui/table";
import { useSession } from "@/hooks/use-session";
import { API_BASE_URL, api } from "@/lib/api";
import type { IntegrationCheck } from "@/lib/types";

type StatusPayload = { checked_at: string; environment: string; integrations: IntegrationCheck[]; breakers?: Record<string, { failures: number; open: boolean }> };
type X402Proof = { notice: string; proof: { transaction: string; explorer_url: string; amount_display: string; payer: string; pay_to: string; network_label: string; created_at: string } | null; reused?: boolean };
type CrsProof = { provider: string; notice: string; checked_at: string; results: { persona_id: string; test_identity: string; outcome: "verified" | "flagged" | "unavailable" | "not_configured"; expected?: string; messages: { code: string; text: string }[]; error?: string | null }[] };

const tone = { ok: "neutral", degraded: "warn", not_configured: "muted", error: "critical" } as const;
const label = { ok: "Operational", degraded: "Degraded", not_configured: "Not configured", error: "Error" } as const;
// The API's categories, in reading order, with the names people use.
const groups: [string, string][] = [["open data", "Disaster signals"], ["evidence", "Supplier screening"], ["sponsor", "Agents and payments"], ["core", "Infrastructure"], ["operations", "Notifications and team tools"]];
const head = "py-2 pr-4 text-left text-xs font-medium text-muted-foreground last:pr-0 last:text-right";

// The API returns only the current check (no history), so the expanded row shows that check and the
// provider's circuit breaker, never a made-up timeline.
function CheckRow({ check, breaker }: { check: IntegrationCheck; breaker?: { failures: number; open: boolean } }) {
  const [open, setOpen] = useState(false);
  const configured = check.status !== "not_configured";
  const Chevron = open ? ChevronDown : ChevronRight;
  return (
    <>
      <tr className="border-b hover:bg-muted [&>td]:align-middle">
        <td className="py-2.5 pr-4">
          <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} className="inline-flex items-center gap-1.5 rounded-sm text-left font-medium outline-hidden focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring">
            <Chevron className="size-4 text-muted-foreground" aria-hidden />{check.name}
          </button>
        </td>
        <td className="py-2.5 pr-4"><StatusText tone={tone[check.status]} value={check.status}>{label[check.status]}</StatusText></td>
        <td className="py-2.5 pr-4">{check.provenance ? <Provenance value={check.provenance} /> : <span className="text-muted-foreground">—</span>}</td>
        <td className="py-2.5 pr-4 text-muted-foreground">{check.detail}</td>
        <td className="py-2.5 text-right whitespace-nowrap tabular">{configured ? `${check.latency_ms.toLocaleString("en-US")} ms` : "—"}</td>
      </tr>
      {open && (
        <tr className="border-b">
          <td colSpan={5} className="pt-3 pb-4 pl-[22px]">
            <p className="text-sm font-semibold">Current check</p>
            <dl className="mt-2 grid max-w-2xl grid-cols-[120px_1fr] gap-y-1 text-sm">
              <dt className="text-muted-foreground">Checked at</dt><dd className="tabular">{when(check.checked_at)} · {clock(check.checked_at)}</dd>
              <dt className="text-muted-foreground">Result</dt><dd>{label[check.status]}</dd>
              <dt className="text-muted-foreground">Duration</dt><dd className="tabular">{configured ? `${check.latency_ms.toLocaleString("en-US")} ms` : "No request made"}</dd>
              <dt className="text-muted-foreground">Detail</dt><dd>{check.detail}</dd>
              {breaker && <><dt className="text-muted-foreground">Circuit breaker</dt><dd>{breaker.open ? "Open, requests paused" : "Closed"} · {breaker.failures} recent failure{breaker.failures === 1 ? "" : "s"}</dd></>}
            </dl>
            <p className="mt-2 text-xs text-muted-foreground">Earlier checks aren&apos;t stored yet, so only the current one is shown.</p>
          </td>
        </tr>
      )}
    </>
  );
}

function SandboxProofs() {
  const session = useSession();
  const x402Proof = useQuery({ queryKey: ["x402-proof"], queryFn: () => api<X402Proof>("/v1/sandbox/x402-proof") });
  const crsProof = useQuery({ queryKey: ["crs-proof"], queryFn: () => api<CrsProof>("/v1/sandbox/crs-proof"), staleTime: 5 * 60_000 });
  const [paying, setPaying] = useState(false);
  const [payError, setPayError] = useState<string | null>(null);
  const runPayment = async () => {
    setPaying(true); setPayError(null);
    try { await api<X402Proof>("/v1/sandbox/x402-proof", { method: "POST", token: session?.token }); await x402Proof.refetch(); }
    catch (error) { setPayError(error instanceof Error ? error.message : "Payment failed"); }
    finally { setPaying(false); }
  };
  const outcome = { verified: "Verified", flagged: "Flagged", unavailable: "Unavailable", not_configured: "Not configured" } as const;
  return (
    <>
      <section aria-label="Sponsor sandbox proof" className="mt-12">
        <h2 className="text-base font-semibold">{crsProof.data?.provider ?? "CRS Credit API sandbox"} <Provenance className="ml-1" value="SANDBOX" /></h2>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{crsProof.data?.notice ?? "Live identity check on CRS-published test identities."}</p>
        {crsProof.isLoading && <p className="mt-3 text-sm text-muted-foreground">Running the CRS sandbox check…</p>}
        {crsProof.isError && <p className="mt-3 text-sm text-critical">CRS sandbox check failed: {crsProof.error.message}</p>}
        <ul className="mt-2">
          {crsProof.data?.results.map((row) => (
            <li key={row.persona_id} className="grid gap-x-4 gap-y-0.5 border-b py-2.5 text-sm sm:grid-cols-[260px_160px_1fr]">
              <span className="font-medium">Test identity {row.persona_id} <span className="font-normal text-muted-foreground">{row.test_identity}</span></span>
              <StatusText tone={row.outcome === "verified" ? "neutral" : row.outcome === "flagged" ? "warn" : row.outcome === "not_configured" ? "muted" : "critical"} value={row.outcome}>{outcome[row.outcome]}{row.expected && row.outcome === row.expected ? " · as expected" : ""}</StatusText>
              <span className="text-muted-foreground">{row.messages.length ? row.messages.map((m) => `${m.code}: ${m.text}`).join("; ") : row.error ?? (row.outcome === "verified" ? "Name, SSN, DOB and address belong together; no fraud flags" : "")}</span>
            </li>
          ))}
        </ul>
      </section>
      <section aria-label="Devnet payment proof" className="mt-10">
        <h2 className="text-base font-semibold">Coinbase x402 on Solana devnet <Provenance className="ml-1" value="SANDBOX" /> <span className="ml-1 text-xs font-medium tracking-wide text-muted-foreground">DEVNET · TEST PAYMENT</span></h2>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{x402Proof.data?.notice ?? "HTTP 402 → signed USDC transfer → facilitator settlement on Solana devnet."}</p>
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
          {session ? <Button variant="secondary" size="sm" disabled={paying} onClick={() => void runPayment()}>{paying ? "Paying over HTTP 402…" : "Run a devnet x402 payment"}</Button>
            : <Link className="font-medium hover:underline" href="/sign-in">Sign in to run a devnet payment →</Link>}
          {x402Proof.data?.proof ? (
            <span className="text-muted-foreground">Last settled {ago(x402Proof.data.proof.created_at)}: {x402Proof.data.proof.amount_display} · {x402Proof.data.proof.payer.slice(0, 6)}… → {x402Proof.data.proof.pay_to.slice(0, 6)}… · <a className="font-medium text-foreground hover:underline" href={x402Proof.data.proof.explorer_url} target="_blank" rel="noreferrer"><span className="font-mono text-xs">tx {x402Proof.data.proof.transaction.slice(0, 16)}…</span> →</a></span>
          ) : <span className="text-muted-foreground">No devnet payment run on this deployment yet.</span>}
        </div>
        {payError && <p className="mt-2 text-sm text-critical">{payError}</p>}
      </section>
    </>
  );
}

// Public page. The island shows the marketing tabs when logged out and the coordinator tabs when logged in.
export default function StatusPage() {
  const [refresh, setRefresh] = useState(0);
  const status = useQuery({ queryKey: ["integration-status", refresh > 0], queryFn: () => api<StatusPayload>(`/v1/integrations/status${refresh ? "?refresh=true" : ""}`), refetchInterval: 60_000 });
  const checks = status.data?.integrations ?? [];
  const operational = checks.filter((check) => check.status === "ok").length;
  const recheck = () => { setRefresh((value) => value + 1); if (refresh > 0) void status.refetch(); };
  const summary = status.data && (
    <>
      {operational} of {checks.length} integrations operational · checked {clock(status.data.checked_at)} ·{" "}
      <button type="button" className="font-medium text-foreground hover:underline disabled:text-muted-foreground" disabled={status.isFetching} onClick={recheck}>{status.isFetching ? "Checking…" : "Re-check now"}</button>
    </>
  );
  return (
    <Page>
      <PageHeader title="System status" meta={summary} />
      <p className="mt-2 max-w-3xl text-sm text-muted-foreground">Each row is a real request the API made just now (cached for 60 s). &ldquo;Operational&rdquo; appears only when that request succeeded. API: <span className="font-mono text-xs">{API_BASE_URL}</span></p>
      {status.isError && <p role="alert" className="mt-6 text-sm text-critical">The ReliefMesh API is unreachable: {status.error.message} <button type="button" className="font-medium text-foreground hover:underline" onClick={() => void status.refetch()}>Retry</button></p>}
      {status.isLoading && <div className="mt-8 space-y-3" aria-label="Running live checks">{[0, 1, 2, 3].map((key) => <div key={key} className="h-5 animate-pulse rounded bg-muted motion-reduce:animate-none" />)}</div>}
      {groups.map(([category, title]) => {
        const rows = checks.filter((check) => check.category === category);
        if (rows.length === 0) return null;
        return (
          <section key={category} aria-label={title} className="mt-10">
            <h2 className="text-xl font-semibold">{title}</h2>
            <div className="mt-2">
              <Table>
                <thead><tr className="border-b"><th className={`${head} w-[22%]`}>Integration</th><th className={`${head} w-[14%]`}>Status</th><th className={`${head} w-[14%]`}>Provenance</th><th className={head}>Detail</th><th className={`${head} w-[10%]`}>Current</th></tr></thead>
                <tbody>{rows.map((check) => <Fragment key={check.id}><CheckRow check={check} breaker={status.data?.breakers?.[check.id]} /></Fragment>)}</tbody>
              </Table>
            </div>
          </section>
        );
      })}
      <SandboxProofs />
      {status.data && <p className="mt-10 text-xs text-muted-foreground">Environment {status.data.environment} · checked {ago(status.data.checked_at)}</p>}
    </Page>
  );
}
