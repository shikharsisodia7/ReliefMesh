"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { AuthForm } from "@/components/auth-form";
import { CenteredColumn } from "@/components/layout/centered-column";
import { safeNext, saveSession } from "@/lib/session";
import { cn } from "@/lib/utils";

type Role = "coordinator" | "supplier";
const roles: { value: Role; title: string; detail: string }[] = [
  { value: "coordinator", title: "Coordinator", detail: "Run missions, compare quotes, and send purchase orders." },
  { value: "supplier", title: "Supplier", detail: "Answer RFQs and manage your quotes and orders." },
];

export function SignUpClient() {
  const router = useRouter();
  const params = useSearchParams();
  const [role, setRole] = useState<Role>(params.get("role") === "supplier" ? "supplier" : "coordinator");
  const next = safeNext(params.get("next"));
  return (
    <CenteredColumn title="Create your account" subtitle={role === "supplier" ? "Use the email address that received your RFQ invitation." : "You'll create your response organization next."}>
      {/* Two outlined radio cards; the chosen role sets the button label. */}
      <fieldset className="mb-6">
        <legend className="sr-only">Account type</legend>
        <div className="grid grid-cols-2 gap-3">
          {roles.map((option) => (
            <label key={option.value} className={cn("cursor-pointer rounded-md border p-3 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-solid has-[:focus-visible]:outline-ring", role === option.value && "border-foreground")}>
              <input type="radio" name="role" value={option.value} checked={role === option.value} onChange={() => setRole(option.value)} className="sr-only" aria-describedby={`role-${option.value}`} />
              <span className="block text-sm font-medium">{option.title}</span>
              <span id={`role-${option.value}`} className="mt-1 block text-xs text-muted-foreground">{option.detail}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <AuthForm key={role} mode="register" defaultRole={role} onAuthenticated={(token, user) => { saveSession(token, user); router.push(next ?? (user.role === "supplier" ? "/supplier" : "/dashboard")); }} />
      <p className="mt-6 text-center text-sm text-muted-foreground">Already have an account? <Link className="font-medium text-foreground hover:underline" href={next ? `/sign-in?next=${encodeURIComponent(next)}` : "/sign-in"}>Sign in</Link></p>
    </CenteredColumn>
  );
}
