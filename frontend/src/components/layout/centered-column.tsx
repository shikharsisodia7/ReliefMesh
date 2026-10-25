import Link from "next/link";
import type { ReactNode } from "react";

// Sign in, sign up, and join: a centered 400px column on white with the wordmark, title, and one primary action.
export function CenteredColumn({ title, subtitle, children }: { title: ReactNode; subtitle?: ReactNode; children: ReactNode }) {
  return (
    <main className="grid min-h-screen place-items-center bg-background px-4 py-12">
      <div className="w-full max-w-[400px]">
        <Link href="/" className="text-lg font-semibold tracking-tight">ReliefMesh</Link>
        <h1 className="mt-10 text-[28px] leading-tight font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-2 text-sm text-muted-foreground">{subtitle}</p>}
        <div className="mt-8">{children}</div>
      </div>
    </main>
  );
}
