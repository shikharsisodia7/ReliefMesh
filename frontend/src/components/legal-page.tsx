import Link from "next/link";
import type { ReactNode } from "react";

export const CONTACT_EMAIL = "shikhar35sisodia35@gmail.com";

// Privacy and Terms: a 680px reading column, 16px body text, plain headings.
export function LegalPage({ title, updated, children }: { title: string; updated: string; children: ReactNode }) {
  return (
    <main className="mx-auto w-full max-w-[680px] px-4 pt-12 pb-20">
      <h1 className="text-[28px] leading-tight font-semibold tracking-tight">{title}</h1>
      <p className="mt-2 text-sm text-muted-foreground">Last updated {updated}</p>
      <div className="mt-10 space-y-8 text-base leading-7 [&_a]:font-medium [&_a]:underline [&_a]:underline-offset-2 [&_h2]:mb-2 [&_h2]:text-lg [&_h2]:font-semibold [&_li]:mt-1 [&_ul]:list-disc [&_ul]:pl-5">
        {children}
      </div>
      <p className="mt-12 border-t pt-6 text-sm text-muted-foreground"><Link className="hover:text-foreground" href="/privacy">Privacy</Link> · <Link className="hover:text-foreground" href="/terms">Terms</Link> · <Link className="hover:text-foreground" href="/status">System Status</Link></p>
    </main>
  );
}
