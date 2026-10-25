"use client";

import { Pause, Play, RotateCcw } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

import { nearestDots } from "@/components/landing/california";
import { DotMap } from "@/components/landing/dot-map";
import { amount } from "@/components/status-badges";
import { useCountUp } from "@/hooks/use-count-up";
import { cn } from "@/lib/utils";

// The landing page's live demo. Static demo data, all in the browser: nothing here calls the API.
const MOMENTS = [
  { time: "14:32:08", label: "Quote withdrawn" },
  { time: "14:32:08", label: "Approval revoked" },
  { time: "14:32:10", label: "Plan v2 ready" },
  { time: "14:40", label: "Approved" },
];
const LAST = MOMENTS.length;
const MS_PER_MOMENT = 1000;

const rows = [
  { name: "Golden Gate Medical Logistics", before: 40, after: 70 },
  { name: "Sierra Backup Provisions", before: 0, after: 30 },
  { name: "Bayside Relief Supply Co", before: 60, after: 0, withdrawn: true },
];

// Decorative glow over the Bay Area only.
const bayArea = nearestDots([
  { latitude: 37.8, longitude: -122.27 }, { latitude: 37.55, longitude: -122.05 }, { latitude: 37.95, longitude: -122.05 },
  { latitude: 37.68, longitude: -121.85 }, { latitude: 37.4, longitude: -121.95 },
]);

// A constant element, so the per-frame playback renders skip its ~2,600 dots. It sits under the cards, placed so the
// Bay Area glow lands in the open space left of the plan card.
const backdrop = <DotMap lit={bayArea} glow dotClass="fill-white/[0.12]" className="pointer-events-none absolute top-[-300px] left-[40px] h-[1300px] w-auto max-lg:hidden" />;

// Slides in from one side once its moment is reached; under reduced motion it just appears.
// In the stacked mobile layout a fragment takes no space until its moment.
function Reveal({ shown, from = "left", className, children }: { shown: boolean; from?: "left" | "right" | "below"; className?: string; children: ReactNode }) {
  const offset = from === "left" ? "-translate-x-6" : from === "right" ? "translate-x-6" : "translate-y-3";
  return (
    <div inert={!shown} className={cn("transition-[opacity,translate,visibility] duration-500 ease-out motion-reduce:transition-none", shown ? "opacity-100" : cn("invisible opacity-0 max-lg:hidden", offset), className)}>
      {children}
    </div>
  );
}

// A thin white leader line from an anchor dot to a short sentence, drawn up and to the right.
function Callout({ shown, dx, dy, children }: { shown: boolean; dx: number; dy: number; children: ReactNode }) {
  return (
    <span aria-hidden={!shown} className={cn("pointer-events-none absolute top-1/2 left-full ml-2 hidden transition-[opacity,visibility] duration-500 motion-reduce:transition-none lg:block", shown ? "opacity-100" : "invisible opacity-0")}>
      <svg className="absolute overflow-visible mix-blend-difference" width="1" height="1" aria-hidden>
        <circle r="3.5" fill="white" />
        <path d={`M0 0 L${dx - 40} ${-dy} L${dx} ${-dy}`} fill="none" stroke="white" strokeWidth="1" />
      </svg>
      <span className="absolute text-base font-medium whitespace-nowrap text-white" style={{ left: dx + 12, top: -dy - 13 }}>{children}</span>
    </span>
  );
}

