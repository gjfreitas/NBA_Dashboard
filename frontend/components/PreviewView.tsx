"use client";
import { SetupHint } from "./SetupHint";
import Link from "next/link";
import { record } from "@/lib/format";
import { useFetch } from "@/lib/hooks";
import { marginText, recordText, restEdge, restText, streakText } from "@/lib/preview";
import type { Preview, TeamPreview } from "@/lib/types";
import { useGameData } from "./GameProvider";
import { AvailabilityPanel } from "./availability/AvailabilityPanel";
import { TeamLogo } from "./Logo";
import { MatchupDepth } from "./MatchupDepth";

interface Row { label: string; key: string; fmt: (v: number) => string; lowerIsBetter?: boolean; neutral?: boolean }

const dec = (v: number) => v.toFixed(1);
const pctFmt = (v: number) => (v * 100).toFixed(1);
const signed = (v: number) => (v > 0 ? `+${v.toFixed(1)}` : v.toFixed(1));

const ROWS: Row[] = [
  { label: "Points", key: "pts", fmt: dec },
  { label: "Rebounds", key: "reb", fmt: dec },
  { label: "Assists", key: "ast", fmt: dec },
  { label: "FG%", key: "fg_pct", fmt: pctFmt },
  { label: "3P%", key: "fg3_pct", fmt: pctFmt },
  { label: "Offensive rating", key: "off_rtg", fmt: dec },
  { label: "Defensive rating", key: "def_rtg", fmt: dec, lowerIsBetter: true },
  { label: "Net rating", key: "net_rtg", fmt: signed },
  { label: "Pace", key: "pace", fmt: dec, neutral: true },
];

function Cell({ t, row, better, right }: { t: TeamPreview; row: Row; better: boolean; right?: boolean }) {
  const v = t.stats[row.key];
  const rank = t.ranks[row.key];
  const rankEl = rank != null && <span className={`${right ? "mr-1.5" : "ml-1.5"} text-xs font-normal text-muted`}>#{rank}</span>;
  return (
    <td className={`px-3 py-2 ${right ? "text-right" : ""} ${better ? "font-bold" : "text-muted"}`}>
      {right && rankEl}
      {v == null ? "–" : row.fmt(v)}
      {!right && rankEl}
      {better && <span className="sr-only"> (better)</span>}
    </td>
  );
}

