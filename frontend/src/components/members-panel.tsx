"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";

type Members = { members: { user_id: string; email: string | null; role: string }[]; pending: { id: string; email: string; role: string }[] };

export function MembersPanel({ organizationId, token, isAdmin }: { organizationId: string; token: string; isAdmin: boolean }) {
  const members = useQuery({ queryKey: ["members", organizationId], queryFn: () => api<Members>(`/v1/organizations/${organizationId}/members`, { token }) });
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("approver");
  const [message, setMessage] = useState<string | null>(null);
  return (
    <div className="rounded-lg border p-3">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Members & approvers</p>
      <p className="text-[11px] text-tertiary">Segregation of duties: the coordinator who requests a mission cannot approve its plan. Add an approver to sign off.</p>
      <ul className="mt-2 flex flex-wrap gap-2 text-xs">
        {members.data?.members.map((member) => <li key={member.user_id} className="rounded border px-2 py-0.5">{member.email} · <span className="font-mono text-telemetry">{member.role}</span></li>)}
        {members.data?.pending.map((invite) => <li key={invite.id} className="rounded border border-dashed px-2 py-0.5 text-muted-foreground">{invite.email} · {invite.role} (invite pending)</li>)}
      </ul>
      {isAdmin && (
        <form className="mt-2 flex flex-wrap items-end gap-2" onSubmit={(event) => { event.preventDefault(); setMessage(null); void api<{ invite_url: string; delivery_status: string }>(`/v1/organizations/${organizationId}/members`, { method: "POST", token, body: JSON.stringify({ email, role }) }).then((invite) => { setEmail(""); setMessage(`Invite link (single use, 7 days; email ${invite.delivery_status}): ${invite.invite_url}`); void members.refetch(); }).catch((error: Error) => setMessage(error.message)); }}>
          <div><Label htmlFor="member-email" className="text-xs">Member email</Label><Input id="member-email" type="email" required className="mt-1 h-8 w-64" value={email} onChange={(event) => setEmail(event.target.value)} /></div>
          <div><Label htmlFor="member-role" className="text-xs">Role</Label><select id="member-role" className="mt-1 h-8 rounded-lg border bg-background px-2 text-sm" value={role} onChange={(event) => setRole(event.target.value)}><option value="approver">approver</option><option value="coordinator">coordinator</option><option value="admin">admin</option></select></div>
          <Button size="sm" type="submit">Add member</Button>
        </form>
      )}
      {message && <p className="mt-1 break-all text-xs text-live">{message}</p>}
    </div>
  );
}
