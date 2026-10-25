"use client";

import { useState, type ReactNode } from "react";

import { Dialog } from "@/components/patterns/overlays";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

// Confirms a destructive action: the facts, one consequence sentence, an optional reason, then Cancel + the action.
export function ConfirmDialog({ open, onOpenChange, title, facts, consequence, reasonLabel, confirmLabel, onConfirm }: {
  open: boolean; onOpenChange: (open: boolean) => void; title: string; facts?: ReactNode; consequence: string;
  reasonLabel?: string; confirmLabel: string; onConfirm: (reason: string) => Promise<void>;
}) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const close = (next: boolean) => { onOpenChange(next); if (!next) setReason(""); };
  const confirm = async () => {
    setBusy(true);
    try { await onConfirm(reason.trim()); close(false); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={close} title={title} footer={<Button disabled={busy} onClick={() => void confirm()}>{busy ? "Working…" : confirmLabel}</Button>}>
      {facts && <div className="mb-3">{facts}</div>}
      <p>{consequence}</p>
      {reasonLabel && (
        <div className="mt-4">
          <Label htmlFor="confirm-reason">{reasonLabel} <span className="font-normal text-muted-foreground">(optional)</span></Label>
          <Textarea id="confirm-reason" rows={3} maxLength={1000} className="mt-1.5" value={reason} onChange={(event) => setReason(event.target.value)} />
        </div>
      )}
    </Dialog>
  );
}
