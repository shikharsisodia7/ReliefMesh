"use client";

import { Menu } from "@base-ui/react/menu";
import { Check, Menu as MenuGlyph } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useLayoutEffect, useRef, useState, type ReactNode } from "react";

import { DotWordmark } from "@/components/landing/dot-wordmark";
import { pageWidth } from "@/components/layout/page-header";
import { Drawer } from "@/components/patterns/overlays";
import { Button, buttonVariants } from "@/components/ui/button";
import { useOrganizations } from "@/hooks/use-organizations";
import { useHydrated, useSession } from "@/hooks/use-session";
import { clearSession, type SessionUser } from "@/lib/session";
import { cn } from "@/lib/utils";

type Tab = { label: string; href: string; active: (path: string, tab: string | null) => boolean };
type Session = { token: string; user: SessionUser };

const coordinatorTabs: Tab[] = [
  { label: "Missions", href: "/dashboard", active: (path) => path === "/dashboard" || path.startsWith("/missions/") },
  { label: "Suppliers", href: "/suppliers", active: (path) => path === "/suppliers" },
  { label: "Analytics", href: "/analytics", active: (path) => path === "/analytics" },
  { label: "System Status", href: "/status", active: (path) => path === "/status" },
];
const supplierTabs: Tab[] = [
  { label: "RFQs", href: "/supplier?tab=rfqs", active: (path, tab) => path.startsWith("/invitations/") || (path === "/supplier" && (tab ?? "rfqs") === "rfqs") },
  { label: "My Quotes", href: "/supplier?tab=quotes", active: (path, tab) => path === "/supplier" && tab === "quotes" },
  { label: "Purchase Orders", href: "/supplier?tab=orders", active: (path, tab) => path === "/supplier" && tab === "orders" },
  { label: "Settings", href: "/supplier?tab=settings", active: (path, tab) => path === "/supplier" && tab === "settings" },
];
const marketingTabs: Tab[] = [
  { label: "How it works", href: "/#how-it-works", active: () => false },
  { label: "Judge guide", href: "/judge", active: (path) => path === "/judge" },
  { label: "System Status", href: "/status", active: (path) => path === "/status" },
];

const roleWords: Record<string, string> = { admin: "Administrator", approver: "Approver", coordinator: "Coordinator" };

// Sign-in, sign-up, and join are a bare centered column without the island.
const bare = (path: string) => path === "/sign-in" || path === "/sign-up" || path.startsWith("/join/");

function initials(email?: string) {
  const local = (email ?? "").split("@")[0];
  const words = local.split(/[._+-]/).filter((word) => /^[a-z]/i.test(word));
  return (words.slice(0, 2).map((word) => word[0]).join("") || local.slice(0, 1) || "?").toUpperCase();
}

function signOut(router: ReturnType<typeof useRouter>) {
  clearSession();
  router.push("/");
}

// Lives in the root layout so it stays mounted and the underline can slide between pages.
export function AppHeader() {
  return <Suspense fallback={<Frame />}><Island /></Suspense>;
}

function Island() {
  const pathname = usePathname();
  const tab = useSearchParams().get("tab");
  const session = useSession();
  const hydrated = useHydrated();
  if (bare(pathname)) return null;
  // The session is only known in the browser; render an empty island until then.
  if (!hydrated) return <Frame />;
  const role = session?.user.role;
  const tabs = role === "coordinator" ? coordinatorTabs : role === "supplier" ? supplierTabs : marketingTabs;
  return (
    <Frame
      nav={<TabNav key={role ?? "public"} tabs={tabs} pathname={pathname} tab={tab} />}
      actions={session ? <AccountMenu session={session} /> : <MarketingActions />}
      mobile={<MobileMenu tabs={tabs} pathname={pathname} tab={tab} session={session} />}
    />
  );
}

