"use client";
import { SetupHint } from "../SetupHint";
import Link from "next/link";
import { useFetch } from "@/lib/hooks";
import { formatStat, teamStat, type LeadersState } from "@/lib/leaders";
import type { TeamLeaders } from "@/lib/types";
import { TeamLogo } from "../Logo";

// Columns shown for every team (the selected stat is highlighted; if it isn't among them it is appended).
const SHOWN = ["net_rtg", "off_rtg", "def_rtg", "pace", "pts", "reb", "ast", "fg_pct", "fg3_pct", "ts_pct"];

export function TeamBoard({ state, update }: { state: LeadersState; update: (p: Partial<LeadersState>) => void }) {
  const def = teamStat(state.stat);
  const qs = new URLSearchParams({ stat: state.stat });
  if (state.season) qs.set("season", state.season);
  const { data, loading, notFound, error } = useFetch<TeamLeaders>(`/api/leaders/teams?${qs}`, { keepPrevious: true });

  if (!data && loading) return <div className="h-96 skeleton rounded-lg bg-surface" aria-busy />;
  if (!data)
    return (
      <p role="alert" className="rounded-lg border border-dashed border-line p-6 text-sm text-muted">
        {notFound ? <>Team stats aren’t loaded. <SetupHint cmd={`python -m nbadash.ingest teams`} />.</> : `Can’t load team rankings${error ? ` (${error})` : ""}.`}
      </p>
    );

  const keys = SHOWN.includes(state.stat) ? SHOWN : [...SHOWN, state.stat];
  return (
    <div className={`space-y-3 transition-opacity ${loading ? "opacity-60" : ""}`} aria-busy={loading}>
      <div className="overflow-x-auto rounded-lg border border-line bg-surface">
        <table className="num w-full min-w-[720px] border-collapse text-sm">
          <caption className="sr-only">Teams ranked by {def.label}, {data.season}</caption>
          <thead>
            <tr className="border-b border-line text-xs text-muted">
              <th scope="col" className="w-10 px-2 py-2 text-right font-medium">#</th>
              <th scope="col" className="sticky left-0 bg-surface px-2 py-2 text-left font-medium">Team</th>
              <th scope="col" className="px-2 py-2 text-right font-medium">W-L</th>
              {keys.map((k) => {
                const d = teamStat(k);
                const active = k === state.stat;
                return (
                  <th key={k} scope="col" aria-sort={active ? (d.lower ? "ascending" : "descending") : undefined} className={`px-2 py-2 text-right font-medium ${active ? "bg-surface2 text-fg" : ""}`}>
                    <button className="min-h-8 px-1 hover:text-fg" onClick={() => update({ stat: k })} aria-label={`Rank by ${d.label}${d.lower ? " (lowest is best)" : ""}`}>
                      {d.short}{active ? (d.lower ? " ▴" : " ▾") : ""}
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r) => (
              <tr key={r.team_id} className="border-b border-line last:border-0">
                <td className="px-2 py-1.5 text-right text-muted">{r.rank}</td>
                <th scope="row" className="sticky left-0 whitespace-nowrap bg-surface px-2 py-1.5 text-left font-medium">
                  <Link href={`/teams/${r.team_id}`} className="inline-flex min-h-9 items-center gap-2 hover:underline">
                    <TeamLogo id={r.team_id} tricode={r.abbr ?? ""} size={28} />
                    <span className="hidden sm:inline">{r.name}</span><span className="sm:hidden">{r.abbr ?? r.name}</span>
                  </Link>
                </th>
                <td className="px-2 py-1.5 text-right text-muted">{r.w}-{r.l}</td>
                {keys.map((k) => (
                  <td key={k} className={`px-2 py-1.5 text-right ${k === state.stat ? "bg-surface2 font-bold" : ""}`}>{formatStat(teamStat(k).kind, r.stats[k])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted">
        Per-game team averages for {data.season} ({data.team_games} games played).{def.lower ? ` For ${def.label.toLowerCase()} the lowest value ranks first.` : ""} Ratings are per 100 possessions. Click a column to rank by it.
      </p>
    </div>
  );
}

