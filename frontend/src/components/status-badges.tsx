import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

// Status is text only: no dots, pills, or tinted backgrounds. Raw API codes stay in data-value.
export type Tone = "ok" | "warn" | "neutral" | "critical" | "muted";

const toneClass: Record<Tone, string> = {
  ok: "text-ok",
  warn: "text-warn",
  neutral: "text-foreground",
  critical: "text-critical",
  muted: "text-muted-foreground",
};

export function StatusText({ tone = "neutral", value, className, children }: { tone?: Tone; value?: string; className?: string; children: ReactNode }) {
  return <span data-value={value} className={cn("font-medium", toneClass[tone], className)}>{children}</span>;
}

const provenanceLabels: Record<string, string> = { USER_SUBMITTED: "USER SUBMITTED", BLOCKED_EXTERNAL: "NOT CONFIGURED" };

// Renders e.g. "LIVE · 14:20". `at` is the API timestamp.
export function Provenance({ value, at, className }: { value?: string | null; at?: string | null; className?: string }) {
  if (!value) return null;
  return (
    <span data-value={value} title={`Data provenance: ${value}`} className={cn("text-xs font-medium tracking-wide whitespace-nowrap text-muted-foreground uppercase", className)}>
      {provenanceLabels[value] ?? value}{at ? ` · ${clock(at)}` : ""}
    </span>
  );
}

const supplierPolicy: Record<string, [string, Tone]> = { PASS: ["Eligible", "neutral"], WARN: ["Eligible", "neutral"], NEEDS_REVIEW: ["Needs review", "warn"], BLOCK: ["Blocked", "neutral"] };
const rulePolicy: Record<string, [string, Tone]> = { PASS: ["Pass", "muted"], WARN: ["Warning", "neutral"], NEEDS_REVIEW: ["Needs review", "warn"], BLOCK: ["Blocked", "neutral"] };

// A supplier's overall verdict, or ("rule") the result of a single policy rule.
export function PolicyText({ value, scope = "supplier", className }: { value?: string | null; scope?: "supplier" | "rule"; className?: string }) {
  if (!value) return null;
  const [label, tone] = (scope === "rule" ? rulePolicy : supplierPolicy)[value] ?? [value, "neutral"];
  return (
    <StatusText tone={tone} value={value} className={className}>
      {label}{scope === "supplier" && value === "WARN" && <span className="font-normal text-muted-foreground"> with warnings</span>}
    </StatusText>
  );
}

const planStates: Record<string, [string, Tone]> = { feasible: ["Feasible", "ok"], approved: ["Approved", "neutral"], stale: ["Stale", "muted"], infeasible: ["Infeasible", "warn"] };

export function PlanStatusText({ value }: { value: string }) {
  const [label, tone] = planStates[value] ?? [value.charAt(0).toUpperCase() + value.slice(1), "neutral"];
  return <StatusText tone={tone} value={value}>{label}</StatusText>;
}

export function money(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") return "—";
  const number = typeof value === "number" ? value : Number(value);
  return number.toLocaleString("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2 });
}

// Dates and times people read, e.g. "Oct 24, 2:20 PM".
export function when(value?: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

// Compact 24-hour HH:mm, only for provenance stamps.
export function clock(value?: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
}

export function ago(value?: string | null) {
  if (!value) return "—";
  const seconds = Math.round((Date.now() - new Date(value).getTime()) / 1000);
  if (seconds < 60) return `${Math.max(seconds, 0)}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86400)}d ago`;
}