function Frame({ nav, actions, mobile }: { nav?: ReactNode; actions?: ReactNode; mobile?: ReactNode }) {
  return (
    <div className="sticky top-4 z-40 mt-4">
      <div className={pageWidth}>
        <header className="grid h-14 grid-cols-[1fr_auto] items-center rounded-xl border bg-background px-6 shadow-[0_2px_12px_rgb(32_33_36/0.08)] md:grid-cols-[1fr_auto_1fr]">
          {/* The brand mark always returns to the marketing landing page, regardless of sign-in state. */}
          <Link href="/" className="justify-self-start text-ink" aria-label="ReliefMesh home">
            <DotWordmark density="compact" className="block h-9 w-auto" />
          </Link>
          <div className="hidden self-stretch md:block">{nav}</div>
          <div className="hidden items-center justify-end gap-4 md:flex">{actions}</div>
          <div className="justify-self-end md:hidden">{mobile}</div>
        </header>
      </div>
    </div>
  );
}

function TabNav({ tabs, pathname, tab }: { tabs: Tab[]; pathname: string; tab: string | null }) {
  const listRef = useRef<HTMLElement>(null);
  const barRef = useRef<HTMLSpanElement>(null);
  const activeIndex = tabs.findIndex((item) => item.active(pathname, tab));
  useLayoutEffect(() => {
    const list = listRef.current;
    const bar = barRef.current;
    if (!list || !bar) return;
    const measure = () => {
      const active = list.querySelector<HTMLElement>('[aria-current="page"]');
      bar.style.opacity = active ? "1" : "0";
      if (active) {
        bar.style.width = `${active.offsetWidth}px`;
        bar.style.transform = `translateX(${active.offsetLeft}px)`;
      }
    };
    measure();
    // Turn the transition on after the first placement, so the bar doesn't sweep in on load.
    const frame = requestAnimationFrame(() => { bar.dataset.ready = "true"; });
    // Re-measure whenever the tabs' layout changes (fonts loading, resizes, tabs added).
    const observer = new ResizeObserver(measure);
    observer.observe(list);
    void document.fonts?.ready.then(measure);
    return () => { cancelAnimationFrame(frame); observer.disconnect(); };
  }, [activeIndex]);
  return (
    <nav ref={listRef} aria-label="Main" className="relative flex h-full items-center gap-8">
      {tabs.map((item, index) => (
        <Link
          key={item.href}
          href={item.href}
          aria-current={index === activeIndex ? "page" : undefined}
          className="flex h-full items-center text-sm font-medium whitespace-nowrap text-muted-foreground transition-colors hover:text-foreground aria-[current=page]:text-foreground"
        >
          {item.label}
        </Link>
      ))}
      <span ref={barRef} aria-hidden className="absolute bottom-0 left-0 h-0.5 bg-foreground opacity-0 data-[ready=true]:motion-safe:transition-[transform,width] data-[ready=true]:motion-safe:duration-200 data-[ready=true]:motion-safe:ease-out" />
    </nav>
  );
}

function MarketingActions() {
  return (
    <>
      <Link href="/sign-in" className="text-sm font-medium text-foreground hover:underline">Sign in</Link>
      <Link href="/sign-up" className={buttonVariants({ size: "sm" })}>Start a mission</Link>
    </>
  );
}

const itemClass = "flex w-full cursor-default items-center gap-2 px-3 py-2 text-left text-sm text-foreground outline-hidden select-none data-[highlighted]:bg-muted";

