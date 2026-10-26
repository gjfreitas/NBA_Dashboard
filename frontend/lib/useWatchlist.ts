"use client";
import { useCallback, useSyncExternalStore } from "react";
import { EMPTY, STORAGE_KEY, parseWatchlist, toggleItem, type WatchItem, type Watchlist } from "./watchlist";

const listeners = new Set<() => void>();
let cachedRaw: string | null | undefined;
let cached: Watchlist = EMPTY;

function read(): Watchlist {
  let raw: string | null = null;
  try { raw = localStorage.getItem(STORAGE_KEY); } catch { /* storage blocked: behave as an empty list */ }
  if (raw !== cachedRaw) { cachedRaw = raw; cached = parseWatchlist(raw); } // same string -> same object, as useSyncExternalStore requires
  return cached;
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  window.addEventListener("storage", cb); // another tab changed it
  return () => { listeners.delete(cb); window.removeEventListener("storage", cb); };
}

/** The followed players and teams, and a toggle. Server render and the first client render both see an empty list. */
export function useWatchlist() {
  const list = useSyncExternalStore(subscribe, read, () => EMPTY);
  const toggle = useCallback((item: WatchItem) => {
    const next = toggleItem(read(), item);
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(next)); } catch { return; }
    listeners.forEach((l) => l());
  }, []);
  return { list, toggle };
}
