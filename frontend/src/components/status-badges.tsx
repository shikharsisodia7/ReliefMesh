import { cn } from "@/lib/utils";

const provenanceStyles: Record<string, string> = {
  LIVE: "border-live/40 bg-live/10 text-live",
  CACHED: "border-telemetry/40 bg-telemetry/10 text-telemetry",
  SANDBOX: "border-violet-400/40 bg-violet-400/10 text-violet-300",
  USER_SUBMITTED: "border-sky-300/30 bg-sky-300/10 text-sky-200",
  SYNTHETIC: "border-fuchsia-400/40 bg-fuchsia-400/10 text-fuchsia-300",
  TEST: "border-fuchsia-400/40 bg-fuchsia-400/10 text-fuchsia-300",
  BLOCKED_EXTERNAL: "border-muted-foreground/30 bg-muted text-muted-foreground",
  UNAVAILABLE: "border-critical/40 bg-critical/10 text-critical",
};

const labels: Record<string, string> = { USER_SUBMITTED: "USER SUBMITTED", BLOCKED_EXTERNAL: "NOT CONFIGURED", NEEDS_REVIEW: "NEEDS REVIEW" };

export function ProvenanceBadge({ value, className }: { value?: string | null; className?: string }) {
  if (!value) return null;
  return (
    <span className={cn("inline-flex h-5 items-center rounded border px-1.5 font-mono text-[10px] font-semibold tracking-wider", provenanceStyles[value] ?? provenanceStyles.BLOCKED_EXTERNAL, className)} title={`Data provenance: ${value}`}>
      {labels[value] ?? value}
    </span>
  );
}

const policyStyles: Record<string, string> = {
  PASS: "border-ok/40 bg-ok/10 text-ok",
  WARN: "border-warn/40 bg-warn/10 text-warn",
  NEEDS_REVIEW: "border-telemetry/50 bg-telemetry/15 text-telemetry",
  BLOCK: "border-critical/50 bg-critical/15 text-critical",
};

export function PolicyBadge({ value, className }: { value?: string | null; className?: string }) {
  if (!value) return null;
  return (
    <span className={cn("inline-flex h-5 items-center rounded border px-1.5 font-mono text-[10px] font-bold tracking-wider", policyStyles[value] ?? policyStyles.WARN, className)} title={`Policy status: ${value}`}>
      {labels[value] ?? value}
    </span>
  );
}

const planStyles: Record<string, string> = {
  feasible: "border-live/40 bg-live/10 text-live",
  approved: "border-ok/50 bg-ok/15 text-ok",
  stale: "border-muted-foreground/30 bg-muted text-muted-foreground line-through decoration-1",
  infeasible: "border-critical/50 bg-critical/15 text-critical",
};

export function PlanStatusBadge({ value }: { value: string }) {
  return <span className={cn("inline-flex h-5 items-center rounded border px-1.5 font-mono text-[10px] font-bold uppercase tracking-wider", planStyles[value] ?? planStyles.stale)}>{value}</span>;
}

export function StatusDot({ tone }: { tone: "ok" | "warn" | "critical" | "idle" | "live" }) {
  const color = { ok: "bg-ok", warn: "bg-warn", critical: "bg-critical", idle: "bg-tertiary", live: "bg-live" }[tone];
  return <span className={cn("inline-block size-2 rounded-full", color, tone === "live" && "animate-pulse")} aria-hidden />;
}

export function money(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") return "—";
  const number = typeof value === "number" ? value : Number(value);
  return number.toLocaleString("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2 });
}

export function when(value?: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export function ago(value?: string | null) {
  if (!value) return "—";
  const seconds = Math.round((Date.now() - new Date(value).getTime()) / 1000);
  if (seconds < 60) return `${Math.max(seconds, 0)}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86400)}d ago`;
}
