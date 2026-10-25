"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useOrgMissions, usePerMission } from "@/components/coordinator/use-org-records";
import { Page, PageHeader } from "@/components/layout/page-header";
import { EVIDENCE_ORDER, checkLabel, resultWords } from "@/components/mission/supplier-evidence";
import { Drawer } from "@/components/patterns/overlays";
import { PolicyText, Provenance, day, money, when } from "@/components/status-badges";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useHydrated, useSession } from "@/hooks/use-session";
import { signInUrl } from "@/lib/session";
import type { Evidence, Mission, Quote, SupplierRow } from "@/lib/types";

type Entry = { mission: Mission; row: SupplierRow; quote?: Quote };
type Supplier = { id: string; name: string; email?: string; isDemo: boolean; entries: Entry[]; screened: string | null };

const latestTime = (records: Evidence[]) => records.map((record) => record.retrieved_at ?? record.created_at).filter(Boolean).sort().at(-1) ?? null;
const quoteText = (quote?: Quote) => (quote ? `${quote.lines.map((line) => `${line.available_quantity} @ ${money(line.unit_price)}`).join(", ")} · v${quote.version}` : "—");

// Groups each mission's supplier rows by supplier. Missions arrive newest first, so entries[0] is the latest.
function bySupplier(rows: [Mission, SupplierRow[]][], quotes: Map<string, Quote[]>) {
  const suppliers = new Map<string, Supplier>();
  for (const [mission, missionRows] of rows) {
    for (const row of missionRows) {
      const id = row.supplier.id;
      const entry: Entry = { mission, row, quote: quotes.get(mission.id)?.filter((quote) => quote.supplier_id === id).sort((a, b) => b.version - a.version)[0] };
      const supplier = suppliers.get(id) ?? { id, name: row.supplier.legal_name || row.supplier.email || id.slice(0, 8), email: row.supplier.email, isDemo: Boolean(row.supplier.is_demo), entries: [], screened: null };
      supplier.entries.push(entry);
      const screened = latestTime(Object.values(row.latest_evidence));
      if (screened && (!supplier.screened || screened > supplier.screened)) supplier.screened = screened;
      suppliers.set(id, supplier);
    }
  }
  return [...suppliers.values()].sort((a, b) => a.name.localeCompare(b.name));
}

