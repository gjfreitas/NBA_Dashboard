"use client";
import { useState } from "react";
import { useFetch } from "@/lib/hooks";
import type { GameLogRow } from "@/lib/types";
import { usePlayer } from "./PlayerProvider";
import { SeasonPicker, useDefaultSelection, type Selection } from "./SeasonPicker";

function PointsBars({ rows }: { rows: GameLogRow[] }) {
  const chrono = [...rows].reverse();
  const max = Math.max(10, ...chrono.map((r) => r.pts));
  const W = 640, H = 90, gap = 2;
  const bw = Math.min(18, Math.max(2, (W - gap * (chrono.length - 1)) / chrono.length));
  const avg = chrono.reduce((a, r) => a + r.pts, 0) / (chrono.length || 1);
  return (
    <figure className="rounded-lg border border-line bg-surface p-3">
      <figcaption className="mb-1 flex justify-between text-xs text-muted"><span>Points per game</span><span>avg {avg.toFixed(1)}</span></figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Points per game over ${chrono.length} games, average ${avg.toFixed(1)}`} className="w-full">
        {chrono.map((r, i) => (
          <rect key={r.game_id} x={i * (bw + gap)} width={bw} y={H - (r.pts / max) * H} height={(r.pts / max) * H}
            fill={r.result === "W" ? "var(--win)" : "var(--muted)"} opacity={0.85}>
            <title>{`${r.date} ${r.matchup}: ${r.pts} pts`}</title>
          </rect>
        ))}
        <line x1={0} x2={W} y1={H - (avg / max) * H} y2={H - (avg / max) * H} stroke="var(--accent)" strokeDasharray="4 3" />
      </svg>
      <p className="mt-1 text-xs text-muted">Green bars are wins.</p>
    </figure>
  );
}

export function GameLogView() {
  const { data: p, id } = usePlayer();
  const [picked, setPicked] = useState<Selection | null>(null);
  const avail = p?.available.filter((a) => a.games > 0) ?? [];
  const sel = useDefaultSelection(avail, picked);
  const { data: rows, loading } = useFetch<GameLogRow[]>(sel ? `/api/players/${id}/gamelog?season=${sel.season}&season_type=${sel.type}` : null);
  if (!p) return <div className="h-64 skeleton rounded-lg bg-surface" aria-busy />;
  if (!sel) return <p className="rounded-lg border border-dashed border-line p-6 text-sm text-muted">No game logs loaded for this player yet.</p>;
  const td = "px-2 py-2 text-right";
  return (
    <div className="space-y-3">
      <SeasonPicker available={avail} value={sel} onChange={setPicked} count="games" />
      {loading || !rows ? <div className="h-64 skeleton rounded-lg bg-surface" aria-busy /> : (
        <>
          <PointsBars rows={rows} />
          <div className="overflow-x-auto rounded-lg border border-line bg-surface">
            <table className="num w-full min-w-[720px] border-collapse text-sm">
              <caption className="sr-only">Game log</caption>
              <thead>
                <tr className="border-b border-line text-xs text-muted">
                  <th scope="col" className="sticky left-0 bg-surface px-3 py-2 text-left font-medium">Date</th>
                  <th scope="col" className="px-2 py-2 text-left font-medium">Matchup</th>
                  {["", "MIN", "PTS", "REB", "AST", "STL", "BLK", "TO", "FG", "3P", "FT", "+/−"].map((h, i) => (
                    <th key={i} scope="col" className="px-2 py-2 text-right font-medium">{h || "W/L"}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.game_id} className="border-b border-line">
                    <th scope="row" className="sticky left-0 whitespace-nowrap bg-surface px-3 py-2 text-left font-normal text-muted">{r.date.slice(5)}</th>
                    <td className="whitespace-nowrap px-2 py-2">{r.matchup}</td>
                    <td className={`${td} font-semibold ${r.result === "W" ? "text-win" : "text-muted"}`}>{r.result ?? "–"}</td>
                    <td className={td}>{Math.round(r.min)}</td>
                    <td className={`${td} font-semibold`}>{r.pts}</td>
                    <td className={td}>{r.reb}</td><td className={td}>{r.ast}</td><td className={td}>{r.stl}</td>
                    <td className={td}>{r.blk}</td><td className={td}>{r.tov}</td>
                    <td className={td}>{r.fgm}-{r.fga}</td><td className={td}>{r.fg3m}-{r.fg3a}</td><td className={td}>{r.ftm}-{r.fta}</td>
                    <td className={td}>{r.plus_minus > 0 ? `+${r.plus_minus}` : r.plus_minus}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