function AccountMenu({ session }: { session: Session }) {
  const router = useRouter();
  const coordinator = session.user.role === "coordinator";
  const { organizations, current, select } = useOrganizations(coordinator ? session.token : undefined);
  const rows = organizations.data ?? [];
  return (
    <Menu.Root>
      <Menu.Trigger aria-label={`Account menu, ${initials(session.user.email)}`} className="grid size-9 place-items-center rounded-full border text-xs font-semibold text-foreground outline-hidden hover:bg-muted focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-2 focus-visible:outline-ring data-[popup-open]:bg-muted">
        {initials(session.user.email)}
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Positioner align="end" sideOffset={10} className="z-50">
          <Menu.Popup className="w-80 rounded-lg border bg-background py-1.5 shadow-lg outline-hidden transition-opacity duration-150 data-[ending-style]:opacity-0 data-[starting-style]:opacity-0 motion-reduce:transition-none">
            <div className="px-3 py-2">
              <p className="truncate text-sm font-medium">{session.user.email}</p>
              <p className="text-xs text-muted-foreground">{coordinator ? "Coordinator" : "Supplier"}{current ? ` · ${roleWords[current.membership_role] ?? current.membership_role}` : ""}</p>
            </div>
            {rows.length > 0 && (
              <>
                <Menu.Separator className="my-1.5 h-px bg-border" />
                <Menu.Group>
                  <Menu.GroupLabel className="px-3 pt-1 pb-1.5 text-xs font-medium text-muted-foreground">Organization</Menu.GroupLabel>
                  <Menu.RadioGroup value={current?.id ?? ""} onValueChange={(value) => select(String(value))}>
                    {rows.map((row) => (
                      <Menu.RadioItem key={row.id} value={row.id} className={itemClass}>
                        <span className="min-w-0 flex-1 truncate">{row.name}{row.is_demo && <span className="ml-2 text-xs text-muted-foreground">DEMO ORG</span>}</span>
                        <Menu.RadioItemIndicator><Check className="size-4" /></Menu.RadioItemIndicator>
                      </Menu.RadioItem>
                    ))}
                  </Menu.RadioGroup>
                </Menu.Group>
              </>
            )}
            <Menu.Separator className="my-1.5 h-px bg-border" />
            {/* The island stays mounted across pages, so the menu must close itself on navigation. */}
            <Menu.LinkItem closeOnClick render={<Link href={coordinator ? "/settings" : "/supplier?tab=settings"} />} className={itemClass}>Settings</Menu.LinkItem>
            {/* Coordinators reach the judge guide here; logged-out visitors see it as a marketing tab. */}
            {coordinator && <Menu.LinkItem closeOnClick render={<Link href="/judge" />} className={itemClass}>Judge guide</Menu.LinkItem>}
            <Menu.Item className={itemClass} onClick={() => signOut(router)}>Sign out</Menu.Item>
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
  );
}

// Under 768px the island is the wordmark plus this button, which opens a full-screen sheet.
function MobileMenu({ tabs, pathname, tab, session }: { tabs: Tab[]; pathname: string; tab: string | null; session: Session | null }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const coordinator = session?.user.role === "coordinator";
  const { organizations, current, select } = useOrganizations(coordinator ? session?.token : undefined);
  const close = () => setOpen(false);
  const row = "flex h-11 w-full items-center text-left text-base";
  return (
    <>
      <Button variant="text" size="icon" aria-label="Open menu" onClick={() => setOpen(true)}><MenuGlyph /></Button>
      <Drawer open={open} onOpenChange={setOpen} title="ReliefMesh" subtitle={session?.user.email}>
        <nav aria-label="Main" className="border-b pb-3">
          {tabs.map((item) => (
            <Link key={item.href} href={item.href} onClick={close} aria-current={item.active(pathname, tab) ? "page" : undefined} className={cn(row, "text-muted-foreground aria-[current=page]:font-medium aria-[current=page]:text-foreground")}>{item.label}</Link>
          ))}
        </nav>
        {session ? (
          <div className="pt-3">
            {(organizations.data?.length ?? 0) > 0 && (
              <div role="group" aria-label="Organization" className="border-b pb-3">
                <p className="pb-1 text-xs font-medium text-muted-foreground">Organization</p>
                {organizations.data!.map((org) => (
                  <button key={org.id} type="button" aria-pressed={org.id === current?.id} onClick={() => select(org.id)} className={cn(row, "justify-between")}>
                    <span className="truncate">{org.name}{org.is_demo && <span className="ml-2 text-xs text-muted-foreground">DEMO ORG</span>}</span>
                    {org.id === current?.id && <Check className="size-4" />}
                  </button>
                ))}
              </div>
            )}
            <Link href={coordinator ? "/settings" : "/supplier?tab=settings"} onClick={close} className={row}>Settings</Link>
            {coordinator && <Link href="/judge" onClick={close} className={row}>Judge guide</Link>}
            <button type="button" className={row} onClick={() => { close(); signOut(router); }}>Sign out</button>
          </div>
        ) : (
          <div className="flex flex-col gap-3 pt-4">
            <Link href="/sign-in" onClick={close} className={buttonVariants({ variant: "secondary" })}>Sign in</Link>
            <Link href="/sign-up" onClick={close} className={buttonVariants()}>Start a mission</Link>
          </div>
        )}
      </Drawer>
    </>
  );
}
