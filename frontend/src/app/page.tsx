import Link from "next/link";
import { ArrowRight, Radar, Scale, ShieldCheck, Workflow } from "lucide-react";

const pillars = [
  { icon: Radar, title: "Real evidence", body: "NASA EONET, NWS, FIRMS, and OpenFEMA frame the emergency. OFAC, SAM.gov, openFDA, and USAspending screen every supplier, with provenance on every record." },
  { icon: Scale, title: "Deterministic policy", body: "Rules, not a language model, decide eligibility. Missing screening is never a pass, and a fuzzy sanctions match always goes to a human." },
  { icon: Workflow, title: "Mathematical allocation", body: "A mixed-integer solver splits the buy across real supplier quotes under budget, inventory, deadline, and concentration constraints." },
  { icon: ShieldCheck, title: "Autonomous recovery", body: "When a supplier withdraws, cuts stock, or gets blocked, the plan goes stale, approval is revoked, and a new plan is computed for human sign-off." },
];

export default function Home() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <section className="mx-auto flex min-h-screen max-w-6xl flex-col px-6 py-8 lg:px-10">
        <header className="flex items-center justify-between">
          <span className="font-mono text-sm font-bold tracking-[0.2em]">RELIEF<span className="text-live">MESH</span></span>
          <div className="flex gap-2 text-sm"><Link className="rounded-lg px-3 py-2 text-muted-foreground hover:text-foreground" href="/status">System status</Link><Link className="rounded-lg px-3 py-2 font-medium hover:bg-secondary" href="/sign-in">Sign in</Link><Link className="rounded-lg bg-primary px-3 py-2 font-medium text-primary-foreground hover:bg-primary/85" href="/sign-up">Create account</Link></div>
        </header>
        <div className="grid flex-1 items-center gap-12 py-16 lg:grid-cols-[1.15fr_.85fr]">
          <div>
            <p className="mb-5 font-mono text-xs font-medium tracking-[.22em] text-live">EMERGENCY PROCUREMENT THAT RECOVERS</p>
            <h1 className="max-w-3xl text-5xl font-semibold tracking-tight sm:text-6xl">An evidence-backed procurement network that rebuilds its own plan when the supply chain changes.</h1>
            <p className="mt-7 max-w-xl text-lg leading-8 text-muted-foreground">Real supplier quotes, real public-record evidence, deterministic policy, and integer optimization, with a human holding the purchasing authority. The AI orchestrates and explains. It never approves.</p>
            <div className="mt-9 flex flex-wrap gap-3"><Link className="inline-flex h-10 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/85" href="/sign-up">Start a procurement mission <ArrowRight className="size-4" /></Link><Link className="inline-flex h-10 items-center rounded-lg border px-4 text-sm font-medium hover:bg-secondary" href="/sign-up?role=supplier">Supplier portal</Link></div>
          </div>
          <div className="grid gap-3">
            {pillars.map(({ icon: Icon, title, body }) => (
              <div key={title} className="rounded-xl border bg-card/90 p-4"><Icon className="mb-2 size-5 text-telemetry" /><h2 className="font-semibold">{title}</h2><p className="mt-1 text-sm text-muted-foreground">{body}</p></div>
            ))}
          </div>
        </div>
        <footer className="flex gap-4 border-t pt-5 text-xs text-muted-foreground"><Link className="hover:text-foreground" href="/privacy">Privacy policy</Link><Link className="hover:text-foreground" href="/terms">Terms of service</Link><Link className="hover:text-foreground" href="/status">System status</Link></footer>
      </section>
    </main>
  );
}
