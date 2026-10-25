import { SignUpClient } from "@/components/sign-up-client";
import { Suspense } from "react";

export const instant = false;

export default function SignUpPage() {
  return <Suspense fallback={<main className="grid min-h-screen place-items-center text-sm text-muted-foreground">Loading registration…</main>}><SignUpClient /></Suspense>;
}
