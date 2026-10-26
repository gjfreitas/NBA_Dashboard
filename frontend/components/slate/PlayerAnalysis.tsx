"use client";
import Link from "next/link";
import { useMemo } from "react";
import { useFetch } from "@/lib/hooks";
import { marketByKey, values } from "@/lib/props";
import { analyze } from "@/lib/slateAnalysis";
import type { PropsData } from "@/lib/types";

const f1 = (v: number | null) => (v == null ? "–" : v.toFixed(1));

/** Loaded only when a player row is opened: how the player has done against this line. */
export function PlayerAnalysis({ playerId, market, line, home, oppId, oppAbbr }: {
  playerId: number; market: string; line: number; home: boolean; oppId: number; oppAbbr: string | null;
}) {
  const { data, loading, error } = useFetch<PropsData>(`/api/players/${playerId}/games`);
  const a = useMemo(() => {
    if (!data) return null;
    const rows = values(data.games, marketByKey(market)).map(({ game, value }) => ({ date: game.date, season: game.season, home: game.home, opp_id: game.opp_id, value }));
    return analyze(rows, line, home, oppId);
  }, [data, market, line, home, oppId]);

  if (loading) return <div className="h-20 skeleton rounded bg-surface2" aria-busy />;
  if (error || !a || a.games === 0)
    return <p className="text-xs text-muted">No game history for this player yet.</p>;
  const pct = (h: { over: number; total: number }) => (h.total ? `${h.over}/${h.total} (${Math.round((h.over / h.total) * 100)}%)` : "–");
  return (
    <div className="space-y-2">
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4" aria-label={`Average ${marketByKey(market).label} against the line ${line}`}>
        {[["Last 5", f1(a.last5)], ["Last 10", f1(a.last10)], [`Season ${a.seasonLabel ?? ""}`.trim(), f1(a.season.avg)],
          [home ? "At home" : "On the road", `${f1(a.venue.avg)} · ${a.venue.n} g`], [`Vs ${oppAbbr ?? "opponent"}`, a.vsOpp.n ? `${f1(a.vsOpp.avg)} · ${a.vsOpp.n} g` : "–"],
          ["Over last 10", pct(a.hit10)], ["Over this season", pct(a.hitSeason)]].map(([k, v]) => (
          <div key={k}><dt className="text-xs text-muted">{k}</dt><dd className="num font-semibold">{v}</dd></div>
        ))}
      </dl>
      <div>
        <p className="mb-1 text-xs text-muted">Last {a.strip.length} games against {line} (oldest first)</p>
        <ol className="flex gap-1" aria-label="Last games: over or under the line">
          {a.strip.map((s, i) => (
            <li key={i} title={`${s.value}`} className={`num grid h-8 min-w-8 place-items-center rounded px-1 text-xs font-bold ${s.push ? "border border-line text-muted" : s.over ? "bg-win text-bg" : "bg-live text-white"}`}>
              {s.value}<span className="sr-only">{s.push ? " push" : s.over ? " over" : " under"}</span>
            </li>
          ))}
        </ol>
      </div>
      <Link href={`/players/${playerId}/stats`} className="inline-flex min-h-11 items-center text-sm underline hover:text-fg">Full stats, filters and splits →</Link>
    </div>
  );
}
