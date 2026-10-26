"use client";
import { useCallback, useSyncExternalStore } from "react";
import { clearAlerts, EMPTY_ALERTS, markRead, parseAlerts, STORAGE_KEY, type AlertState } from "./alerts";

const listeners = new Set<() => void>();
let cachedRaw: string | null | undefined;
let cached: AlertState = EMPTY_ALERTS;

export function readAlerts(): AlertState {
  let raw: string | null = null;
  try { raw = localStorage.getItem(STORAGE_KEY); } catch { /* storage blocked: behave as no alerts */ }
  if (raw !== cachedRaw) { cachedRaw = raw; cached = parseAlerts(raw); } // same string -> same object, as useSyncExternalStore requires
  return cached;
}

export function writeAlerts(next: AlertState) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(next)); } catch { return; }
  listeners.forEach((l) => l());
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  window.addEventListener("storage", cb);
  return () => { listeners.delete(cb); window.removeEventListener("storage", cb); };
}

/** The alert list and its unread count, shared by the nav badge, the watchlist page and the background watcher. */
export function useAlertStore() {
  const state = useSyncExternalStore(subscribe, readAlerts, () => EMPTY_ALERTS);
  const read = useCallback(() => writeAlerts(markRead(readAlerts())), []);
  const clear = useCallback(() => writeAlerts(clearAlerts(readAlerts())), []);
  return { state, read, clear };
}
