"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { AuthForm } from "@/components/auth-form";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { safeNext, saveSession } from "@/lib/session";

export function SignUpClient() {
  const router = useRouter();
  const params = useSearchParams();
  const role = params.get("role") === "supplier" ? "supplier" : "coordinator";
  const next = safeNext(params.get("next"));
  return <main className="grid min-h-screen place-items-center bg-background panel-grid px-5"><Card className="w-full max-w-md"><CardHeader><CardTitle>Create a {role} account</CardTitle><CardDescription>{role === "supplier" ? "Use the email address that received your RFQ invitation." : "You will create your response organization next."}</CardDescription></CardHeader><CardContent><AuthForm mode="register" defaultRole={role} onAuthenticated={(token, user) => { saveSession(token, user); router.push(next ?? (user.role === "supplier" ? "/supplier" : "/dashboard")); }} /><p className="mt-5 text-center text-sm text-muted-foreground">Already have an account? <Link className="font-medium text-foreground underline" href={next ? `/sign-in?next=${encodeURIComponent(next)}` : "/sign-in"}>Sign in</Link></p></CardContent></Card></main>;
}
