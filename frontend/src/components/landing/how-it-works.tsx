"use client";

import { Hash, ScrollText, Scale, Sigma } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";

import { cn } from "@/lib/utils";

// The diagram is laid out on a fixed 1312 × 600 canvas and scaled to fit; under 1024px it becomes a vertical flow.
const W = 1312;
const H = 600;

// Motion: edges draw left to right over 1.2 s and the orange path draws last. Times are in ms.
const reveal = (delay: number, duration = 200): CSSProperties => ({ transitionDelay: `${delay}ms`, transitionDuration: `${duration}ms` });
const fade = "opacity-0 transition-opacity ease-out group-data-[drawn=true]:opacity-100 motion-reduce:opacity-100 motion-reduce:transition-none";

function Tile({ children, small = false }: { children: ReactNode; small?: boolean }) {
  return <span className={cn("grid shrink-0 place-items-center rounded-lg border border-sand-border bg-white", small ? "size-7" : "size-9")}>{children}</span>;
}

// Federal agencies restrict their seals, so they get a plain text wordmark.
function Wordmark({ text }: { text: string }) {
  return <span className="text-center text-[9px] leading-none font-extrabold tracking-tight text-ink">{text}</span>;
}

function Logo({ src, className }: { src: string; className?: string }) {
  // eslint-disable-next-line @next/next/no-img-element -- small static SVG brand marks
  return <img src={`/logos/${src}`} alt="" className={cn("h-5 w-auto", className)} />;
}

function Check({ children, at }: { children: ReactNode; at?: number }) {
  return <p className={cn("mt-2 text-[11px] whitespace-nowrap text-ink", at !== undefined && fade)} style={at !== undefined ? reveal(at) : undefined}><span className="mr-1 text-ok">✓</span>{children}</p>;
}

const card = "rounded-[14px] border border-sand-border bg-white shadow-[0_1px_2px_rgb(21_22_26/0.04),0_6px_16px_-6px_rgb(21_22_26/0.08)]";

function Node({ tile, name, role, children, className, style }: { tile?: ReactNode; name: string; role?: string; children?: ReactNode; className?: string; style?: CSSProperties }) {
  return (
    <div className={cn(card, "p-3", className)} style={style}>
      <div className="flex items-center gap-3">
        {tile}
        <div className="min-w-0">
          <p className="text-[13px] leading-tight font-semibold text-ink">{name}</p>
          {role && <p className="mt-0.5 text-[11.5px] leading-snug text-muted-foreground">{role}</p>}
        </div>
      </div>
      {children}
    </div>
  );
}

const sources = [
  { name: "NASA EONET", role: "Open disaster events", tile: <Wordmark text="NASA" /> },
  { name: "NWS", role: "Weather alerts", tile: <Wordmark text="NWS" /> },
  { name: "NASA FIRMS", role: "Active fire detections", tile: <Wordmark text="NASA" /> },
  { name: "OpenFEMA", role: "Disaster declarations", tile: <Wordmark text="FEMA" /> },
];
const screens = [
  { label: "OFAC", tile: <Wordmark text="OFAC" /> },
  { label: "openFDA", tile: <Wordmark text="FDA" /> },
  { label: "USAspending", tile: <Wordmark text="USA$" /> },
  { label: "SAM.gov", tile: <Wordmark text="SAM" /> },
  { label: "CRS", tile: <Logo src="crs.svg" className="h-auto w-[22px]" /> },
];
const assistants = [
  { name: "Gemini", role: "drafts quotes", tile: <Logo src="gemini.svg" /> },
  { name: "Fetch.ai agent", role: "answers questions", tile: <Logo src="fetch-ai.svg" /> },
  { name: "Explain changes", role: "read-only", tile: <ScrollText className="size-4 text-muted-foreground" strokeWidth={1.5} /> },
];

function Apify({ className, style, checkAt }: { className?: string; style?: CSSProperties; checkAt?: number }) {
  return <Node className={className} style={style} tile={<Tile><Logo src="apify.svg" /></Tile>} name="Apify" role="Supplier discovery"><Check at={checkAt}>4 suppliers found</Check></Node>;
}

function Evidence({ className, style, checkAt }: { className?: string; style?: CSSProperties; checkAt?: number }) {
  return (
    <div className={cn(card, "p-3", className)} style={style}>
      <p className="text-sm font-semibold text-ink">Evidence &amp; screening</p>
      <p className="mt-0.5 text-xs text-muted-foreground">Source-backed checks</p>
      {/* Fixed columns keep every tile, CRS included, inside the card; USAspending's long label gets a wider one. */}
      <ul className="mt-3 grid grid-cols-[1fr_1fr_1.5fr_1fr_1fr]">
        {screens.map((screen) => <li key={screen.label} className="flex flex-col items-center gap-1"><Tile small>{screen.tile}</Tile><span className="text-[8px] whitespace-nowrap text-muted-foreground">{screen.label}</span></li>)}
      </ul>
      <Check at={checkAt}>20 checks · 1 needs review</Check>
    </div>
  );
}

