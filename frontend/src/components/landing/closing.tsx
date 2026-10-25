import Link from "next/link";

import { DotWordmark } from "@/components/landing/dot-wordmark";

type FooterLink = { label: string; href: string };

const AGENT = "agent1qwsexvyvdavc0pjys60fgh7mev3d6xccnqfjg9famyqvnxrw4eajsxs243x";

// Devpost has no published project URL yet, so it is left out rather than linked to a guess.
const columns: { title: string; links: FooterLink[] }[] = [
  { title: "Product", links: [{ label: "How it works", href: "#how-it-works" }, { label: "System Status", href: "/status" }, { label: "Supplier portal", href: "/sign-up?role=supplier" }] },
  { title: "Project", links: [{ label: "GitHub", href: "https://github.com/shikharsisodia7/calhacks" }, { label: "Fetch.ai agent on Agentverse", href: `https://agentverse.ai/agents/details/${AGENT}/profile` }] },
  {
    title: "Data",
    links: [
      { label: "NASA EONET", href: "https://eonet.gsfc.nasa.gov/" },
      { label: "NWS", href: "https://www.weather.gov/documentation/services-web-api" },
      { label: "NASA FIRMS", href: "https://firms.modaps.eosdis.nasa.gov/" },
      { label: "OpenFEMA", href: "https://www.fema.gov/about/openfema" },
      { label: "OFAC", href: "https://ofac.treasury.gov/sanctions-list-service" },
      { label: "openFDA", href: "https://open.fda.gov/" },
      { label: "USAspending", href: "https://www.usaspending.gov/" },
      { label: "SAM.gov", href: "https://sam.gov/" },
    ],
  },
  {
    title: "Sponsors",
    links: [
      { label: "Fetch.ai", href: "https://fetch.ai/" },
      { label: "CRS", href: "https://crscreditapi.com/" },
      { label: "Apify", href: "https://apify.com/" },
      { label: "Coinbase x402", href: "https://www.x402.org/" },
      { label: "Solana", href: "https://solana.com/" },
    ],
  },
];

function FooterAnchor({ link }: { link: FooterLink }) {
  const className = "text-base text-ink hover:underline md:text-lg";
  if (link.href.startsWith("http")) return <a className={className} href={link.href} target="_blank" rel="noreferrer">{link.label}</a>;
  return <Link className={className} href={link.href}>{link.label}</Link>;
}

export function Closing() {
  return (
    <footer className="overflow-hidden bg-signal text-ink">
      <div className="mx-auto max-w-[1376px] px-4 pt-20 md:px-8 md:pt-24">
        <div className="flex flex-col gap-8 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h2 className="text-[38px] leading-[1.02] font-bold tracking-[-0.035em] md:text-[56px]">AI explains. It never approves.</h2>
            <p className="mt-4 text-lg md:text-xl">Rules decide eligibility. Math allocates. People authorize spending.</p>
          </div>
          <Link href="/sign-up" className="inline-flex h-14 shrink-0 items-center self-start rounded-md bg-ink px-10 text-lg font-semibold text-white outline-hidden hover:bg-ink/90 focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-2 focus-visible:outline-ink">Start a mission</Link>
        </div>
        <nav aria-label="Footer" className="mt-16 grid grid-cols-1 gap-10 sm:grid-cols-2 lg:grid-cols-4">
          {columns.map((column) => (
            <div key={column.title}>
              <h3 className="text-base font-bold md:text-lg">{column.title}</h3>
              <ul className="mt-4 space-y-2">{column.links.map((link) => <li key={link.label}><FooterAnchor link={link} /></li>)}</ul>
            </div>
          ))}
        </nav>
        <p className="mt-12 text-right text-sm">Built at Cal Hacks 13.0</p>
      </div>
      <div className="mx-auto mt-3 max-w-[1440px] px-2">
        <DotWordmark className="block h-auto w-full text-ink" />
      </div>
      <div className="border-t border-ink/25">
        <div className="mx-auto flex max-w-[1376px] gap-6 px-4 py-4 text-xs md:px-8">
          <Link className="hover:underline" href="/privacy">Privacy</Link>
          <Link className="hover:underline" href="/terms">Terms</Link>
        </div>
      </div>
    </footer>
  );
}
