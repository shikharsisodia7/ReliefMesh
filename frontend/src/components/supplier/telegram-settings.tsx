"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";

type SupplierProfile = { telegram_user_id?: string | null };
type LinkResult = { bot_url: string | null; bot_username: string | null; expires_at: string };

export function TelegramSettings({ token, compact = false }: { token: string; compact?: boolean }) {
  const client = useQueryClient();
  const [link, setLink] = useState<LinkResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmDisconnect, setConfirmDisconnect] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const profile = useQuery({
    queryKey: ["supplier-profile", token],
    queryFn: () => api<SupplierProfile>("/v1/supplier/profile", { token }),
    refetchInterval: link ? 3_000 : false,
  });

  const generateLink = async () => {
    setBusy(true);
    setError(null);
    setLink(null);
    try {
      const result = await api<LinkResult & { code: string }>("/v1/supplier/telegram/link-code", { method: "POST", token });
      setLink(result);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not create a Telegram link");
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async () => {
    setBusy(true);
    setError(null);
    try {
      await api("/v1/supplier/telegram", { method: "DELETE", token });
      setLink(null);
      await client.invalidateQueries({ queryKey: ["supplier-profile", token] });
      setConfirmDisconnect(false);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not disconnect Telegram");
    } finally {
      setBusy(false);
    }
  };

  const connected = Boolean(profile.data?.telegram_user_id);
  return (
    <section className={compact ? "rounded-lg border p-4" : "max-w-2xl rounded-lg border p-6"} aria-labelledby="telegram-settings-title">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 id="telegram-settings-title" className="text-base font-semibold">Telegram supplier updates</h2>
          <p className="mt-1 max-w-xl text-sm text-muted-foreground">
            Link your Telegram account to receive and respond to RFQs, update quotes, and report order status. Quote changes require confirmation; Telegram cannot approve purchases.
          </p>
        </div>
        {profile.isLoading ? <span className="text-sm text-muted-foreground">Checking connection…</span>
          : connected ? <span className="rounded-full bg-muted px-2.5 py-1 text-xs font-medium">Connected</span>
            : <span className="rounded-full bg-muted px-2.5 py-1 text-xs font-medium">Not connected</span>}
      </div>

      {profile.isError && <p role="alert" className="mt-3 text-sm text-critical">Couldn’t check Telegram status. <button type="button" className="underline" onClick={() => void profile.refetch()}>Retry</button></p>}
      {error && <p role="alert" className="mt-3 text-sm text-critical">{error}</p>}

      {connected ? (
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <p className="text-sm text-muted-foreground">Your supplier account is linked to Telegram.</p>
          {confirmDisconnect ? <>
            <span className="text-sm">Disconnect this Telegram account?</span>
            <Button type="button" variant="secondary" size="sm" disabled={busy} onClick={() => void disconnect()}>{busy ? "Disconnecting…" : "Confirm disconnect"}</Button>
            <Button type="button" variant="text" size="sm" disabled={busy} onClick={() => setConfirmDisconnect(false)}>Keep connected</Button>
          </> : <Button type="button" variant="secondary" size="sm" onClick={() => setConfirmDisconnect(true)}>Disconnect Telegram</Button>}
        </div>
      ) : (
        <div className="mt-4">
          {!link ? <Button type="button" size="sm" disabled={busy || profile.isLoading || profile.isError} onClick={() => void generateLink()}>
            {busy ? "Preparing secure link…" : "Connect Telegram"}
          </Button> : (
            <div className="space-y-3">
              {link.bot_url ? <a className="inline-flex h-9 items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:opacity-90" href={link.bot_url} target="_blank" rel="noreferrer">Open Telegram{link.bot_username ? ` · @${link.bot_username}` : ""}</a>
                : <p role="alert" className="text-sm text-critical">Telegram isn’t configured for this service yet. Ask your ReliefMesh administrator to finish bot setup, then try again.</p>}
              {link.bot_url && <p className="text-xs text-muted-foreground">The secure link expires at {new Date(link.expires_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}. In Telegram, press Start to finish linking. This page checks the connection automatically. If it expires, generate a new link.</p>}
              <Button type="button" variant="text" size="sm" onClick={() => setLink(null)}>Generate a fresh link</Button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