function Rules() {
  return <Node className="shadow-none" tile={<Tile small><Scale className="size-4 text-muted-foreground" strokeWidth={1.5} /></Tile>} name="Rules" role="deterministic policy" />;
}

function Optimizer({ checkAt }: { checkAt?: number }) {
  return <Node className="shadow-none" tile={<Tile small><Sigma className="size-4 text-muted-foreground" strokeWidth={1.5} /></Tile>} name="Optimizer" role="PuLP / CBC"><Check at={checkAt}>Plan v2 in 1.8 s</Check></Node>;
}

function Approval({ className, style }: { className?: string; style?: CSSProperties }) {
  return (
    <Node
      className={cn("border-[1.5px] border-signal", className)} style={style}
      tile={<span className="grid size-9 shrink-0 place-items-center rounded-full bg-[#7A7D83] text-xs font-semibold text-white">JP</span>}
      name="Human approval" role="Independent approver"
    />
  );
}

function FooterTiles({ className, style }: { className?: string; style?: CSSProperties }) {
  return (
    <div className={className} style={style}>
      <Node className="flex items-center" tile={<Tile><Logo src="mongodb.svg" className="h-6" /></Tile>} name="System of record" role="MongoDB" />
      <Node className="flex items-center" tile={<Tile><Hash className="size-4 text-muted-foreground" strokeWidth={1.5} /></Tile>} name="Every step" role="SHA-256 audit" />
      <Node
        className="flex items-center"
        tile={<span className="flex items-center gap-3 pr-2"><Logo src="coinbase.svg" className="h-4" /><span className="h-6 w-px bg-sand-border" /><Logo src="solana.svg" className="h-5" /></span>}
        name="Evidence purchases" role="Coinbase x402 · Solana devnet (test USDC)"
      />
    </div>
  );
}

const lane = "text-xs font-medium tracking-[0.12em] text-muted-foreground uppercase";

type Edge = { d: string; delay: number; duration: number; tone?: "gray" | "signal" | "ai"; end?: [number, number, number] };

// Curves between node ports. `end` is the arrowhead: x, y, and angle in degrees.
const edges: Edge[] = [
  ...[64, 136, 208, 280].map((y) => ({ d: `M196 ${y} C215 ${y} 210 168 230 168`, delay: 0, duration: 250 })),
  { d: "M230 168 L326 168", delay: 250, duration: 150, end: [326, 168, 0] },
  { d: "M454 168 L512 168", delay: 400, duration: 150, end: [512, 168, 0] },
  { d: "M740 168 L794 168", delay: 550, duration: 150, end: [794, 168, 0] },
  { d: "M878 136 L878 184", delay: 700, duration: 100, end: [878, 184, 90] },
  { d: "M1217 234 C1217 264 1144 262 1144 292", delay: 700, duration: 150, end: [1144, 292, 90] },
  { d: "M1217 234 C1217 264 1259 262 1259 292", delay: 700, duration: 150, end: [1259, 292, 90] },
  { d: "M405 404 C405 330 626 320 626 246", delay: 600, duration: 250, tone: "ai", end: [626, 246, -90] },
  { d: "M665 404 C665 350 878 350 878 298", delay: 600, duration: 250, tone: "ai", end: [878, 298, -90] },
  { d: "M925 404 C925 300 1114 250 1114 144", delay: 600, duration: 250, tone: "ai", end: [1114, 144, -90] },
  { d: "M962 232 C995 232 990 108 1016 108", delay: 850, duration: 200, tone: "signal", end: [1016, 108, 0] },
  { d: "M1212 108 C1250 108 1260 130 1260 170", delay: 1050, duration: 150, tone: "signal", end: [1260, 170, 90] },
];

const stroke = { gray: "#A8A196", signal: "#F25C1F", ai: "#A8A196" };

