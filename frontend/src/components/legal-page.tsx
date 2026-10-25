import Link from "next/link";
import type { ReactNode } from "react";

export const CONTACT_EMAIL = "shikhar35sisodia35@gmail.com";

export function LegalPage({ title, updated, children }: { title: string; updated: string; children: ReactNode }) {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <div className="mx-auto max-w-3xl px-6 py-10">
        <Link href="/" className="font-mono text-sm font-bold tracking-[0.2em]">RELIEF<span className="text-live">MESH</span></Link>
        <h1 className="mt-8 text-3xl font-semibold tracking-tight">{title}</h1>
        <p className="mt-2 text-sm text-muted-foreground">Last updated {updated}</p>
        <div className="mt-8 space-y-6 text-sm leading-7 text-muted-foreground [&_h2]:mb-2 [&_h2]:text-base [&_h2]:font-semibold [&_h2]:text-foreground [&_a]:text-foreground [&_a]:underline [&_ul]:list-disc [&_ul]:pl-5">
          {children}
        </div>
        <p className="mt-10 text-sm text-muted-foreground"><Link href="/privacy">Privacy</Link> · <Link href="/terms">Terms</Link> · <Link href="/status">System status</Link></p>
      </div>
    </main>
  );
}
