import Link from "next/link";
import { ArrowRight, ShieldCheck, Workflow } from "lucide-react";

export default function Home() {
  return (
    <main className="min-h-screen bg-slate-950 text-slate-50">
      <section className="mx-auto flex min-h-screen max-w-6xl flex-col px-6 py-8 lg:px-10">
        <header className="flex items-center justify-between">
          <span className="text-lg font-semibold tracking-tight">RELIEFMESH</span>
          <div className="flex gap-3"><Link className="rounded-lg px-3 py-2 text-sm font-medium hover:bg-slate-800" href="/sign-in">Sign in</Link><Link className="rounded-lg bg-white px-3 py-2 text-sm font-medium text-slate-950 hover:bg-slate-200" href="/sign-up">Create account</Link></div>
        </header>
        <div className="grid flex-1 items-center gap-12 py-20 lg:grid-cols-[1.2fr_.8fr]">
          <div>
            <p className="mb-5 text-sm font-medium tracking-[.18em] text-cyan-300">EMERGENCY PROCUREMENT, BUILT TO RECOVER</p>
            <h1 className="max-w-3xl text-5xl font-semibold tracking-tight sm:text-7xl">Supply plans that adapt when reality changes.</h1>
            <p className="mt-7 max-w-xl text-lg leading-8 text-slate-300">Coordinate supplier RFQs, calculate a defensible allocation, and replan automatically when a quote changes—without bypassing human approval.</p>
            <div className="mt-9 flex flex-wrap gap-3"><Link className="inline-flex h-10 items-center gap-2 rounded-lg bg-white px-4 text-sm font-medium text-slate-950 hover:bg-slate-200" href="/sign-up">Start a procurement mission <ArrowRight className="size-4" /></Link><Link className="inline-flex h-10 items-center rounded-lg border border-slate-600 px-4 text-sm font-medium hover:bg-slate-800" href="/supplier">Supplier portal</Link></div>
          </div>
          <div className="grid gap-4 rounded-2xl border border-slate-700 bg-slate-900/80 p-6 shadow-2xl">
            <div className="rounded-xl border border-slate-700 bg-slate-950 p-5"><Workflow className="mb-4 text-cyan-300" /><h2 className="font-semibold">Deterministic allocation</h2><p className="mt-1 text-sm text-slate-400">Inventory, delivery, budget, and supplier policy constraints are solved from submitted quotes.</p></div>
            <div className="rounded-xl border border-slate-700 bg-slate-950 p-5"><ShieldCheck className="mb-4 text-cyan-300" /><h2 className="font-semibold">Approval stays human</h2><p className="mt-1 text-sm text-slate-400">A disrupted plan becomes stale. Its prior approval cannot be used to issue a purchase order.</p></div>
          </div>
        </div>
      </section>
    </main>
  );
}
