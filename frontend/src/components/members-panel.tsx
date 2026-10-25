"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";

// Role codes in plain English.
const ROLE_WORDS: Record<string, string> = { admin: "Administrator", approver: "Approver", coordinator: "Coordinator" };
const roleWord = (role: string) => ROLE_WORDS[role] ?? role;

type Members = { members: { user_id: string; email: string | null; role: string }[]; pending: { id: string; email: string; role: string }[] };

export function MembersPanel({ organizationId, token, isAdmin }: { organizationId: string; token: string; isAdmin: boolean }) {
  const members = useQuery({ queryKey: ["members", organizationId], queryFn: () => api<Members>(`/v1/organizations/${organizationId}/members`, { token }) });
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("approver");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const add = () => {
    setMessage(null); setError(null);
    void api<{ invite_url: string; delivery_status: string }>(`/v1/organizations/${organizationId}/members`, { method: "POST", token, body: JSON.stringify({ email, role }) })
      .then((invite) => { setEmail(""); setMessage(`Invite link (single use, 7 days; email ${invite.delivery_status}): ${invite.invite_url}`); void members.refetch(); })
      .catch((requestError: Error) => setError(requestError.message));
  };
  return (
    <div className="space-y-8">
      <p className="max-w-2xl text-sm text-muted-foreground">Segregation of duties: the coordinator who requests a mission cannot approve its plan. Add an approver to sign off.</p>
      {members.isError && <p className="text-sm text-critical">{members.error.message} <button type="button" className="font-medium text-foreground hover:underline" onClick={() => void members.refetch()}>Retry</button></p>}
      <Table>
        <TableHeader><TableRow><TableHead>Member</TableHead><TableHead>Role</TableHead><TableHead>Status</TableHead></TableRow></TableHeader>
        <TableBody>
          {members.data?.members.map((member) => <TableRow key={member.user_id}><TableCell>{member.email}</TableCell><TableCell>{roleWord(member.role)}</TableCell><TableCell>Active</TableCell></TableRow>)}
          {members.data?.pending.map((invite) => <TableRow key={invite.id} className="text-tertiary"><TableCell>{invite.email}</TableCell><TableCell>{roleWord(invite.role)}</TableCell><TableCell>Invite pending</TableCell></TableRow>)}
        </TableBody>
      </Table>
      {isAdmin && (
        <section>
          <h2 className="text-base font-semibold">Add a member</h2>
          <form className="mt-3 flex flex-wrap items-end gap-3" onSubmit={(event) => { event.preventDefault(); add(); }}>
            <div className="w-full sm:w-auto"><Label htmlFor="member-email">Member email</Label><Input id="member-email" type="email" required className="mt-1.5 w-full sm:w-72" value={email} onChange={(event) => setEmail(event.target.value)} /></div>
            <div className="w-full sm:w-auto"><Label htmlFor="member-role">Role</Label><select id="member-role" className="mt-1.5 h-9 w-full rounded-md border bg-background px-3 text-sm sm:w-auto" value={role} onChange={(event) => setRole(event.target.value)}><option value="approver">Approver · approves plans</option><option value="coordinator">Coordinator · runs missions and orders, cannot approve</option><option value="admin">Administrator · approves, orders, manages members</option></select></div>
            <Button type="submit">Add member</Button>
          </form>
          {message && <p className="mt-3 text-sm break-all text-muted-foreground">{message}</p>}
          {error && <p className="mt-3 text-sm text-critical">{error}</p>}
        </section>
      )}
    </div>
  );
}
