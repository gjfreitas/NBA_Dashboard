"use client";
import { useEffect, useMemo } from "react";
import { addAlerts, allKeys, newAlerts, watching, type LineMoveIn } from "@/lib/alerts";
import { API } from "@/lib/hooks";
import type { InjuryChanges } from "@/lib/types";
import { readAlerts, writeAlerts } from "@/lib/useAlerts";
import { useWatchlist } from "@/lib/useWatchlist";

const EVERY_MS = 2 * 60_000;

/** Renders nothing. While any page is open and the watchlist is not empty, checks every couple of minutes for injury-report changes and
 *  prop-line moves about followed players and teams, stores them as alerts, and shows a browser notification if the visitor allowed it. */
export function AlertWatcher() {
  const { list } = useWatchlist();
  const signature = useMemo(() => JSON.stringify(list.items.map((i) => [i.kind, i.id, i.sub ?? ""])), [list]);

  useEffect(() => {
    const w = watching(list.items);
    if (!w.players.size && !w.teamIds.size) return;
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const [c, m] = await Promise.all([
          fetch(`${API}/api/injuries/changes?hours=12`, { cache: "no-store" }).then((r) => (r.ok ? (r.json() as Promise<InjuryChanges>) : null)),
          fetch(`${API}/api/lines/moves?min_move=1`, { cache: "no-store" }).then((r) => (r.ok ? (r.json() as Promise<LineMoveIn[]>) : null)),
        ]);
        if (stop || (!c && !m)) return;
        const changes = c?.changes ?? [], moves = m ?? [];
        const state = readAlerts();
        if (!state.started) {
          writeAlerts({ ...state, started: true, seen: allKeys(changes, moves) }); // first run: today's existing news is not an alert
        } else {
          const fresh = newAlerts(changes, moves, w, new Set(state.seen), new Date().toISOString());
          if (fresh.length) {
            writeAlerts(addAlerts(state, fresh));
            if (typeof Notification !== "undefined" && Notification.permission === "granted")
              for (const a of fresh.slice(0, 3)) new Notification("NBA Live", { body: a.text, tag: a.key });
          }
        }
      } catch { /* offline or the relay is down: try again next time */ }
      if (!stop) timer = setTimeout(tick, document.hidden ? EVERY_MS * 4 : EVERY_MS);
    };
    tick();
    return () => { stop = true; clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `signature` stands for list.items: re-run only when who is followed changes
  }, [signature]);

  return null;
}
