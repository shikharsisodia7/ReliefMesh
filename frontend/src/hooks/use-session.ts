"use client";

import { useSyncExternalStore } from "react";

import { readSession } from "@/lib/session";

const subscribe = (onStoreChange: () => void) => {
  window.addEventListener("storage", onStoreChange);
  return () => window.removeEventListener("storage", onStoreChange);
};
const subscribeNoop = () => () => {};

export function useSession() {
  return useSyncExternalStore(subscribe, readSession, () => null);
}

// During hydration useSyncExternalStore reports the server snapshot (null), so a
// redirect effect must wait until the stored session has actually been read.
export function useHydrated() {
  return useSyncExternalStore(subscribeNoop, () => true, () => false);
}
