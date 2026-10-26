"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import { useFetch } from "@/lib/hooks";
import { similarRows, similarSummary, type Market } from "@/lib/props";
import type { Similar } from "@/lib/types";

const SHOWN = 10;
const MODES = [["shots", "By shot profile"], ["position", "By position"]] as const;

const fmt = (v: number | null, nd = 1) => (v == null ? "–" : v.toFixed(nd));
const signed = (v: number | null, nd = 1) => (v == null ? "–" : v > 0 ? `+${v.toFixed(nd)}` : v.toFixed(nd));
const pctSigned = (v: number | null) => (v == null ? "–" : `${v > 0 ? "+" : ""}${Math.round(v * 100)}%`);
const tone = (v: number | null) => (v == null || v === 0 ? "text-muted" : v > 0 ? "text-win" : "text-live");
const shortDate = (d: string) => new Date(`${d}T12:00:00`).toLocaleDateString([], { month: "short", day: "2-digit" });

function DiffPill({ v }: { v: number | null }) {
  return (
    <span className="num inline-block min-w-14 rounded px-1.5 py-0.5 text-center text-xs font-bold text-white"
      style={{ background: v == null || v === 0 ? "var(--surface-2)" : v > 0 ? "var(--win-strong)" : "var(--live-strong)", color: v == null || v === 0 ? "var(--muted)" : "#fff" }}>
      {pctSigned(v)}
    </span>
  );
}

