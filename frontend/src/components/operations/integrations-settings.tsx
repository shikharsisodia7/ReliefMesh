"use client";

import { useQuery } from "@tanstack/react-query";
import { CalendarDays, FolderArchive, Mail, MessageSquare, RefreshCw, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useState, type ReactNode } from "react";

import { DeliveryList } from "@/components/operations/delivery-list";
import { StatusDot, ago } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import type { CapabilityStatus, IntegrationState, IntegrationsView } from "@/lib/types";

const stateTone: Record<IntegrationState, "ok" | "warn" | "idle" | "critical"> = { LIVE: "ok", DEGRADED: "warn", NOT_CONFIGURED: "idle", BLOCKED: "critical" };
const stateText: Record<IntegrationState, string> = { LIVE: "text-ok", DEGRADED: "text-warn", NOT_CONFIGURED: "text-muted-foreground", BLOCKED: "text-critical" };

export function StateBadge({ state }: { state: IntegrationState }) {
  return <span className={`inline-flex items-center gap-1.5 font-mono text-[11px] font-semibold tracking-wider ${stateText[state]}`}><StatusDot tone={stateTone[state]} />{state.replace("_", " ")}</span>;
}

function CapabilityRow({ icon, name, status, onTest, testing, canTest }: { icon: ReactNode; name: string; status: CapabilityStatus; onTest?: () => void; testing?: boolean; canTest: boolean }) {
  return (
    <li className="grid gap-1 py-2.5 sm:grid-cols-[150px_140px_1fr_auto] sm:items-center">
      <span className="flex items-center gap-2 text-sm font-medium">{icon}{name}</span>
      <StateBadge state={status.state} />
      <span className="text-xs text-muted-foreground">{status.detail}{status.last_success ? ` · last success ${ago(status.last_success)}` : ""}</span>
      {canTest && onTest && status.state !== "NOT_CONFIGURED" && <Button size="sm" variant="outline" disabled={testing} onClick={onTest}>{testing ? "Testing…" : "Send test"}</Button>}
    </li>
  );
}

