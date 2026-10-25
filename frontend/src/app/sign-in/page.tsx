"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { AuthForm } from "@/components/auth-form";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { safeNext, saveSession } from "@/lib/session";

function SignIn() {
  const router = useRouter();
  const next = safeNext(useSearchParams().get("next"));
  return <main className="grid min-h-screen place-items-center bg-background panel-grid px-5"><Card className="w-full max-w-md"><CardHeader><CardTitle>Sign in to ReliefMesh</CardTitle><CardDescription>Use the account associated with your organization or supplier profile.</CardDescription></CardHeader><CardContent><AuthForm mode="login" onAuthenticated={(token, user) => { saveSession(token, user); router.push(next ?? (user.role === "supplier" ? "/supplier" : "/dashboard")); }} /><p className="mt-5 text-center text-sm text-muted-foreground">New here? <Link className="font-medium text-foreground underline" href={next ? `/sign-up?next=${encodeURIComponent(next)}` : "/sign-up"}>Create an account</Link></p></CardContent></Card></main>;
}

export default function SignInPage() {
  return <Suspense fallback={<main className="grid min-h-screen place-items-center">Loading sign-in…</main>}><SignIn /></Suspense>;
}