/** How players with a similar shot profile (shot zones + shot types) performed against this opponent this season. */
export function SimilarPlayersPanel({ playerId, season, oppId, market, oppAbbr }: {
  playerId: string | number; season: string; oppId: number | null; market: Market; oppAbbr: string | null;
}) {
  const [mode, setMode] = useState<"shots" | "position">("shots");
  const [showAll, setShowAll] = useState(false);
  const qs = new URLSearchParams({ season, mode });
  if (oppId != null) qs.set("opp", String(oppId));
  const { data, loading, notFound, error } = useFetch<Similar>(`/api/players/${playerId}/similar?${qs}`);

  const rows = useMemo(() => (data ? similarRows(data.games, data.players, market) : []), [data, market]);
  const summary = useMemo(() => similarSummary(rows, !!market.binary), [rows, market]);
  const shown = showAll ? rows : rows.slice(0, SHOWN);
  const name = oppAbbr ?? data?.opponent?.abbr ?? "the opponent";

  return (
    <section aria-label="Similar players" className="rounded-lg border border-line bg-surface p-3">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">Similar players · {market.label} vs {name}</h3>
        <div role="group" aria-label="How similar players are chosen" className="flex rounded-lg border border-line text-sm">
          {MODES.map(([v, l], i) => (
            <button key={v} aria-pressed={mode === v} onClick={() => setMode(v)}
              className={`min-h-9 px-3 ${mode === v ? "bg-surface2 font-semibold" : "text-muted hover:text-fg"} ${i === 0 ? "rounded-l-lg" : "rounded-r-lg"}`}>{l}</button>
          ))}
        </div>
      </div>

      {loading && !data && <div className="h-40 skeleton rounded bg-surface2" aria-busy />}
      {(notFound || (!loading && !data)) && (
        <p className="text-sm text-muted">{error ? `Can’t load similar players (${error}).` : "No shot profile for this player and season yet."}</p>
      )}

      {data && (
        <>
          <ul className="mb-3 flex flex-wrap gap-1.5" aria-label="Similar players, closest first">
            {data.players.map((p) => (
              <li key={p.player_id}>
                <Link href={`/players/${p.player_id}/stats`} title={`${p.name}: ${p.match}% match, ${p.games_vs_opp} game${p.games_vs_opp === 1 ? "" : "s"} vs ${name}`}
                  className="inline-flex min-h-8 items-center gap-1.5 rounded-full border border-line px-2.5 text-xs hover:bg-surface2">
                  <span className="font-medium">{p.name}</span><span className="num text-muted">{Math.round(p.match)}%</span>
                </Link>
              </li>
            ))}
            {!data.players.length && <li className="text-sm text-muted">No comparable players found.</li>}
          </ul>

          {!data.opponent ? (
            <p className="rounded border border-dashed border-line p-4 text-center text-sm text-muted">Choose an opponent to see how these players did against them.</p>
          ) : !rows.length ? (
            <p className="rounded border border-dashed border-line p-4 text-center text-sm text-muted">None of these players has a {market.label} result against {name} in {data.season}.</p>
          ) : (
            <>
              <dl className="num mb-3 flex flex-wrap gap-x-8 gap-y-2">
                {!market.binary && (
                  <>
                    <div><dt className="text-xs font-medium text-muted">AVG DIFF</dt><dd className={`text-lg font-bold ${tone(summary.avgDiff)}`}>{signed(summary.avgDiff, 2)}</dd></div>
                    <div><dt className="text-xs font-medium text-muted">AVG DIFF %</dt><dd className={`text-lg font-bold ${tone(summary.avgDiffPct)}`}>{pctSigned(summary.avgDiffPct)}</dd></div>
                  </>
                )}
                <div>
                  <dt className="text-xs font-medium text-muted">{market.binary ? "ACHIEVED" : "HIT RATE"}</dt>
                  <dd className={`text-lg font-bold ${summary.hit.pct == null ? "text-muted" : summary.hit.pct >= 0.55 ? "text-win" : summary.hit.pct <= 0.45 ? "text-live" : ""}`}>
                    {summary.hit.pct == null ? "–" : `${Math.round(summary.hit.pct * 100)}%`}
                    <span className="ml-1 text-sm font-semibold text-muted">({summary.hit.over}/{summary.hit.total})</span>
                  </dd>
                </div>
              </dl>

              <div className="overflow-x-auto">
                <table className="num w-full border-collapse text-sm">
                  <caption className="sr-only">Similar players’ {market.label} against {name}, compared with each player’s own season average</caption>
                  <thead>
                    <tr className="text-xs text-muted">
                      <th scope="col" className="py-1 text-left font-medium">DATE</th><th scope="col" className="hidden text-left font-medium sm:table-cell">TEAM</th>
                      <th scope="col" className="text-left font-medium">PLAYER</th>
                      {!market.binary && <th scope="col" className="text-right font-medium">AVG</th>}
                      <th scope="col" className="text-right font-medium">RESULT</th>
                      {!market.binary && <th scope="col" className="text-right font-medium">DIFF %</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {shown.map((r) => (
                      <tr key={`${r.game.player_id}-${r.game.game_id}`} className="border-t border-line">
                        <td className="py-1.5 text-muted">{shortDate(r.game.date)}</td>
                        <td className="hidden text-muted sm:table-cell">{r.game.team_abbr ?? "–"}</td>
                        <td className="font-medium"><Link href={`/players/${r.game.player_id}/stats`} className="hover:underline">{r.game.player_name}</Link></td>
                        {!market.binary && <td className="text-right text-muted">{fmt(r.avg)}</td>}
                        <td className="text-right font-semibold">{market.binary ? (r.value >= 1 ? "Yes" : "No") : r.value}</td>
                        {!market.binary && <td className="text-right"><DiffPill v={r.diffPct} /></td>}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {rows.length > SHOWN && (
                <button onClick={() => setShowAll((s) => !s)} className="mt-2 min-h-9 text-sm text-muted underline hover:text-fg">
                  {showAll ? "Show fewer" : `Show all ${rows.length} games`}
                </button>
              )}
            </>
          )}
          <p className="mt-3 text-xs text-muted">
            {mode === "shots"
              ? "Closest matches on shot zones and shot types (share of attempts), among players with a comparable role (20+ minutes and at least half this player’s shot volume)."
              : "Players at the same position, ordered by how closely their shot zones and shot types match."}
            {" "}Without sportsbook lines, each result is compared with that player’s own season average; hit rate counts games above it.
          </p>
        </>
      )}
    </section>
  );
}