function EdgeLayer() {
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden>
      <defs><filter id="signal-glow" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="3" /></filter></defs>
      {edges.map((edge, index) => {
        const tone = edge.tone ?? "gray";
        const start = edge.d.match(/^M(\d+) (\d+)/)!;
        const arrowAt = edge.delay + edge.duration;
        return (
          <g key={index}>
            {tone === "signal" && <path d={edge.d} pathLength={1} fill="none" stroke={stroke.signal} strokeWidth={6} opacity={0.35} filter="url(#signal-glow)" className="[stroke-dasharray:1] [stroke-dashoffset:1] transition-[stroke-dashoffset] ease-out group-data-[drawn=true]:[stroke-dashoffset:0] motion-reduce:[stroke-dashoffset:0] motion-reduce:transition-none" style={reveal(edge.delay, edge.duration)} />}
            {tone === "ai"
              ? <path d={edge.d} fill="none" stroke={stroke.ai} strokeWidth={1.25} strokeDasharray="4 4" className={fade} style={reveal(edge.delay, edge.duration)} />
              : <path d={edge.d} pathLength={1} fill="none" stroke={stroke[tone]} strokeWidth={tone === "signal" ? 1.75 : 1.25} className="[stroke-dasharray:1] [stroke-dashoffset:1] transition-[stroke-dashoffset] ease-out group-data-[drawn=true]:[stroke-dashoffset:0] motion-reduce:[stroke-dashoffset:0] motion-reduce:transition-none" style={reveal(edge.delay, edge.duration)} />}
            <circle cx={start[1]} cy={start[2]} r={3} fill={stroke[tone]} stroke="#F5F2EC" strokeWidth={1.5} className={fade} style={reveal(edge.delay, 100)} />
            {edge.end && <path d="M-6 -4 L0 0 L-6 4" fill="none" stroke={stroke[tone]} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" transform={`translate(${edge.end[0]} ${edge.end[1]}) rotate(${edge.end[2]})`} className={fade} style={reveal(arrowAt - 50, 100)} />}
          </g>
        );
      })}
    </svg>
  );
}

function EdgeLabel({ x, y, children, at, signal = false, align = "center" }: { x: number; y: number; children: ReactNode; at: number; signal?: boolean; align?: "center" | "left" }) {
  return (
    <span
      className={cn("absolute text-[11px] whitespace-nowrap", signal ? "text-sm font-medium text-signal" : "text-ink/80", align === "center" && "-translate-x-1/2", fade)}
      style={{ left: x, top: y, ...reveal(at) }}
    >
      {children}
    </span>
  );
}

const at = (x: number, y: number, w: number, h?: number): CSSProperties => ({ position: "absolute", left: x, top: y, width: w, height: h });

function Canvas() {
  return (
    <div className="relative" style={{ width: W, height: H }}>
      <EdgeLayer />
      <p className={cn(lane, "absolute")} style={at(0, 0, 300)}>Data · fetched live</p>
      <p className={cn(lane, "absolute")} style={at(794, 0, 220)}>Rules &amp; math · decide</p>
      <p className={cn(lane, "absolute")} style={at(1016, 0, 220)}>Human · approves</p>
      {sources.map((source, index) => <Node key={source.name} style={at(0, 34 + index * 72, 196, 60)} tile={<Tile>{source.tile}</Tile>} name={source.name} role={source.role} />)}
      <EdgeLabel x={278} y={150} at={250}>Wildfire · Oakland</EdgeLabel>
      <Apify style={at(326, 110, 128)} checkAt={400} />
      <EdgeLabel x={483} y={150} at={400}>4 suppliers</EdgeLabel>
      <Evidence style={at(512, 96, 228)} checkAt={550} />
      <EdgeLabel x={767} y={150} at={550}>20 checks</EdgeLabel>
      <div className={cn(card, "absolute p-2.5")} style={at(794, 34, 168, 258)}>
        <p className="px-1 pb-2 text-sm font-semibold text-ink">Decision core</p>
        <Rules />
        <div className="h-[46px]" />
        <Optimizer checkAt={800} />
      </div>
      <EdgeLabel x={888} y={152} at={700} align="left">3 eligible</EdgeLabel>
      <Approval style={at(1016, 78, 196, 60)} />
      <EdgeLabel x={986} y={206} at={1050} align="left" signal>Plan v2 · $3,466</EdgeLabel>
      <EdgeLabel x={1222} y={80} at={1200} align="left" signal>Approved</EdgeLabel>
      <div className={cn(card, "absolute px-4 py-3 text-center")} style={at(1122, 170, 190, 64)}>
        <p className="text-sm font-semibold text-ink">Purchase orders</p>
        <p className="mt-0.5 text-xs text-muted-foreground">Draft, then confirm &amp; send</p>
      </div>
      <div className={cn(card, "absolute grid place-items-center text-xs font-medium whitespace-nowrap text-ink")} style={at(1092, 292, 104, 46)}>Supplier email</div>
      <div className={cn(card, "absolute grid place-items-center text-[11px] font-medium whitespace-nowrap text-ink")} style={at(1204, 292, 108, 46)}>Audit log · SHA-256</div>
      <p className={cn(lane, "absolute -translate-x-1/2 bg-sand px-3")} style={{ left: 665, top: 362 }}>AI assists. It never decides.</p>
      {assistants.map((assistant, index) => <Node key={assistant.name} className="flex items-center" style={at(300 + index * 260, 404, 210, 72)} tile={<Tile>{assistant.tile}</Tile>} name={assistant.name} role={assistant.role} />)}
      <FooterTiles className="grid grid-cols-[380px_380px_1fr] gap-3 [&>*]:h-20" style={at(0, 520, W, 80)} />
    </div>
  );
}

