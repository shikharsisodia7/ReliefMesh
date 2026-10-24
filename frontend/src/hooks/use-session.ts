"use client";

import { useSyncExternalStore } from "react";

import { readSession } from "@/lib/session";

const subscribe = (onStoreChange: () => void) => {
  window.addEventListener("storage", onStoreChange);
  return () => window.removeEventListener("storage", onStoreChange);
};

export function useSession() {
  return useSyncExternalStore(subscribe, readSession, () => null);
}