function Comparison({ p }: { p: Preview }) {
  return (
    <section aria-label="Team comparison" className="overflow-hidden rounded-lg border border-line bg-surface">
      <table className="num w-full border-collapse text-sm">
        <caption className="border-b border-line px-3 py-2 text-left text-xs text-muted">
          Per-game averages, {p.season}{p.is_fallback ? " (last season — the new season is too young)" : ""}. #N is the league rank.
        </caption>
        <thead>
          <tr className="border-b border-line text-xs">
            <th scope="col" className="px-3 py-2 text-left font-semibold">{p.away.abbr ?? "AWAY"}</th>
            <th scope="col" className="px-3 py-2 text-center font-medium text-muted"><span className="sr-only">Stat</span></th>
            <th scope="col" className="px-3 py-2 text-right font-semibold">{p.home.abbr ?? "HOME"}</th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map((r) => {
            const a = p.away.stats[r.key], h = p.home.stats[r.key];
            const cmp = a == null || h == null || r.neutral || a === h ? 0 : (a > h ? 1 : -1) * (r.lowerIsBetter ? -1 : 1);
            return (
              <tr key={r.key} className="border-b border-line last:border-0">
                <Cell t={p.away} row={r} better={cmp === 1} />
                <th scope="row" className="px-3 py-2 text-center text-xs font-normal text-muted">{r.label}</th>
                <Cell t={p.home} row={r} better={cmp === -1} right />
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

function Schedule({ p }: { p: Preview }) {
  const a = p.away.context, h = p.home.context;
  if (!a && !h) return null;
  const edge = restEdge(a, h, p.away.abbr ?? "Away", p.home.abbr ?? "Home");
  const rows: { label: string; away: string; home: string; flag?: [boolean, boolean] }[] = [
    { label: "Rest", away: restText(a), home: restText(h), flag: [!!a?.back_to_back, !!h?.back_to_back] },
    { label: "Games in last 7 days", away: a ? String(a.games_last_7) : "–", home: h ? String(h.games_last_7) : "–" },
    { label: "Streak", away: streakText(a?.streak), home: streakText(h?.streak) },
    { label: "Last 5", away: recordText(a?.last5), home: recordText(h?.last5) },
    { label: "Away / home record", away: `${recordText(a?.away)} ${marginText(a?.away)}`.trim(), home: `${recordText(h?.home)} ${marginText(h?.home)}`.trim() },
  ];
  return (
    <section aria-label="Schedule and splits" className="overflow-hidden rounded-lg border border-line bg-surface">
      <table className="num w-full border-collapse text-sm">
        <caption className="border-b border-line px-3 py-2 text-left text-xs text-muted">
          Schedule context from games played this season. For the last row: {p.away.abbr} on the road, {p.home.abbr} at home, with average margin.
          {edge && <> <b className="font-semibold text-fg">{edge}.</b></>}
        </caption>
        <thead>
          <tr className="border-b border-line text-xs">
            <th scope="col" className="px-3 py-2 text-left font-semibold">{p.away.abbr}</th>
            <th scope="col" className="px-3 py-2 text-center font-medium text-muted"><span className="sr-only">Measure</span></th>
            <th scope="col" className="px-3 py-2 text-right font-semibold">{p.home.abbr}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label} className="border-b border-line last:border-0">
              <td className={`px-3 py-2 ${r.flag?.[0] ? "font-bold text-live" : ""}`}>{r.away}</td>
              <th scope="row" className="px-3 py-2 text-center text-xs font-normal text-muted">{r.label}</th>
              <td className={`px-3 py-2 text-right ${r.flag?.[1] ? "font-bold text-live" : ""}`}>{r.home}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function Form({ t }: { t: TeamPreview }) {
  const w = t.form.filter((g) => g.result === "W").length;
  const chrono = [...t.form].reverse();
  return (
    <div className="rounded-lg border border-line bg-surface p-3">
      <div className="mb-2 flex items-baseline justify-between text-sm">
        <span className="font-semibold">{t.abbr}</span>
        <span className="num text-xs text-muted">Last {t.form.length}: {w}-{t.form.length - w}</span>
      </div>
      <ol className="flex gap-1" aria-label={`${t.name} last ${t.form.length} games, oldest first`}>
        {chrono.map((g) => (
          <li key={g.date + g.opp}
            title={`${g.date} ${g.home ? "vs" : "@"} ${g.opp}: ${g.result} (${g.margin > 0 ? "+" : ""}${g.margin})`}
            className={`grid size-7 place-items-center rounded text-xs font-bold ${g.result === "W" ? "bg-win text-bg" : "border border-line text-muted"}`}>
            {g.result}
          </li>
        ))}
      </ol>
    </div>
  );
}

function Leaders({ t }: { t: TeamPreview }) {
  return (
    <section className="rounded-lg border border-line bg-surface p-3">
      <h3 className="mb-2 text-xs font-medium text-muted">{t.name}</h3>
      <ul className="space-y-1.5">
        {t.leaders.map((l) => (
          <li key={l.player_id} className="flex items-baseline justify-between gap-2 text-sm">
            <Link href={`/players/${l.player_id}`} className="truncate font-medium hover:underline">{l.name}</Link>
            <span className="num shrink-0 text-muted"><b className="text-fg">{l.pts.toFixed(1)}</b> pts · {l.reb.toFixed(1)} reb · {l.ast.toFixed(1)} ast</span>
          </li>
        ))}
        {!t.leaders.length && <li className="text-sm text-muted">No data yet.</li>}
      </ul>
    </section>
  );
}

function Series({ p }: { p: Preview }) {
  const { games, home_wins, away_wins } = p.series;
  return (
    <section aria-label="Season series" className="rounded-lg border border-line bg-surface p-3">
      <div className="mb-2 flex items-baseline justify-between text-sm">
        <h3 className="font-semibold">Recent meetings</h3>
        {games.length > 0 && <span className="num text-xs text-muted">{p.away.abbr} {away_wins} – {home_wins} {p.home.abbr}</span>}
      </div>
      {games.length ? (
        <ul className="divide-y divide-line text-sm">
          {games.slice(0, 6).map((g) => (
            <li key={g.date} className="num flex items-center justify-between py-1.5">
              <span className="text-muted">{g.date}</span>
              <span>
                <span className={g.away_pts > g.home_pts ? "font-bold" : "text-muted"}>{g.away_abbr} {g.away_pts}</span>
                <span className="text-muted"> @ </span>
                <span className={g.home_pts > g.away_pts ? "font-bold" : "text-muted"}>{g.home_abbr} {g.home_pts}</span>
              </span>
            </li>
          ))}
        </ul>
      ) : <p className="text-sm text-muted">These teams haven’t met this season or last.</p>}
    </section>
  );
}

export function PreviewView() {
  const { id, game } = useGameData();
  const { data: p, loading, notFound } = useFetch<Preview>(game ? `/api/preview?home=${game.home.id}&away=${game.away.id}&game_id=${id}` : null);
  if (!game) return <div className="h-48 skeleton rounded-lg bg-surface" aria-busy />;
  const when = game.start_utc
    ? new Date(game.start_utc).toLocaleString([], { weekday: "long", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })
    : game.status_text;
  return (
    <div className="space-y-3">
      <section className="rounded-lg border border-line bg-surface p-4 text-center">
        <p className="text-sm text-muted">{when}</p>
        <div className="mt-3 flex items-center justify-center gap-6">
          {[game.away, game.home].map((t, i) => (
            <div key={t.id} className="flex items-center gap-6">
              {i === 1 && <span className="text-muted">@</span>}
              <div className="flex flex-col items-center gap-1">
                <TeamLogo id={t.id} tricode={t.tricode} size={56} />
                <span className="font-semibold">{t.city} {t.name}</span>
                <span className="num text-sm text-muted">{record(t)}</span>
              </div>
            </div>
          ))}
        </div>
      </section>
      <AvailabilityPanel gameId={id} />
      {loading && <div className="h-64 skeleton rounded-lg bg-surface" aria-busy />}
      {notFound && (
        <p className="rounded-lg border border-dashed border-line p-4 text-sm text-muted">
          Team data isn’t loaded yet. <SetupHint cmd={`python -m nbadash.ingest teams`} />.
        </p>
      )}
      {p && (
        <>
          <Comparison p={p} />
          <Schedule p={p} />
          <MatchupDepth homeId={game.home.id} awayId={game.away.id} />
          <div className="grid gap-3 sm:grid-cols-2"><Form t={p.away} /><Form t={p.home} /></div>
          <div className="grid gap-3 sm:grid-cols-2"><Leaders t={p.away} /><Leaders t={p.home} /></div>
          <Series p={p} />
        </>
      )}
    </div>
  );
}
