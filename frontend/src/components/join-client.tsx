"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { CenteredColumn } from "@/components/layout/centered-column";
import { when } from "@/components/status-badges";
import { Button, buttonVariants } from "@/components/ui/button";
import { useSession } from "@/hooks/use-session";
import { api } from "@/lib/api";
import { clearSession } from "@/lib/session";

type Invite = { organization: string; email: string; role: string; expires_at: string };

const roleWords: Record<string, string> = { approver: "Approver", coordinator: "Coordinator", admin: "Administrator" };

export function JoinClient({ token }: { token: string }) {
  const router = useRouter();
  const session = useSession();
  const [error, setError] = useState<string | null>(null);
  const [joining, setJoining] = useState(false);
  const invite = useQuery({ queryKey: ["org-invite", token], retry: false, queryFn: () => api<Invite>(`/v1/org-invites/${token}`) });
  const next = encodeURIComponent(`/join/${token}`);
  if (!invite.data) {
    return (
      <CenteredColumn title="Organization invitation">
        {invite.isError ? <p className="text-sm text-critical">{invite.error.message}</p> : <p className="text-sm text-muted-foreground">Loading invitation…</p>}
      </CenteredColumn>
    );
  }
  const otherAccount = Boolean(session && session.user.email?.toLowerCase() !== invite.data.email.toLowerCase());
  const accept = async () => {
    if (!session) return;
    setJoining(true); setError(null);
    try { await api(`/v1/org-invites/${token}/accept`, { method: "POST", token: session.token }); router.push("/dashboard"); }
    catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Could not accept the invitation"); setJoining(false); }
  };
  return (
    <CenteredColumn title={`Join ${invite.data.organization}`}>
      <dl className="space-y-2 text-sm">
        <div className="flex justify-between gap-4"><dt className="text-muted-foreground">Role</dt><dd>{roleWords[invite.data.role] ?? invite.data.role}</dd></div>
        <div className="flex justify-between gap-4"><dt className="text-muted-foreground">For</dt><dd>{invite.data.email}</dd></div>
        <div className="flex justify-between gap-4"><dt className="text-muted-foreground">Expires</dt><dd>{when(invite.data.expires_at)}</dd></div>
      </dl>
      {error && <p role="alert" className="mt-4 text-sm text-critical">{error}</p>}
      <div className="mt-8">
        {!session ? (
          <>
            <Link href={`/sign-up?next=${next}`} className={buttonVariants({ size: "lg", className: "w-full" })}>Create account</Link>
            <p className="mt-3 text-center text-sm text-muted-foreground">Already registered? <Link className="font-medium text-foreground hover:underline" href={`/sign-in?next=${next}`}>Sign in</Link> as {invite.data.email}.</p>
          </>
        ) : otherAccount ? (
          <>
            <p className="text-sm">You&apos;re signed in as {session.user.email}; this invitation is for {invite.data.email}.</p>
            <Button variant="secondary" className="mt-4 w-full" onClick={() => { clearSession(); router.push(`/sign-up?next=${next}`); }}>Sign out and continue as {invite.data.email}</Button>
          </>
        ) : (
          <Button size="lg" className="w-full" disabled={joining} onClick={() => void accept()}>Accept invitation</Button>
        )}
      </div>
    </CenteredColumn>
  );
}
