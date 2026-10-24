"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { api } from "@/lib/api";
import type { SessionUser } from "@/lib/session";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const schema = z.object({
  email: z.email("Enter a valid email address"),
  password: z.string().min(12, "Use at least 12 characters"),
});

type Values = z.infer<typeof schema>;

export function AuthForm({
  mode,
  defaultRole,
  onAuthenticated,
}: {
  mode: "login" | "register";
  defaultRole?: "coordinator" | "supplier";
  onAuthenticated: (token: string, user: SessionUser) => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: "", password: "" } });
  const submit = form.handleSubmit(async (values) => {
    setError(null);
    try {
      const result = await api<{ access_token: string; user: SessionUser }>(`/v1/auth/${mode === "login" ? "login" : "register"}`, {
        method: "POST",
        body: JSON.stringify(mode === "register" ? { ...values, role: defaultRole } : values),
      });
      onAuthenticated(result.access_token, result.user);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to authenticate");
    }
  });
  const action = mode === "register" ? `Create ${defaultRole} account` : "Sign in";
  return (
    <form onSubmit={submit} className="grid gap-5" noValidate>
      <div className="grid gap-2">
        <Label htmlFor="email">Email</Label>
        <Input id="email" type="email" autoComplete="email" {...form.register("email")} />
        {form.formState.errors.email && <p className="text-sm text-destructive">{form.formState.errors.email.message}</p>}
      </div>
      <div className="grid gap-2">
        <Label htmlFor="password">Password</Label>
        <Input id="password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} {...form.register("password")} />
        {form.formState.errors.password && <p className="text-sm text-destructive">{form.formState.errors.password.message}</p>}
      </div>
      {error && <p role="alert" className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">{error}</p>}
      <Button type="submit" disabled={form.formState.isSubmitting}>{form.formState.isSubmitting ? "Working…" : action}</Button>
    </form>
  );
}