// Plays once, when at least a third of the diagram is on screen.
function useDrawOnce() {
  const ref = useRef<HTMLDivElement>(null);
  const [drawn, setDrawn] = useState(false);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new IntersectionObserver(([entry]) => { if (entry.isIntersecting) { setDrawn(true); observer.disconnect(); } }, { threshold: 0.3 });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return { ref, drawn };
}

function useFitScale() {
  const ref = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    const measure = () => setScale(Math.min(1, element.clientWidth / W));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return { ref, scale };
}

function Down({ label, signal = false }: { label?: string; signal?: boolean }) {
  return (
    <div className="flex h-12 items-center gap-3 pl-[22px]">
      <span className={cn("h-full w-px", signal ? "w-0.5 bg-signal" : "bg-[#A8A196]")} />
      {label && <span className={cn("text-xs", signal ? "font-medium text-signal" : "text-ink/80")}>{label}</span>}
    </div>
  );
}

// Under 1024px: the same nodes stacked top to bottom, with the AI lane as a list underneath.
function VerticalFlow() {
  return (
    <div>
      <p className={lane}>Data · fetched live</p>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">{sources.map((source) => <Node key={source.name} tile={<Tile>{source.tile}</Tile>} name={source.name} role={source.role} />)}</div>
      <Down label="Wildfire · Oakland" />
      <Apify />
      <Down label="4 suppliers" />
      <Evidence />
      <Down label="20 checks" />
      <p className={cn(lane, "mb-3")}>Rules &amp; math · decide</p>
      <div className={cn(card, "p-2.5")}>
        <p className="px-1 pb-2 text-sm font-semibold text-ink">Decision core</p>
        <Rules />
        <Down label="3 eligible" />
        <Optimizer />
      </div>
      <Down label="Plan v2 · $3,466" signal />
      <p className={cn(lane, "mb-3")}>Human · approves</p>
      <Approval />
      <Down label="Approved" signal />
      <div className={cn(card, "px-4 py-3")}>
        <p className="text-sm font-semibold text-ink">Purchase orders</p>
        <p className="mt-0.5 text-xs text-muted-foreground">Draft, then confirm &amp; send</p>
      </div>
      <Down />
      <div className="grid grid-cols-2 gap-2">
        <div className={cn(card, "px-4 py-3 text-xs font-medium text-ink")}>Supplier email</div>
        <div className={cn(card, "px-4 py-3 text-xs font-medium text-ink")}>Audit log · SHA-256</div>
      </div>
      <p className={cn(lane, "mt-12")}>AI assists. It never decides.</p>
      <ul className="mt-3 grid gap-2">{assistants.map((assistant) => <li key={assistant.name}><Node tile={<Tile>{assistant.tile}</Tile>} name={assistant.name} role={assistant.role} /></li>)}</ul>
      <FooterTiles className="mt-10 grid gap-2" />
    </div>
  );
}

export function HowItWorks() {
  const { ref, drawn } = useDrawOnce();
  const { ref: fitRef, scale } = useFitScale();
  return (
    <section
      id="how-it-works"
      className="scroll-mt-24 bg-sand bg-[radial-gradient(circle,#E1DED9_1px,transparent_1.5px)] bg-[length:24px_24px] py-20 md:py-24"
    >
      <div className="mx-auto max-w-[1376px] px-4 md:px-8">
        <p className={lane}>How it works</p>
        <h2 className="mt-4 text-[34px] leading-[1.05] font-bold tracking-[-0.03em] text-ink md:text-[52px]">From a real emergency to a human decision.</h2>
        <div ref={ref} data-drawn={drawn} className="group mt-14">
          <div ref={fitRef} className="hidden lg:block" style={{ height: H * scale }}>
            <div className="origin-top-left" style={{ transform: `scale(${scale})` }}><Canvas /></div>
          </div>
          <div className="lg:hidden"><VerticalFlow /></div>
        </div>
      </div>
    </section>
  );
}
