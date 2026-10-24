"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useSession } from "@/hooks/use-session";
import { api } from "@/lib/api";

type Invite = { organization: string; email: string; role: string; expires_at: string };

export function JoinClient({ token }: { token: string }) {
  const router = useRouter();
  const session = useSession();
  const [error, setError] = useState<string | null>(null);
  const invite = useQuery({ queryKey: ["org-invite", token], retry: false, queryFn: () => api<Invite>(`/v1/org-invites/${token}`) });
  return (
    <main className="grid min-h-screen place-items-center bg-background panel-grid px-5">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>{invite.data ? `Join ${invite.data.organization}` : "Organization invitation"}</CardTitle>
          <CardDescription>{invite.data ? `Invited as ${invite.data.role} for ${invite.data.email}.` : invite.isError ? invite.error.message : "Loading invitation…"}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {error && <p role="alert" className="rounded-md border border-critical/40 bg-critical/10 p-3 text-sm text-critical">{error}</p>}
          {invite.data && (!session ? (
            <p className="text-sm">Sign in or create a coordinator account with <strong>{invite.data.email}</strong>, then reopen this link. <Link className="underline" href="/sign-up">Create account</Link> · <Link className="underline" href="/sign-in">Sign in</Link></p>
          ) : (
            <Button onClick={() => void api(`/v1/org-invites/${token}/accept`, { method: "POST", token: session.token }).then(() => router.push("/dashboard")).catch((requestError: Error) => setError(requestError.message))}>Accept invitation</Button>
          ))}
        </CardContent>
      </Card>
    </main>
  );
}
