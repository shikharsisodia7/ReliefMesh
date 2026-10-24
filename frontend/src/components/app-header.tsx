"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { clearSession } from "@/lib/session";

export function AppHeader({ email, home, label }: { email?: string; home: string; label?: string }) {
  const router = useRouter();
  return (
    <header className="sticky top-0 z-40 border-b bg-background/90 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-5 py-3">
        <div className="flex items-center gap-5">
          <Link className="font-mono text-sm font-bold tracking-[0.2em]" href={home}>RELIEF<span className="text-live">MESH</span></Link>
          {label && <span className="hidden text-xs uppercase tracking-[0.16em] text-muted-foreground sm:inline">{label}</span>}
          <nav className="flex items-center gap-3 text-sm text-muted-foreground"><Link className="hover:text-foreground" href={home}>Missions</Link><Link className="hover:text-foreground" href="/status">System status</Link></nav>
        </div>
        <div className="flex items-center gap-3 text-sm">
          {email && <span className="hidden text-muted-foreground md:block">{email}</span>}
          <Button variant="outline" size="sm" onClick={() => { clearSession(); router.push("/"); }}>Sign out</Button>
        </div>
      </div>
    </header>
  );
}
