"use client";

import { Dialog as BaseDialog } from "@base-ui/react/dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type OverlayProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  subtitle?: ReactNode;
  // Overrides the accessible name when it must differ from the visible title.
  label?: string;
  closeLabel?: string;
  // Footer actions; a plain "Cancel" (or cancelLabel) is added before them.
  footer?: ReactNode;
  cancelLabel?: string;
  children: ReactNode;
};

const scrim = "fixed inset-0 z-50 bg-foreground/20 transition-opacity duration-200 data-[starting-style]:opacity-0 data-[ending-style]:opacity-0 motion-reduce:transition-none";

function Header({ title, subtitle, label, closeLabel }: Pick<OverlayProps, "title" | "subtitle" | "label" | "closeLabel">) {
  const heading = "text-lg font-semibold leading-snug";
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="min-w-0">
        {label ? <h2 className={heading}>{title}</h2> : <BaseDialog.Title className={heading}>{title}</BaseDialog.Title>}
        {subtitle && <p className="mt-1 text-xs font-medium text-muted-foreground">{subtitle}</p>}
      </div>
      <BaseDialog.Close render={<Button variant="text" size="icon-sm" aria-label={closeLabel ?? "Close"} />}><X /></BaseDialog.Close>
    </div>
  );
}

function Footer({ cancelLabel = "Cancel", children }: { cancelLabel?: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-end gap-2 border-t px-6 py-4">
      <BaseDialog.Close render={<Button variant="text" />}>{cancelLabel}</BaseDialog.Close>
      {children}
    </div>
  );
}

// Right-side panel shared by Drawer (read-only detail) and SlideOver (forms).
function Sheet({ width, open, onOpenChange, label, footer, cancelLabel, children, ...header }: OverlayProps & { width: string }) {
  return (
    <BaseDialog.Root open={open} onOpenChange={(next) => onOpenChange(next)}>
      <BaseDialog.Portal>
        <BaseDialog.Backdrop className={scrim} />
        <BaseDialog.Popup
          aria-label={label}
          className={cn(
            "fixed inset-y-0 right-0 z-50 flex w-full flex-col bg-background shadow-xl outline-none md:rounded-l-lg",
            "transition-transform duration-200 ease-out data-[starting-style]:translate-x-full data-[ending-style]:translate-x-full motion-reduce:transition-none",
            width,
          )}
        >
          <div className="px-6 pt-6 pb-4"><Header label={label} {...header} /></div>
          <div className="flex-1 overflow-y-auto px-6 pb-6">{children}</div>
          {footer && <Footer cancelLabel={cancelLabel}>{footer}</Footer>}
        </BaseDialog.Popup>
      </BaseDialog.Portal>
    </BaseDialog.Root>
  );
}

// 420px read-only side panel: Explain changes, evidence records, supplier details.
export function Drawer(props: OverlayProps) {
  return <Sheet width="md:max-w-[420px]" {...props} />;
}

// 480px form panel with a sticky Cancel + primary footer: New mission, Revise quote.
export function SlideOver(props: OverlayProps) {
  return <Sheet width="md:max-w-[480px]" {...props} />;
}

// Centered 520px confirmation: the facts, one consequence sentence, then Cancel + primary.
export function Dialog({ open, onOpenChange, label, footer, cancelLabel, children, ...header }: OverlayProps) {
  return (
    <BaseDialog.Root open={open} onOpenChange={(next) => onOpenChange(next)}>
      <BaseDialog.Portal>
        <BaseDialog.Backdrop className={scrim} />
        <BaseDialog.Popup
          aria-label={label}
          className={cn(
            "fixed top-1/2 left-1/2 z-50 flex max-h-[calc(100dvh-32px)] w-[calc(100%-32px)] max-w-[520px] -translate-x-1/2 -translate-y-1/2 flex-col rounded-lg bg-background shadow-xl outline-none",
            "transition-[opacity,scale] duration-200 ease-out data-[starting-style]:scale-95 data-[starting-style]:opacity-0 data-[ending-style]:scale-95 data-[ending-style]:opacity-0 motion-reduce:transition-none",
          )}
        >
          <div className="px-6 pt-6 pb-4"><Header label={label} {...header} /></div>
          <div className="overflow-y-auto px-6 pb-6 text-sm">{children}</div>
          {footer && <Footer cancelLabel={cancelLabel}>{footer}</Footer>}
        </BaseDialog.Popup>
      </BaseDialog.Portal>
    </BaseDialog.Root>
  );
}
