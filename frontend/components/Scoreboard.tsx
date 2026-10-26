"use client";
import type { Game, GameAvailabilitySummary } from "@/lib/types";
import { usePolling } from "@/lib/hooks";
import { GameCard } from "./GameCard";

const ORDER = { live: 0, pre: 1, final: 2 } as const;

export function Scoreboard() {
  const { data, error, loading } = usePolling<Game[]>("/api/scoreboard", 5000);
  // Lineups and injuries only matter before tip-off. The id list is stable between polls, so this doesn't refetch every 5 s.
  const preIds = (data ?? []).filter((g) => g.state === "pre").map((g) => g.id).sort().join(",");
  const { data: avail } = usePolling<GameAvailabilitySummary[]>(preIds ? `/api/availability/summary?game_ids=${preIds}` : null, 60_000);
  const byGame = new Map((avail ?? []).map((a) => [a.game_id, a]));
  if (loading)
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-busy>
        {[0, 1, 2, 3, 4, 5].map((i) => <div key={i} className="h-40 skeleton rounded-lg bg-surface" />)}
      </div>
    );
  if (!data)
    return <p role="alert" className="rounded-lg border border-line bg-surface p-4 text-muted">
      Can’t reach the data service{error ? ` (${error})` : ""}. Retrying…</p>;
  const games = [...data].sort((a, b) => ORDER[a.state] - ORDER[b.state] || (a.start_utc ?? "").localeCompare(b.start_utc ?? ""));
  if (!games.length) return <p className="text-muted">No games today.</p>;
  return (
    <>
      {error && <p role="status" className="mb-3 text-xs text-muted">Data delayed — showing last update.</p>}
      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {games.map((g, i) => <li key={g.id} className="reveal" style={{ "--i": i } as React.CSSProperties}><GameCard g={g} avail={byGame.get(g.id)} /></li>)}
      </ul>
    </>
  );
}
