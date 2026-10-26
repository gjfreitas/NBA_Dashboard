"use client";
import { useEffect, useRef, useState } from "react";
import type { Game, Play } from "./types";

export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Loadable<T> = { data: T | null; error: string | null; loading: boolean; notFound: boolean };

type Fetched = { status: number; body: unknown };
const recent = new Map<string, { at: number; p: Promise<Fetched> }>();

/** Several components poll the same endpoint (the scoreboard has four consumers): requests within 2 s share one fetch. */
function fetchShared(path: string): Promise<Fetched> {
  const hit = recent.get(path);
  if (hit && Date.now() - hit.at < 2000) return hit.p;
  const p = fetch(`${API}${path}`, { cache: "no-store" }).then(async (r) => ({ status: r.status, body: r.ok ? await r.json() : null }));
  recent.set(path, { at: Date.now(), p });
  p.catch(() => recent.delete(path));
  return p;
}

/** Polls a JSON endpoint. 404 => notFound (e.g. box score before tip-off). Keeps last data on errors. Pauses while the tab is hidden and refreshes when it returns. */
export function usePolling<T>(path: string | null, intervalMs: number): Loadable<T> {
  const [s, setS] = useState<Loadable<T>>({ data: null, error: null, loading: true, notFound: false });
  useEffect(() => {
    if (!path) return;
    let stop = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      clearTimeout(timer);
      try {
        const r = await fetchShared(path);
        if (stop) return;
        if (r.status === 404) setS((p) => ({ ...p, loading: false, notFound: true, error: null }));
        else if (r.status < 200 || r.status > 299) throw new Error(`HTTP ${r.status}`);
        else setS({ data: r.body as T, error: null, loading: false, notFound: false });
      } catch (e) {
        if (!stop) setS((p) => ({ ...p, loading: false, error: e instanceof Error ? e.message : "error" }));
      }
      if (!stop && !document.hidden) timer = setTimeout(tick, intervalMs);
    };
    const onVisible = () => { if (!document.hidden && !stop) tick(); };
    document.addEventListener("visibilitychange", onVisible);
    tick();
    return () => { stop = true; clearTimeout(timer); document.removeEventListener("visibilitychange", onVisible); };
  }, [path, intervalMs]);
  return s;
}

export interface PlayStream { plays: Play[]; game: Game | null; connected: boolean; ended: boolean; available: boolean }

/** SSE live feed. Plays are upserted by id (the NBA edits past actions). */
export function usePlayStream(gameId: string): PlayStream {
  const [state, setState] = useState<PlayStream>({ plays: [], game: null, connected: false, ended: false, available: true });
  const map = useRef(new Map<number, Play>());
  useEffect(() => {
    map.current = new Map();
    const es = new EventSource(`${API}/api/games/${gameId}/stream`);
    es.onopen = () => setState((s) => ({ ...s, connected: true }));
    es.onerror = () => setState((s) => ({ ...s, connected: false }));
    es.addEventListener("plays", (e) => {
      for (const p of JSON.parse((e as MessageEvent).data) as Play[]) map.current.set(p.id, p);
      const plays = [...map.current.values()].sort((a, b) => a.order - b.order || a.id - b.id);
      setState((s) => ({ ...s, plays, available: true }));
    });
    es.addEventListener("removed", (e) => { // plays the NBA deleted after the fact
      for (const id of JSON.parse((e as MessageEvent).data) as number[]) map.current.delete(id);
      const plays = [...map.current.values()].sort((a, b) => a.order - b.order || a.id - b.id);
      setState((s) => ({ ...s, plays }));
    });
    es.addEventListener("game", (e) => setState((s) => ({ ...s, game: JSON.parse((e as MessageEvent).data), available: true })));
    es.addEventListener("status", () => setState((s) => ({ ...s, available: false })));
    es.addEventListener("end", () => { es.close(); setState((s) => ({ ...s, ended: true, connected: false })); });
    return () => es.close();
  }, [gameId]);
  return state;
}

/** One-shot fetch that refetches when the path changes. */
export function useFetch<T>(path: string | null, opts: { keepPrevious?: boolean } = {}): Loadable<T> {
  const [s, setS] = useState<Loadable<T>>({ data: null, error: null, loading: path !== null, notFound: false });
  const [prev, setPrev] = useState(path);
  if (prev !== path) { // reset during render when the target changes (avoids setState-in-effect)
    setPrev(path);
    // keepPrevious: leave the old data on screen (marked loading) so filters and "show more" don't flash a skeleton
    setS((p) => ({ data: opts.keepPrevious ? p.data : null, error: null, loading: path !== null, notFound: false }));
  }
  useEffect(() => {
    if (!path) return;
    const ctl = new AbortController();
    fetch(`${API}${path}`, { signal: ctl.signal })
      .then(async (r) => {
        if (r.status === 404) setS({ data: null, error: null, loading: false, notFound: true });
        else if (!r.ok) throw new Error(`HTTP ${r.status}`);
        else setS({ data: await r.json(), error: null, loading: false, notFound: false });
      })
      .catch((e) => { if (!ctl.signal.aborted) setS({ data: null, error: String(e.message ?? e), loading: false, notFound: false }); });
    return () => ctl.abort();
  }, [path]);
  return s;
}
