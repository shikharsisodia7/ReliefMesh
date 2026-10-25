"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import type { Mission } from "@/lib/types";

function localInput(iso: string) {
  const date = new Date(iso);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

// Coordinator controls that change the procurement record itself. The calendar mirror follows via operations events.
export function MissionLifecycleControls({ mission, token, run, setNotice }: {
  mission: Mission; token: string; run: (operation: () => Promise<void>) => Promise<void>; setNotice: (message: string) => void;
}) {
  const [open, setOpen] = useState<"deadline" | "cancel" | null>(null);
  const [deadline, setDeadline] = useState(localInput(mission.delivery_deadline));
  const [reason, setReason] = useState("");
  const [confirming, setConfirming] = useState(false);
  if (mission.status === "cancelled") {
    return <p role="status" className="rounded-md border border-critical/40 bg-critical/10 p-3 text-sm text-critical">This mission is cancelled. Plans are stale and no further replanning runs; issued purchase orders must be cancelled with each supplier.</p>;
  }
  const changeDeadline = () => run(async () => {
    const response = await api<{ stale_plan_versions: number[] }>(`/v1/missions/${mission.id}/deadline`, { method: "PATCH", token, body: JSON.stringify({ delivery_deadline: new Date(deadline).toISOString(), reason: reason || null }) });
    setOpen(null); setReason("");
    setNotice(response.stale_plan_versions.length ? `Deadline updated. Plan v${response.stale_plan_versions.join(", v")} is stale and ReliefMesh is replanning against the new deadline.` : "Deadline updated.");
  });
  const cancel = () => run(async () => {
    const response = await api<{ open_purchase_orders: string[] }>(`/v1/missions/${mission.id}/cancel`, { method: "POST", token, body: JSON.stringify({ reason }) });
    setOpen(null); setConfirming(false);
    setNotice(response.open_purchase_orders.length ? `Mission cancelled. Still-open purchase orders: ${response.open_purchase_orders.join(", ")} — cancel them with the supplier.` : "Mission cancelled.");
  });
  return (
    <div className="flex flex-wrap items-end gap-2 text-sm">
      <Button size="sm" variant="secondary" onClick={() => { setOpen(open === "deadline" ? null : "deadline"); setConfirming(false); }}>Change deadline</Button>
      <Button size="sm" variant="secondary" className="border-critical/40 text-critical" onClick={() => { setOpen(open === "cancel" ? null : "cancel"); setConfirming(false); }}>Cancel mission</Button>
      {open === "deadline" && (
        <form className="flex flex-wrap items-end gap-2" onSubmit={(event) => { event.preventDefault(); void changeDeadline(); }}>
          <div><Label htmlFor="new-deadline" className="text-xs">New delivery deadline</Label><Input id="new-deadline" type="datetime-local" required className="mt-1 h-8" value={deadline} onChange={(event) => setDeadline(event.target.value)} /></div>
          <div><Label htmlFor="deadline-reason" className="text-xs">Reason (optional)</Label><Input id="deadline-reason" className="mt-1 h-8 w-56" value={reason} onChange={(event) => setReason(event.target.value)} /></div>
          <Button size="sm" type="submit">Save deadline</Button>
        </form>
      )}
      {open === "cancel" && (
        <form className="flex flex-wrap items-end gap-2" onSubmit={(event) => { event.preventDefault(); if (confirming) void cancel(); else setConfirming(true); }}>
          <div><Label htmlFor="cancel-reason" className="text-xs">Cancellation reason</Label><Input id="cancel-reason" required minLength={3} className="mt-1 h-8 w-72" value={reason} onChange={(event) => setReason(event.target.value)} /></div>
          <Button size="sm" type="submit" variant={confirming ? "primary" : "secondary"}>{confirming ? "Confirm cancellation" : "Cancel mission…"}</Button>
        </form>
      )}
    </div>
  );
}
