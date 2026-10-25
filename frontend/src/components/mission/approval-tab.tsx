"use client";

import { ApprovalSection } from "@/components/mission/plan-tab";
import { PlanStatusText, StatusText, money, when, type Tone } from "@/components/status-badges";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { Approval, Plan } from "@/lib/types";

type Run = (operation: () => Promise<void>) => Promise<void>;

const STATUS: Record<Approval["status"], [string, Tone]> = { active: ["Active", "neutral"], invalidated: ["Revoked", "muted"], expired: ["Expired", "muted"], consumed: ["Used", "neutral"] };

function reason(approval: Approval) {
  if (approval.status === "invalidated") return `Revoked: ${approval.invalidation_reason ?? "the plan changed"}`;
  if (approval.status === "expired") return `Expired: ${approval.invalidation_reason ?? "approval window elapsed"}`;
  if (approval.status === "consumed") return `Purchase orders generated${approval.consumed_at ? ` ${when(approval.consumed_at)}` : ""}`;
  return approval.expires_at ? `Expires ${when(approval.expires_at)}` : "";
}

// Approval tab: where the current plan stands, and the history that shows approvals never carry over to a changed plan.
export function ApprovalTab({ plans, approvals, demoOrg, canApprove, approvalBlocked, requester, ttlMinutes, token, run, setNotice, onTab }: {
  plans: Plan[]; approvals: Approval[]; demoOrg: boolean; canApprove: boolean; approvalBlocked: string | null; requester: string; ttlMinutes: number;
  token: string; run: Run; setNotice: (value: string) => void; onTab: (tab: string) => void;
}) {
  const [plan] = plans;
  const history = [...approvals].sort((a, b) => b.approved_at.localeCompare(a.approved_at));
  return (
    <div className="space-y-12">
      <section aria-label="Current approval" className="max-w-md">
        <h2 className="text-xl font-semibold">{plan ? <>Plan v{plan.version} <span className="ml-2 text-base"><PlanStatusText value={plan.status} /></span></> : "No plan yet"}</h2>
        <div className="mt-5">
          {plan ? <ApprovalSection plan={plan} approvals={approvals} canApprove={canApprove} approvalBlocked={approvalBlocked} requester={requester} ttlMinutes={ttlMinutes} token={token} run={run} setNotice={setNotice} onTab={onTab} />
            : <p className="text-sm text-muted-foreground">Approval starts once a feasible plan exists.</p>}
        </div>
        <p className="mt-5 text-sm text-muted-foreground">
          {/* The rail already says so when the viewer is the requester. */}
          {demoOrg ? "Demo organization: self-approval is allowed and each one is labeled DEMO override. " : approvalBlocked ? "" : "Segregation of duties: the coordinator who requested this mission can't approve its plan. "}
          An approval covers one exact plan version, expires, and is used once to generate purchase orders.
        </p>
      </section>

      <section aria-label="Approval history">
        <h3 className="text-base font-semibold">Approval history</h3>
        {history.length === 0 ? <p className="mt-2 text-sm text-muted-foreground">No approvals yet.</p> : (
          <Table className="mt-3">
            <TableHeader><TableRow><TableHead>Plan version</TableHead><TableHead>Status</TableHead><TableHead>Approver</TableHead><TableHead>Time</TableHead><TableHead className="text-right">Amount</TableHead><TableHead>Reason</TableHead></TableRow></TableHeader>
            <TableBody>
              {history.map((approval) => {
                const [label, tone] = STATUS[approval.status] ?? [approval.status, "neutral"];
                return (
                  <TableRow key={approval.id}>
                    <TableCell>v{approval.plan_version}</TableCell>
                    <TableCell><StatusText tone={tone} value={approval.status}>{label}</StatusText></TableCell>
                    <TableCell>{approval.approver_email ?? "—"}{approval.segregation_of_duties === "DEMO_ORG_SELF_APPROVAL_OVERRIDE" && <span className="text-muted-foreground"> · DEMO override</span>}</TableCell>
                    <TableCell>{when(approval.approved_at)}</TableCell>
                    <TableCell className="text-right tabular">{money(approval.amount)}</TableCell>
                    <TableCell className="whitespace-normal text-muted-foreground">{reason(approval)}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </section>

      {plans.length > 0 && (
        <section aria-label="Plan versions">
          <h3 className="text-base font-semibold">Plan versions</h3>
          <p className="mt-1 text-sm text-muted-foreground">Each version is immutable: its inputs, policy fingerprint, and hash are fixed. A stale plan can&apos;t be approved.</p>
          <Table className="mt-3">
            <TableHeader><TableRow><TableHead>Version</TableHead><TableHead>Status</TableHead><TableHead>Computed</TableHead><TableHead>Trigger</TableHead><TableHead className="text-right">Total</TableHead><TableHead>Plan hash</TableHead></TableRow></TableHeader>
            <TableBody>
              {plans.map((row) => (
                <TableRow key={row.id}>
                  <TableCell>v{row.version}</TableCell>
                  <TableCell><PlanStatusText value={row.status} /></TableCell>
                  <TableCell>{when(row.computed_at)}</TableCell>
                  <TableCell className="whitespace-normal">{row.trigger.replace(/_/g, " ")}{row.stale_reason && <span className="block text-xs text-muted-foreground">Stale: {row.stale_reason}</span>}</TableCell>
                  <TableCell className="text-right tabular">{row.status === "infeasible" ? "—" : money(row.total_cost)}</TableCell>
                  <TableCell><span className="font-mono text-xs" title={row.plan_hash}>{row.plan_hash?.slice(0, 12)}…</span></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </section>
      )}
    </div>
  );
}