export function IntegrationsSettings({ organizationId, token, notice: initialNotice }: { organizationId: string; token: string; notice?: string | null }) {
  const view = useQuery({ queryKey: ["integrations", organizationId], refetchInterval: 8000, queryFn: () => api<IntegrationsView>(`/v1/organizations/${organizationId}/integrations`, { token }) });
  const [notice, setNotice] = useState<string | null>(initialNotice ?? null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [slackMode, setSlackMode] = useState<"bot" | "webhook">("bot");
  const [botToken, setBotToken] = useState("");
  const [channel, setChannel] = useState("#relief-operations");
  const [webhook, setWebhook] = useState("");
  const data = view.data;
  const isAdmin = data?.membership_role === "admin";

  const run = async (key: string, operation: () => Promise<string | void>) => {
    setBusy(key); setError(null); setNotice(null);
    try { const message = await operation(); if (message) setNotice(message); await view.refetch(); }
    catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Request failed"); }
    finally { setBusy(null); }
  };
  const connect = (provider: "google" | "slack") => run(`connect-${provider}`, async () => {
    const response = await api<{ authorization_url: string }>(`/v1/organizations/${organizationId}/integrations/${provider}/connect`, { method: "POST", token });
    window.location.assign(response.authorization_url);
  });
  const disconnect = (provider: "google" | "slack") => run(`disconnect-${provider}`, async () => {
    const response = await api<Record<string, unknown>>(`/v1/organizations/${organizationId}/integrations/${provider}/disconnect`, { method: "POST", token });
    return `${provider === "google" ? "Google" : "Slack"} disconnected${Object.values(response).includes(true) ? " and access revoked at the provider" : ""}.`;
  });
  const test = (channelName: "gmail" | "calendar" | "drive" | "slack") => run(`test-${channelName}`, async () => {
    const result = await api<{ status: string; last_error: string | null; provider_url: string | null }>(`/v1/organizations/${organizationId}/integrations/test`, { method: "POST", token, body: JSON.stringify({ channel: channelName }) });
    return `${channelName} test: ${result.status}${result.last_error ? ` — ${result.last_error}` : ""}`;
  });
  const saveSlack = () => run("slack-save", async () => {
    const body = slackMode === "bot" ? { bot_token: botToken, channel } : { webhook_url: webhook };
    await api(`/v1/organizations/${organizationId}/integrations/slack`, { method: "PUT", token, body: JSON.stringify(body) });
    setBotToken(""); setWebhook("");
    return "Slack connected — a test message was posted to the channel.";
  });

  if (view.isLoading) return <p className="text-muted-foreground">Loading integrations…</p>;
  if (view.isError || !data) return <p role="alert" className="rounded-md border border-critical/40 bg-critical/10 p-3 text-sm text-critical">{view.error?.message ?? "Integrations unavailable"}</p>;
  const google = data.google;
  const googleConnected = google.status === "CONNECTED" || google.status === "NEEDS_REAUTH";
  const slackConnected = data.slack.status === "CONNECTED" || data.slack.status === "NEEDS_REAUTH";
  return (
    <div className="space-y-5">
      {error && <p role="alert" className="rounded-md border border-critical/40 bg-critical/10 p-3 text-sm text-critical">{error}</p>}
      {notice && <p className="rounded-md border border-live/30 bg-live/10 p-3 text-sm text-live">{notice}</p>}
      {!isAdmin && <p className="text-sm text-muted-foreground">Only an organization administrator can connect or test integrations.</p>}

      <section aria-label="Google" className="rounded-xl border bg-card p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold">Google Workspace</h2>
            <p className="text-sm text-muted-foreground">
              {googleConnected ? <>Connected as <span className="font-mono">{google.account_email ?? "unknown account"}</span> {google.connected_at && `· ${ago(google.connected_at)}`}</>
                : google.oauth_configured ? "Not connected. ReliefMesh asks only for: send email, manage its own calendar, and files it creates."
                  : "NOT CONFIGURED on this server (no Google OAuth client)."}
            </p>
            {google.status === "NEEDS_REAUTH" && <p className="mt-1 text-sm text-critical">Google access expired or was revoked. Reconnect to resume Gmail, Calendar and Drive.</p>}
          </div>
          {isAdmin && google.oauth_configured && (
            <div className="flex gap-2">
              <Button size="sm" disabled={busy !== null} onClick={() => void connect("google")}>{googleConnected ? "Reconnect Google" : "Connect Google"}</Button>
              {googleConnected && <Button size="sm" variant="outline" disabled={busy !== null} onClick={() => void disconnect("google")}>Disconnect</Button>}
            </div>
          )}
        </div>
        <ul className="mt-2 divide-y divide-border/60">
          <CapabilityRow icon={<Mail className="size-4" />} name="Gmail" status={google.capabilities.gmail} canTest={isAdmin} testing={busy === "test-gmail"} onTest={() => void test("gmail")} />
          <CapabilityRow icon={<CalendarDays className="size-4" />} name="Calendar" status={google.capabilities.calendar} canTest={isAdmin} testing={busy === "test-calendar"} onTest={() => void test("calendar")} />
          <CapabilityRow icon={<FolderArchive className="size-4" />} name="Drive archive" status={google.capabilities.drive} canTest={isAdmin} testing={busy === "test-drive"} onTest={() => void test("drive")} />
        </ul>
        <p className="mt-2 text-[11px] text-tertiary">Email mode <span className="font-mono">{data.email.mode}</span> · transport <span className="font-mono">{data.email.transport}</span>{data.email.allowlist_active ? " · recipient allowlist active" : ""}. Calendar events land on a dedicated “ReliefMesh Operations” calendar; ReliefMesh stays the system of record.</p>
      </section>

      <section aria-label="Slack" className="rounded-xl border bg-card p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold">Slack</h2>
            <p className="text-sm text-muted-foreground">
              {slackConnected ? <>Workspace <span className="font-medium">{data.slack.team_name ?? "—"}</span> · channel <span className="font-mono">{data.slack.channel_name ?? "—"}</span> · {data.slack.mode === "bot" ? "app" : "incoming webhook"}</> : "Not connected."}
            </p>
            <p className="mt-1 text-[11px] text-tertiary">Slack messages are informational. There is no approve button, slash command or emoji approval — every approval happens inside ReliefMesh under the approver’s own sign-in.</p>
          </div>
          {isAdmin && (
            <div className="flex gap-2">
              {data.slack.oauth_configured && <Button size="sm" disabled={busy !== null} onClick={() => void connect("slack")}><MessageSquare className="size-3.5" />Add to Slack</Button>}
              {slackConnected && <Button size="sm" variant="outline" disabled={busy !== null} onClick={() => void test("slack")}>Send test</Button>}
              {slackConnected && <Button size="sm" variant="outline" disabled={busy !== null} onClick={() => void disconnect("slack")}>Disconnect</Button>}
            </div>
          )}
        </div>
        <div className="mt-2"><StateBadge state={data.slack.state} /> <span className="ml-2 text-xs text-muted-foreground">{data.slack.detail}</span></div>
        {isAdmin && !slackConnected && (
          <form className="mt-3 space-y-2 rounded-lg border border-dashed p-3" onSubmit={(event) => { event.preventDefault(); void saveSlack(); }}>
            <div className="flex gap-3 text-xs">
              <label className="flex items-center gap-1"><input type="radio" checked={slackMode === "bot"} onChange={() => setSlackMode("bot")} />Bot token + channel</label>
              <label className="flex items-center gap-1"><input type="radio" checked={slackMode === "webhook"} onChange={() => setSlackMode("webhook")} />Incoming webhook</label>
            </div>
            {slackMode === "bot" ? (
              <div className="flex flex-wrap items-end gap-2">
                <div><Label htmlFor="slack-token" className="text-xs">Bot token (xoxb-…)</Label><Input id="slack-token" type="password" autoComplete="off" required className="mt-1 h-8 w-72" value={botToken} onChange={(event) => setBotToken(event.target.value)} /></div>
                <div><Label htmlFor="slack-channel" className="text-xs">Channel</Label><Input id="slack-channel" required className="mt-1 h-8 w-52" value={channel} onChange={(event) => setChannel(event.target.value)} /></div>
                <Button size="sm" type="submit" disabled={busy !== null}>Verify & connect</Button>
              </div>
            ) : (
              <div className="flex flex-wrap items-end gap-2">
                <div><Label htmlFor="slack-webhook" className="text-xs">Webhook URL</Label><Input id="slack-webhook" type="password" autoComplete="off" required placeholder="https://hooks.slack.com/services/…" className="mt-1 h-8 w-96" value={webhook} onChange={(event) => setWebhook(event.target.value)} /></div>
                <Button size="sm" type="submit" disabled={busy !== null}>Verify & connect</Button>
              </div>
            )}
            <p className="text-[11px] text-tertiary">ReliefMesh posts one real test message before saving; credentials are encrypted at rest and never shown again.</p>
          </form>
        )}
      </section>

      <section aria-label="Recent deliveries" className="rounded-xl border bg-card p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-muted-foreground">Recent external deliveries</h2>
          <Button size="sm" variant="ghost" onClick={() => void view.refetch()}><RefreshCw className={view.isFetching ? "size-3.5 animate-spin" : "size-3.5"} />Refresh</Button>
        </div>
        <DeliveryList deliveries={data.deliveries} token={token} canRetry={isAdmin} onChanged={() => void view.refetch()} showMission />
      </section>
      <p className="text-[11px] text-tertiary"><RotateCcw className="mr-1 inline size-3" />Failed deliveries retry automatically with backoff; an administrator can retry a failed one after fixing the connection. <Link className="underline" href="/status">System status</Link> shows the same providers from the server’s side.</p>
    </div>
  );
}
