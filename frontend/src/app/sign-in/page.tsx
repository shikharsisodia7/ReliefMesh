"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { AuthForm } from "@/components/auth-form";
import { CenteredColumn } from "@/components/layout/centered-column";
import { safeNext, saveSession } from "@/lib/session";

function SignIn() {
  const router = useRouter();
  const next = safeNext(useSearchParams().get("next"));
  return (
    <CenteredColumn title="Sign in" subtitle="Use the account for your organization or supplier profile.">
      <AuthForm mode="login" onAuthenticated={(token, user) => { saveSession(token, user); router.push(next ?? (user.role === "supplier" ? "/supplier" : "/dashboard")); }} />
      <p className="mt-6 text-center text-sm text-muted-foreground">New to ReliefMesh? <Link className="font-medium text-foreground hover:underline" href={next ? `/sign-up?next=${encodeURIComponent(next)}` : "/sign-up"}>Create an account</Link></p>
    </CenteredColumn>
  );
}

export default function SignInPage() {
  return <Suspense fallback={<main className="grid min-h-screen place-items-center text-sm text-muted-foreground">Loading sign-in…</main>}><SignIn /></Suspense>;
}