function PlanCard({ moment }: { moment: number }) {
  const rebuilt = moment >= 3;
  const total = useCountUp(rebuilt ? 3466 : 3271);
  return (
    <div className="rounded-[14px] bg-white p-6 text-ink shadow-[0_30px_80px_-20px_rgb(0_0_0/0.6)] md:p-8">
      <h3 className="text-2xl font-bold tracking-tight md:text-[32px]">Shelter blankets · Plan v{rebuilt ? 2 : 1}</h3>
      <p className="mt-4 flex flex-wrap items-baseline gap-x-4 tabular">
        {rebuilt && <><span className="text-2xl font-semibold text-tertiary line-through md:text-[32px]">$3,271</span><span className="text-2xl text-muted-foreground" aria-hidden>→</span></>}
        <span className="text-3xl font-bold tracking-tight md:text-[40px]" data-testid="demo-total">{amount(Math.round(total))}</span>
        <span className={cn("relative text-lg text-muted-foreground transition-opacity duration-300 md:text-xl", rebuilt ? "opacity-100" : "opacity-0")}>
          (+$195)
          <Callout shown={rebuilt} dx={230} dy={50}>Still $1,534 under budget.</Callout>
        </span>
      </p>
      <table className="mt-5 w-full text-sm md:text-base">
        <thead><tr className="border-y bg-muted text-left text-sm text-muted-foreground"><th className="px-4 py-2.5 font-medium">Supplier</th><th className="px-4 py-2.5 text-right font-medium">Quantity</th></tr></thead>
        <tbody>
          {rows.map((row) => {
            const gone = row.withdrawn && moment >= 1;
            const changed = row.withdrawn ? moment >= 1 : rebuilt;
            return (
              <tr key={row.name} className={cn("border-b transition-colors duration-500", gone && "text-tertiary")}>
                <td className="px-4 py-3">{row.name}</td>
                <td className="px-4 py-3 text-right whitespace-nowrap tabular">
                  <span className="relative inline-flex items-center gap-2">
                    {changed ? <><span className={cn(gone && "line-through")}>{row.before}</span><span aria-hidden>→</span><span>{row.after}</span></> : row.before}
                    {row.withdrawn && <Callout shown={rebuilt} dx={130} dy={70}>Bayside&apos;s 60 blankets, reassigned.</Callout>}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mt-4 min-h-6 text-sm text-muted-foreground md:text-base">
        {moment >= 2 ? "Approval revoked · new approval required." : "Plan v1 approved."}
      </p>
      {rebuilt && <p className="mt-2 text-sm text-muted-foreground lg:hidden">Bayside&apos;s 60 blankets, reassigned. Still $1,534 under budget.</p>}
    </div>
  );
}

function SupplierNotice() {
  return (
    <div className="rounded-xl border border-white/60 bg-[#F4F4F5] p-5 text-ink shadow-[0_20px_50px_-20px_rgb(0_0_0/0.6)]">
      <p className="text-lg font-semibold tracking-tight">Bayside Relief Supply Co</p>
      <p className="mt-0.5 text-sm text-muted-foreground tabular">Quote withdrawn · 14:32:08</p>
      <p className="mt-4 border-t pt-3 text-sm text-muted-foreground">Withdrawn</p>
    </div>
  );
}

function ApprovalRequest({ approved, onApprove }: { approved: boolean; onApprove: () => void }) {
  return (
    <div className="rounded-xl border-[1.5px] border-signal bg-white p-5 text-ink shadow-[0_20px_50px_-20px_rgb(0_0_0/0.6)]">
      <div className="flex items-center gap-3">
        <span className="grid size-9 place-items-center rounded-full border bg-muted text-xs font-semibold">JP</span>
        <div>
          <p className="text-sm font-medium">Jordan Park</p>
          <p className="text-lg font-semibold tracking-tight">Approve plan v2 · $3,466</p>
        </div>
      </div>
      <button type="button" onClick={onApprove} disabled={approved} className="mt-4 h-11 w-full rounded-md bg-ink text-base font-semibold text-white outline-hidden hover:bg-ink/90 focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-2 focus-visible:outline-signal disabled:bg-ink/80">
        {approved ? "Approved" : "Approve"}
      </button>
      <p className="mt-2 text-center text-xs text-muted-foreground">Demo only</p>
    </div>
  );
}

function AuditEntry() {
  return <p className="rounded-lg border border-white/30 px-4 py-3 font-mono text-xs whitespace-nowrap text-white/85">#14 plan.approved · 7b92…e14c</p>;
}

function Scrubber({ progress, playing, onToggle, onSeek }: { progress: number; playing: boolean; onToggle: () => void; onSeek: (value: number) => void }) {
  const moment = Math.floor(progress + 1e-6);
  const fill = `${(progress / LAST) * 100}%`;
  const label = moment === 0 ? "Before the failure" : `${MOMENTS[moment - 1].time} ${MOMENTS[moment - 1].label}`;
  // Arrow keys jump between the four moments instead of creeping along.
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    const next = { ArrowRight: moment + 1, ArrowUp: moment + 1, ArrowLeft: Math.ceil(progress - 1e-6) - 1, ArrowDown: Math.ceil(progress - 1e-6) - 1, Home: 0, End: LAST }[event.key];
    if (next === undefined) return;
    event.preventDefault();
    onSeek(Math.max(0, Math.min(LAST, next)));
  };
  const Icon = playing ? Pause : progress >= LAST ? RotateCcw : Play;
  return (
    <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:gap-8">
      <button type="button" onClick={onToggle} className="flex shrink-0 items-center gap-3 rounded-md py-1 text-base font-medium text-white outline-hidden focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-4 focus-visible:outline-signal lg:-mt-2.5">
        <Icon className="size-6" strokeWidth={1.5} />
        {playing ? "Pause" : progress >= LAST ? "Replay failure" : "Simulate failure"}
      </button>
      <div className="min-w-0 flex-1">
        <div className="relative h-5">
          <span className="absolute inset-x-0 top-1/2 h-1 -translate-y-1/2 rounded-full bg-white/30" />
          <span className="absolute top-1/2 left-0 h-1 -translate-y-1/2 rounded-full bg-signal" style={{ width: fill }} />
          {MOMENTS.map((item, index) => <span key={index} className="absolute top-1/2 h-3 w-px -translate-y-1/2 bg-white/80" style={{ left: `${((index + 1) / LAST) * 100}%` }} />)}
          <span className="absolute top-1/2 size-5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white shadow" style={{ left: fill }} />
          <input
            type="range" min={0} max={LAST} step={0.01} value={progress} aria-label="Failure timeline" aria-valuetext={label}
            onChange={(event) => onSeek(Number(event.target.value))} onKeyDown={onKeyDown}
            className="peer absolute inset-0 h-full w-full cursor-pointer opacity-0"
          />
          <span className="pointer-events-none absolute top-1/2 hidden size-7 -translate-x-1/2 -translate-y-1/2 rounded-full outline-2 outline-signal peer-focus-visible:block" style={{ left: fill }} />
        </div>
        <ol className="relative mt-3 hidden h-12 text-sm text-white/80 lg:block">
          {MOMENTS.map((item, index) => {
            const last = index === LAST - 1;
            return (
              <li key={index} className={cn("absolute tabular", last ? "right-0 text-right" : "-translate-x-[2px]", moment > index && "text-white")} style={last ? undefined : { left: `${((index + 1) / LAST) * 100}%` }}>
                <span className="block">{item.time}</span><span className="block">{item.label}</span>
              </li>
            );
          })}
        </ol>
        <p className="mt-3 text-sm text-white/80 tabular lg:hidden" aria-live="polite">{label}</p>
      </div>
    </div>
  );
}

export function SupplierFails() {
  const [progress, setProgress] = useState(0);
  const [playing, setPlaying] = useState(false);
  const startedFrom = useRef(0);
  const moment = Math.floor(progress + 1e-6);

  // Plays from where play was pressed to 14:40, one moment per second.
  useEffect(() => {
    if (!playing) return;
    const started = performance.now();
    let frame = 0;
    const step = (now: number) => {
      // The first frame's timestamp can be a little earlier than `started`.
      const next = Math.min(LAST, startedFrom.current + Math.max(0, now - started) / MS_PER_MOMENT);
      setProgress(next);
      if (next < LAST) frame = requestAnimationFrame(step);
      else setPlaying(false);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [playing]);

  const toggle = () => {
    if (playing) return setPlaying(false);
    startedFrom.current = progress >= LAST ? 0 : progress;
    setProgress(startedFrom.current);
    setPlaying(true);
  };
  const seek = (value: number) => { setPlaying(false); setProgress(value); };

  return (
    <section aria-labelledby="supplier-fails-title" className="relative overflow-hidden bg-charcoal py-20 text-white md:py-28">
      <div className="relative mx-auto max-w-[1376px] px-4 md:px-8">
        <h2 id="supplier-fails-title" className="max-w-[900px] text-[38px] leading-[1.02] font-bold tracking-[-0.035em] md:text-[72px]">When a supplier fails,<br className="max-md:hidden" /> the plan rebuilds itself.</h2>

        <div className="mt-12 grid gap-4 lg:relative lg:mt-16 lg:block lg:h-[580px]">
          {backdrop}
          <Reveal shown={moment >= 1} className="lg:absolute lg:top-[60px] lg:left-[30px] lg:z-10 lg:w-[330px] lg:-rotate-2">
            <SupplierNotice />
          </Reveal>
          <div className="lg:absolute lg:top-0 lg:left-[330px] lg:z-20 lg:w-[580px]">
            <PlanCard moment={moment} />
          </div>
          <Reveal shown={moment >= 3} from="right" className="lg:absolute lg:top-[372px] lg:left-[760px] lg:z-30 lg:w-[320px]">
            <ApprovalRequest approved={moment >= 4} onApprove={() => seek(LAST)} />
          </Reveal>
          {/* The audit entry exists only once the plan is approved at 14:40. */}
          <Reveal shown={moment >= 4} from="below" className="lg:absolute lg:top-[480px] lg:left-[1096px] lg:z-30">
            <AuditEntry />
          </Reveal>
        </div>

        <div className="mt-14">
          <Scrubber progress={progress} playing={playing} onToggle={toggle} onSeek={seek} />
        </div>
        <p className="mt-10 text-sm text-white/70 md:text-base">20 evidence checks per plan · 0 approvals carried over · every step on a SHA-256 hash chain.</p>
      </div>
    </section>
  );
}
