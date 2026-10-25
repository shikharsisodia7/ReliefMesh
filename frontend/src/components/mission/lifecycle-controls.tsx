"use client";

import { Menu } from "@base-ui/react/menu";
import { Ellipsis } from "lucide-react";
import { useState } from "react";

import { Dialog } from "@/components/patterns/overlays";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import type { Mission } from "@/lib/types";

function localInput(iso: string) {
  const date = new Date(iso);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

const itemClass = "flex w-full cursor-default items-center px-3 py-2 text-left text-sm outline-hidden select-none data-[highlighted]:bg-muted";

// The header's "⋯" menu: coordinator controls that change the procurement record itself.
// The calendar mirror follows via operations events.
export function MissionMenu({ mission, token, run, setNotice }: {
  mission: Mission; token: string; run: (operation: () => Promise<void>) => Promise<void>; setNotice: (message: string) => void;
}) {
  const [dialog, setDialog] = useState<"deadline" | "cancel" | null>(null);
  const [deadline, setDeadline] = useState(localInput(mission.delivery_deadline));
  const [reason, setReason] = useState("");
  const close = (open: boolean) => { if (!open) { setDialog(null); setReason(""); } };
  const changeDeadline = () => run(async () => {
    const response = await api<{ stale_plan_versions: number[] }>(`/v1/missions/${mission.id}/deadline`, { method: "PATCH", token, body: JSON.stringify({ delivery_deadline: new Date(deadline).toISOString(), reason: reason || null }) });
    close(false);
    setNotice(response.stale_plan_versions.length ? `Deadline updated. Plan v${response.stale_plan_versions.join(", v")} is stale and ReliefMesh is replanning against the new deadline.` : "Deadline updated.");
  });
  const cancel = () => run(async () => {
    const response = await api<{ open_purchase_orders: string[] }>(`/v1/missions/${mission.id}/cancel`, { method: "POST", token, body: JSON.stringify({ reason }) });
    close(false);
    setNotice(response.open_purchase_orders.length ? `Mission cancelled. Still-open purchase orders: ${response.open_purchase_orders.join(", ")} — cancel them with the supplier.` : "Mission cancelled.");
  });
  return (
    <>
      <Menu.Root>
        <Menu.Trigger aria-label="Mission actions" render={<Button variant="text" size="icon" />}><Ellipsis /></Menu.Trigger>
        <Menu.Portal>
          <Menu.Positioner align="end" sideOffset={6} className="z-50">
            <Menu.Popup className="w-56 rounded-lg border bg-background py-1.5 shadow-lg outline-hidden">
              <Menu.Item className={itemClass} onClick={() => setDialog("deadline")}>Change deadline…</Menu.Item>
              <Menu.Item className={itemClass} onClick={() => setDialog("cancel")}>Cancel mission…</Menu.Item>
            </Menu.Popup>
          </Menu.Positioner>
        </Menu.Portal>
      </Menu.Root>
      <Dialog open={dialog === "deadline"} onOpenChange={close} title="Change deadline" footer={<Button type="submit" form="deadline-form">Save deadline</Button>}>
        <form id="deadline-form" className="space-y-4" onSubmit={(event) => { event.preventDefault(); void changeDeadline(); }}>
          <div><Label htmlFor="new-deadline">New delivery deadline</Label><Input id="new-deadline" type="datetime-local" required className="mt-1.5" value={deadline} onChange={(event) => setDeadline(event.target.value)} /></div>
          <div><Label htmlFor="deadline-reason">Reason (optional)</Label><Input id="deadline-reason" className="mt-1.5" value={reason} onChange={(event) => setReason(event.target.value)} /></div>
          <p className="text-muted-foreground">If this changes what the current plan can deliver, the plan goes stale and ReliefMesh replans against the new deadline.</p>
        </form>
      </Dialog>
      <Dialog open={dialog === "cancel"} onOpenChange={close} title="Cancel mission" cancelLabel="Keep mission" footer={<Button type="submit" form="cancel-form">Cancel mission</Button>}>
        <form id="cancel-form" className="space-y-4" onSubmit={(event) => { event.preventDefault(); void cancel(); }}>
          <div><Label htmlFor="cancel-reason">Cancellation reason</Label><Input id="cancel-reason" required minLength={3} className="mt-1.5" value={reason} onChange={(event) => setReason(event.target.value)} /></div>
          <p className="text-muted-foreground">Plans become stale and no further replanning runs. Issued purchase orders must be cancelled with each supplier. This can&apos;t be undone.</p>
        </form>
      </Dialog>
    </>
  );
}
