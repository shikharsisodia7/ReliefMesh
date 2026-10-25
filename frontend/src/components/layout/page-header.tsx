import Link from "next/link";
import { Fragment, type ReactNode } from "react";

import { cn } from "@/lib/utils";

// The island and page content share this width so their edges line up.
export const pageWidth = "mx-auto w-full max-w-[1132px] px-4";

export function Page({ className, children }: { className?: string; children: ReactNode }) {
  return <main className={cn(pageWidth, "pt-10 pb-16", className)}>{children}</main>;
}

type Crumb = { label: string; href?: string };

// Breadcrumb → title → one meta line → optional gray activity line; actions sit on the right.
export function PageHeader({ breadcrumb, title, meta, activity, actions }: { breadcrumb?: Crumb[]; title: ReactNode; meta?: ReactNode; activity?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
      <div className="min-w-0">
        {breadcrumb && breadcrumb.length > 0 && (
          <nav aria-label="Breadcrumb" className="mb-2 text-xs font-medium text-muted-foreground">
            {breadcrumb.map((crumb, index) => (
              <Fragment key={`${crumb.label}-${index}`}>
                {index > 0 && <span className="mx-1.5">/</span>}
                {crumb.href ? <Link className="hover:text-foreground" href={crumb.href}>{crumb.label}</Link> : <span>{crumb.label}</span>}
              </Fragment>
            ))}
          </nav>
        )}
        <h1 className="text-[28px] leading-tight font-semibold tracking-tight">{title}</h1>
        {meta && <p className="mt-1.5 text-sm text-muted-foreground">{meta}</p>}
        {activity && <p className="mt-1 text-sm text-muted-foreground">{activity}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </header>
  );
}
