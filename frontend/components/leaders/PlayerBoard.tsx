"use client";
import { SetupHint } from "../SetupHint";
import Link from "next/link";
import { useFetch } from "@/lib/hooks";
import { formatStat, modeApplies, playerStat, type Kind, type LeadersState } from "@/lib/leaders";
import type { PlayerLeader, PlayerLeaders } from "@/lib/types";
import { Headshot } from "../Headshot";

interface Col { key: keyof PlayerLeader & string; short: string; kind: Kind; sortKey?: string }

// Columns every row shows. `sortKey` is the API stat a header click switches to.
const COLUMNS: Col[] = [
  { key: "gp", short: "GP", kind: "total" },
  { key: "min", short: "MIN", kind: "count", sortKey: "min" },
  { key: "pts", short: "PTS", kind: "count", sortKey: "pts" },
  { key: "reb", short: "REB", kind: "count", sortKey: "reb" },
  { key: "ast", short: "AST", kind: "count", sortKey: "ast" },
  { key: "stl", short: "STL", kind: "count", sortKey: "stl" },
  { key: "blk", short: "BLK", kind: "count", sortKey: "blk" },
  { key: "tov", short: "TOV", kind: "count", sortKey: "tov" },
  { key: "fg_pct", short: "FG%", kind: "pct", sortKey: "fg_pct" },
  { key: "fg3_pct", short: "3P%", kind: "pct", sortKey: "fg3_pct" },
  { key: "ft_pct", short: "FT%", kind: "pct" , sortKey: "ft_pct" },
  { key: "ts_pct", short: "TS%", kind: "pct", sortKey: "ts_pct" },
];

function TopCard({ r, label, fmt }: { r: PlayerLeader; label: string; fmt: string }) {
  return (
    <li className="min-w-0 rounded-lg border border-line bg-surface p-3 text-center">
      <div className="text-xs font-semibold text-muted">#{r.rank}</div>
      <Link href={`/players/${r.player_id}/stats`} className="mt-1 flex flex-col items-center gap-1 hover:underline">
        <Headshot id={r.player_id} name={r.name} width={72} />
        <span className="w-full truncate text-sm font-semibold">{r.name}</span>
      </Link>
      <div className="truncate text-xs text-muted">{[r.team_abbr, r.position].filter(Boolean).join(" · ")}</div>
      <div className="num mt-1 text-2xl font-bold">{fmt}</div>
      <div className="text-xs text-muted">{label}</div>
    </li>
  );
}

