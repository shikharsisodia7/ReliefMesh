"use client";

import { useEffect, useSyncExternalStore } from "react";

// One quiet toast at a time, bottom center, gone after 4 s.
type Toast = { id: number; message: string };
let current: Toast | null = null;
const listeners = new Set<() => void>();

function emit() {
  for (const listener of listeners) listener();
}

export function showToast(message: string) {
  current = { id: Date.now(), message };
  emit();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export function Toaster() {
  const toast = useSyncExternalStore(subscribe, () => current, () => null);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => { if (current?.id === toast.id) { current = null; emit(); } }, 4000);
    return () => clearTimeout(timer);
  }, [toast]);
  return (
    <div aria-live="polite" role="status" className="pointer-events-none fixed inset-x-0 bottom-6 z-50 flex justify-center px-4">
      {toast && <p key={toast.id} className="rounded-lg border bg-background px-4 py-2.5 text-sm font-medium shadow-lg motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-2">{toast.message}</p>}
    </div>
  );
}
