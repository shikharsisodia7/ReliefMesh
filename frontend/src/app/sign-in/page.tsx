"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { AuthForm } from "@/components/auth-form";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { saveSession } from "@/lib/session";

export default function SignInPage() {
  const router = useRouter();
  return <main className="grid min-h-screen place-items-center bg-slate-50 px-5"><Card className="w-full max-w-md"><CardHeader><CardTitle>Sign in to ReliefMesh</CardTitle><CardDescription>Use the account associated with your organization or supplier profile.</CardDescription></CardHeader><CardContent><AuthForm mode="login" onAuthenticated={(token, user) => { saveSession(token, user); router.push(user.role === "supplier" ? "/supplier" : "/dashboard"); }} /><p className="mt-5 text-center text-sm text-muted-foreground">New here? <Link className="font-medium text-foreground underline" href="/sign-up">Create an account</Link></p></CardContent></Card></main>;
}
