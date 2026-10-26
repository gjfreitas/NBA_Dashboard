"use client";
import { SetupHint } from "./SetupHint";
import Link from "next/link";
import type { FormGame, StandingRow, TeamPreview } from "@/lib/types";
import { TeamInjuries } from "./availability/TeamInjuries";
import { useTeam } from "./TeamProvider";

const one = (v: number | null | undefined) => (v == null ? "–" : v.toFixed(1));
const pctOf = (v: number | null | undefined) => (v == null ? "–" : (v * 100).toFixed(1));
const signed = (v: number | null | undefined) => (v == null ? "–" : v > 0 ? `+${v.toFixed(1)}` : v.toFixed(1));

function Tile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg border border-line bg-surface p-3 text-center">
      <div className="num text-2xl font-bold">{value}</div>
      <div className="text-xs text-muted">{label}</div>
      {sub && <div className="num text-xs text-muted">{sub}</div>}
    </div>
  );
}

const STATS: { label: string; key: string; fmt: (v: number | null | undefined) => string }[] = [
  { label: "Points", key: "pts", fmt: one }, { label: "Rebounds", key: "reb", fmt: one }, { label: "Assists", key: "ast", fmt: one },
  { label: "FG%", key: "fg_pct", fmt: pctOf }, { label: "3P%", key: "fg3_pct", fmt: pctOf },
  { label: "Offensive rating", key: "off_rtg", fmt: one }, { label: "Defensive rating", key: "def_rtg", fmt: one },
  { label: "Net rating", key: "net_rtg", fmt: signed }, { label: "Pace", key: "pace", fmt: one },
];

function Records({ s }: { s: StandingRow }) {
  const items: [string, string][] = [["Home", s.home], ["Road", s.road], ["Conference", s.conf_record], ["Division", s.div_record], ["Last 10", s.l10]];
  return (
    <dl className="num grid grid-cols-2 gap-x-4 gap-y-1 rounded-lg border border-line bg-surface p-3 text-sm sm:grid-cols-5">
      {items.map(([k, v]) => (
        <div key={k}><dt className="text-xs text-muted">{k}</dt><dd className="font-semibold">{v}</dd></div>
      ))}
    </dl>
  );
}

function Form({ games }: { games: FormGame[] }) {
  const chrono = [...games].reverse();
  const w = games.filter((g) => g.result === "W").length;
  return (
    <section className="rounded-lg border border-line bg-surface p-3">
      <div className="mb-2 flex items-baseline justify-between text-sm">
        <h2 className="font-semibold">Recent form</h2>
        <span className="num text-xs text-muted">Last {games.length}: {w}-{games.length - w}</span>
      </div>
      <ol className="flex flex-wrap gap-1" aria-label={`Last ${games.length} games, oldest first`}>
        {chrono.map((g) => (
          <li key={g.date + g.opp} title={`${g.date} ${g.home ? "vs" : "@"} ${g.opp}: ${g.result} (${g.margin > 0 ? "+" : ""}${g.margin})`}
            className={`grid size-7 place-items-center rounded text-xs font-bold ${g.result === "W" ? "bg-win text-bg" : "border border-line text-muted"}`}>
            {g.result}
          </li>
        ))}
      </ol>
    </section>
  );
}

function Stats({ d, season, fallback }: { d: TeamPreview; season: string; fallback: boolean }) {
  return (
    <section className="overflow-hidden rounded-lg border border-line bg-surface">
      <table className="num w-full border-collapse text-sm">
        <caption className="border-b border-line px-3 py-2 text-left text-xs text-muted">
          Per-game averages, {season}{fallback ? " (last season: the new season is too young)" : ""}. #N is the league rank.
        </caption>
        <tbody>
          {STATS.map((s) => (
            <tr key={s.key} className="border-b border-line last:border-0">
              <th scope="row" className="px-3 py-2 text-left font-normal text-muted">{s.label}</th>
              <td className="px-3 py-2 text-right font-semibold">{s.fmt(d.stats[s.key])}</td>
              <td className="w-14 px-3 py-2 text-right text-xs text-muted">{d.ranks[s.key] != null ? `#${d.ranks[s.key]}` : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export function TeamOverview() {
  const { data, loading } = useTeam();
  if (loading || !data) return <div className="h-64 skeleton rounded-lg bg-surface" aria-busy />;
  const s = data.standing, d = data.detail;
  return (
    <div className="space-y-4">
      {s && (
        <section aria-label="Season summary" className="space-y-2">
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
            <Tile label="Record" value={`${s.w}-${s.l}`} sub={s.gb === 0 ? "conference leader" : `${s.gb.toFixed(1)} GB`} />
            <Tile label="PPG" value={one(s.ppg)} />
            <Tile label="Opp PPG" value={one(s.opp_ppg)} />
            <Tile label="Point diff" value={signed(s.diff)} />
            <Tile label="Streak" value={s.streak || "–"} />
          </div>
          <Records s={s} />
        </section>
      )}
      {d ? (
        <>
          <div className="grid gap-3 md:grid-cols-2">
            <Stats d={d} season={data.stats_season!} fallback={data.is_fallback} />
            <div className="space-y-3">
              <TeamInjuries teamId={data.team.id} />
              <Form games={d.form} />
              <section className="rounded-lg border border-line bg-surface p-3">
                <h2 className="mb-2 text-sm font-semibold">Leading scorers</h2>
                <ul className="space-y-1.5">
                  {d.leaders.map((l) => (
                    <li key={l.player_id} className="flex items-baseline justify-between gap-2 text-sm">
                      <Link href={`/players/${l.player_id}`} className="truncate font-medium hover:underline">{l.name}</Link>
                      <span className="num shrink-0 text-muted"><b className="text-fg">{l.pts.toFixed(1)}</b> pts · {l.reb.toFixed(1)} reb · {l.ast.toFixed(1)} ast</span>
                    </li>
                  ))}
                </ul>
              </section>
            </div>
          </div>
        </>
      ) : (
        <p className="rounded-lg border border-dashed border-line p-4 text-sm text-muted">
          Team stats aren’t loaded. <SetupHint cmd={`python -m nbadash.ingest teams`} />.
        </p>
      )}
    </div>
  );
}