export function PlayerBoard({ state, update }: { state: LeadersState; update: (p: Partial<LeadersState>) => void }) {
  const def = playerStat(state.stat);
  const mode = modeApplies(def) ? state.mode : "pg";
  const qs = new URLSearchParams({ stat: state.stat, season_type: state.type, mode, qualified: String(state.qualified), limit: String(state.limit) });
  if (state.season) qs.set("season", state.season);
  const { data, loading, notFound, error } = useFetch<PlayerLeaders>(`/api/leaders/players?${qs}`, { keepPrevious: true });

  if (!data && loading) return <div className="h-96 skeleton rounded-lg bg-surface" aria-busy />;
  if (!data)
    return (
      <p role="alert" className="rounded-lg border border-dashed border-line p-6 text-sm text-muted">
        {notFound ? <>No game logs are loaded. <SetupHint cmd={`python -m nbadash.ingest props`} />.</> : `Can’t load the leaderboard${error ? ` (${error})` : ""}.`}
      </p>
    );

  const inColumns = COLUMNS.some((c) => c.sortKey === state.stat);
  const fmtValue = (v: number | null) => formatStat(def.kind, v, mode);
  const top = data.rows.slice(0, 3);
  const subtitle = mode === "total" ? "total" : def.kind === "count" ? "per game" : "";

  return (
    <div className={`space-y-4 transition-opacity ${loading ? "opacity-60" : ""}`} aria-busy={loading}>
      {data.rows.length === 0 ? (
        <p className="rounded-lg border border-dashed border-line p-6 text-center text-sm text-muted">
          No players {data.qualified ? "qualify" : "have games"} for {def.label.toLowerCase()} in {data.season}{state.type === "playoffs" ? " playoffs" : ""} yet.
          {data.qualified && " Untick “Qualified players only” to include everyone."}
        </p>
      ) : (
        <>
          <ol className="grid grid-cols-3 gap-2 sm:gap-3" aria-label={`Top ${top.length} for ${def.label}`}>
            {top.map((r) => <TopCard key={r.player_id} r={r} label={`${def.label} ${subtitle}`.trim()} fmt={fmtValue(r.value)} />)}
          </ol>

          <div className="overflow-x-auto rounded-lg border border-line bg-surface">
            <table className="num w-full min-w-[720px] border-collapse text-sm">
              <caption className="sr-only">{def.label} leaders, {data.season}{state.type === "playoffs" ? " playoffs" : ""}, {mode === "total" ? "totals" : "per game"}</caption>
              <thead>
                <tr className="border-b border-line text-xs text-muted">
                  <th scope="col" className="w-10 px-2 py-2 text-right font-medium">#</th>
                  <th scope="col" className="sticky left-0 bg-surface px-2 py-2 text-left font-medium">Player</th>
                  {COLUMNS.map((c) => {
                    const active = c.sortKey === state.stat;
                    return (
                      <th key={c.key} scope="col" aria-sort={active ? "descending" : undefined} className={`px-2 py-2 text-right font-medium ${active ? "bg-surface2 text-fg" : ""}`}>
                        {c.sortKey ? (
                          <button className="min-h-8 px-1 hover:text-fg" onClick={() => update({ stat: c.sortKey!, limit: 25 })} aria-label={`Rank by ${c.short}`}>{c.short}{active ? " ▾" : ""}</button>
                        ) : c.short}
                      </th>
                    );
                  })}
                  {!inColumns && <th scope="col" aria-sort="descending" className="bg-surface2 px-2 py-2 text-right font-medium text-fg">{def.short} ▾</th>}
                </tr>
              </thead>
              <tbody>
                {data.rows.map((r) => (
                  <tr key={r.player_id} className="border-b border-line last:border-0">
                    <td className="px-2 py-1.5 text-right text-muted">{r.rank}</td>
                    <th scope="row" className="sticky left-0 whitespace-nowrap bg-surface px-2 py-1.5 text-left font-medium">
                      <Link href={`/players/${r.player_id}/stats`} className="inline-flex min-h-9 items-center gap-2 hover:underline">
                        <Headshot id={r.player_id} name={r.name} width={40} />
                        <span>{r.name} <span className="text-xs font-normal text-muted">{r.team_abbr}</span></span>
                      </Link>
                    </th>
                    {COLUMNS.map((c) => {
                      const v = r[c.key] as number | null;
                      const active = c.sortKey === state.stat;
                      // GP is a plain count; counting stats follow the per-game / totals switch
                      const text = c.key === "gp" ? String(v) : formatStat(c.kind, v, mode);
                      return <td key={c.key} className={`px-2 py-1.5 text-right ${active ? "bg-surface2 font-bold" : ""}`}>{text}</td>;
                    })}
                    {!inColumns && <td className="bg-surface2 px-2 py-1.5 text-right font-bold">{fmtValue(r.value)}</td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
            <span role="status">Showing {data.rows.length} of {data.total}.{data.requirement ? ` Qualified: ${data.requirement}.` : ""}</span>
            {data.rows.length < data.total && (
              <button className="min-h-11 rounded-lg border border-line bg-surface px-4 text-sm font-semibold text-fg hover:bg-surface2" onClick={() => update({ limit: Math.min(state.limit + 25, 300) })}>
                Show more
              </button>
            )}
          </div>
        </>
      )}
    </div>
  );
}