function SupplierDrawer({ supplier, onClose }: { supplier: Supplier | null; onClose: () => void }) {
  const latest = supplier?.entries[0];
  const checks = latest ? EVIDENCE_ORDER.map(([type]) => latest.row.latest_evidence[type]).filter(Boolean) : [];
  return (
    <Drawer open={supplier !== null} onOpenChange={(open) => { if (!open) onClose(); }} title={supplier?.name ?? "Supplier"} subtitle={supplier ? [supplier.email, supplier.isDemo ? "TEST supplier" : null].filter(Boolean).join(" · ") : undefined} label="Supplier detail">
      {supplier && latest && (
        <>
          <section>
            <h3 className="text-sm font-semibold">Missions</h3>
            <ul className="mt-2">
              {supplier.entries.map(({ mission, row, quote }) => (
                <li key={mission.id} className="border-b py-2.5 text-sm last:border-0">
                  <div className="flex items-baseline justify-between gap-3"><span className="font-medium">{mission.name}</span><PolicyText value={row.policy.status} /></div>
                  <p className="mt-0.5 text-muted-foreground tabular">{quoteText(quote)}{quote ? ` · ${quote.status.charAt(0).toUpperCase()}${quote.status.slice(1)}` : ""}</p>
                  <Link className="mt-1 inline-block font-medium hover:underline" href={`/missions/${mission.id}?tab=evidence`}>Open evidence →</Link>
                </li>
              ))}
            </ul>
          </section>
          <section className="mt-8">
            <h3 className="text-sm font-semibold">Latest checks <span className="font-normal text-muted-foreground">· {latest.mission.name}</span></h3>
            {checks.length === 0 ? <p className="mt-2 text-sm text-muted-foreground">No evidence checks on record yet.</p> : (
              <ul className="mt-2">
                {checks.map((record) => (
                  <li key={record.id} className="flex items-baseline justify-between gap-3 border-b py-2 text-sm last:border-0">
                    <span>{checkLabel(record.type)} · {resultWords(record)}</span>
                    <span className="text-right whitespace-nowrap"><Provenance value={record.provenance} at={record.retrieved_at} /></span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </Drawer>
  );
}

export default function SuppliersPage() {
  const router = useRouter();
  const session = useSession();
  const hydrated = useHydrated();
  useEffect(() => { if (hydrated && (!session || session.user.role !== "coordinator")) router.replace(signInUrl()); }, [hydrated, router, session]);
  const { current, missions } = useOrgMissions(session?.token);
  const supplierRows = usePerMission<SupplierRow>(session?.token, missions.data, "suppliers");
  const quoteRows = usePerMission<Quote>(session?.token, missions.data, "quotes");
  const [open, setOpen] = useState<Supplier | null>(null);
  const suppliers = bySupplier(supplierRows.rows, new Map(quoteRows.rows.map(([mission, quotes]) => [mission.id, quotes])));
  const loading = missions.isLoading || supplierRows.loading;
  const error = missions.error ?? supplierRows.error;
  return (
    <Page>
      <PageHeader title="Suppliers" meta={current ? <>{current.name}{current.is_demo && " · DEMO ORG"} · suppliers across this organization&apos;s missions</> : undefined} />
      <div className="mt-10">
        {error ? <p className="text-sm text-critical">{error.message}</p>
          : loading ? <div className="space-y-3" aria-label="Loading suppliers">{[0, 1, 2].map((key) => <div key={key} className="h-5 animate-pulse rounded bg-muted motion-reduce:animate-none" />)}</div>
            : suppliers.length === 0 ? <p className="text-sm text-muted-foreground">No suppliers yet. They appear here once they quote on one of your missions. <Link className="font-medium text-foreground hover:underline" href="/dashboard">Missions →</Link></p>
              : (
                <Table>
                  <TableHeader><TableRow><TableHead>Supplier</TableHead><TableHead>Missions</TableHead><TableHead>Last quote</TableHead><TableHead>Verdict</TableHead><TableHead className="text-right">Last screened</TableHead></TableRow></TableHeader>
                  <TableBody>
                    {suppliers.map((supplier) => (
                      <TableRow key={supplier.id} className="cursor-pointer" onClick={() => setOpen(supplier)}>
                        <TableCell className="whitespace-normal">
                          <button type="button" className="text-left font-medium outline-hidden hover:underline focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring" onClick={(event) => { event.stopPropagation(); setOpen(supplier); }}>{supplier.name}</button>
                          {supplier.isDemo && <span className="ml-2 text-xs text-muted-foreground">TEST</span>}
                        </TableCell>
                        <TableCell className="whitespace-normal text-muted-foreground">{supplier.entries.map((entry) => entry.mission.name).join(", ")}</TableCell>
                        <TableCell className="tabular">{quoteText(supplier.entries[0].quote)}</TableCell>
                        <TableCell><PolicyText value={supplier.entries[0].row.policy.status} /></TableCell>
                        <TableCell className="text-right tabular" title={supplier.screened ? when(supplier.screened) : undefined}>{supplier.screened ? day(supplier.screened) : "—"}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
        {!loading && !error && suppliers.length > 0 && <p className="mt-4 text-xs text-muted-foreground">Verdict and last quote are from each supplier&apos;s most recent mission. The API doesn&apos;t list suppliers across organizations, so this covers {current?.name ?? "the current organization"} only.</p>}
      </div>
      <SupplierDrawer supplier={open} onClose={() => setOpen(null)} />
    </Page>
  );
}
