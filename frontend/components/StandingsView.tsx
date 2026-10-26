"use client";
import { SetupHint } from "./SetupHint";
import Link from "next/link";
import { useState } from "react";
import { useFetch } from "@/lib/hooks";
import type { StandingRow, Standings } from "@/lib/types";
import { teamVars } from "@/lib/teamColors";
import { TeamLogo } from "./Logo";

type View = "conference" | "division" | "league";

const CLINCH: Record<string, string> = {
  z: "Clinched top seed", y: "Clinched division", x: "Clinched playoff berth", pi: "Clinched play-in spot", e: "Eliminated",
};

const gb = (v: number) => (v === 0 ? "–" : v.toFixed(1));
const signed = (v: number) => (v > 0 ? `+${v.toFixed(1)}` : v.toFixed(1));

function Table({ title, rows, rankKey, playoffLines }: {
  title: string; rows: StandingRow[]; rankKey: "conf_rank" | "div_rank" | "index"; playoffLines?: boolean;
}) {
  const th = "px-2 py-2 text-right text-xs font-medium text-muted";
  const td = "px-2 py-2 text-right";
  return (
    <section aria-label={title} className="overflow-x-auto rounded-lg border border-line bg-surface">
      <table className="num w-full min-w-[640px] border-collapse text-sm">
        <caption className="border-b border-line px-3 py-2 text-left text-sm font-semibold">{title}</caption>
        <thead>
          <tr className="border-b border-line">
            <th scope="col" className="w-8 px-2 py-2 text-right text-xs font-medium text-muted"><span className="sr-only">Rank</span>#</th>
            <th scope="col" className="sticky left-8 bg-surface px-2 py-2 text-left text-xs font-medium text-muted">Team</th>
            {["W", "L", "PCT", "GB", "HOME", "ROAD", "L10", "STRK", "DIFF"].map((h) => <th key={h} scope="col" className={th}>{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const rank = rankKey === "index" ? i + 1 : r[rankKey];
            // NBA format: seeds 1-6 qualify directly, 7-10 enter the play-in tournament
            const line = playoffLines && (rank === 7 || rank === 11) ? "border-t-2 border-t-accent" : "";
            return (
              <tr key={r.team.id} className={`group reveal border-b border-line transition-colors hover:bg-surface2 ${line}`} style={{ "--i": Math.min(i, 14), ...teamVars(r.team.abbr) } as React.CSSProperties}>
                <td className="border-l-[3px] border-l-[var(--t1)] px-2 py-2 text-right text-muted">{rank}</td>
                <th scope="row" className="sticky left-8 whitespace-nowrap bg-surface px-2 py-2 text-left font-medium transition-colors group-hover:bg-surface2">
                  <Link href={`/teams/${r.team.id}`} className="inline-flex min-h-8 items-center gap-2 hover:underline">
                    <TeamLogo id={r.team.id} tricode={r.team.abbr ?? ""} size={24} />
                    <span className="hidden sm:inline">{r.team.city} {r.team.name}</span>
                    <span className="sm:hidden">{r.team.abbr}</span>
                  </Link>
                  {r.clinch && <abbr title={CLINCH[r.clinch]} className="ml-1.5 text-xs font-normal text-muted no-underline">{r.clinch}</abbr>}
                </th>
                <td className={`${td} font-semibold`}>{r.w}</td>
                <td className={td}>{r.l}</td>
                <td className={`${td} relative`}>
                  <span aria-hidden className="absolute inset-y-2 left-1 right-1 -z-0 origin-left rounded-sm bg-[var(--t1)] opacity-[0.16]" style={{ transform: `scaleX(${r.pct})` }} />
                  <span className="relative">{r.pct.toFixed(3).replace(/^0/, "")}</span>
                </td>
                <td className={td}>{gb(r.gb)}</td>
                <td className={td}>{r.home}</td>
                <td className={td}>{r.road}</td>
                <td className={td}>{r.l10}</td>
                <td className={`${td} ${r.streak.startsWith("W") ? "text-win" : "text-muted"}`}>{r.streak || "–"}</td>
                <td className={td}>{signed(r.diff)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

export function StandingsView() {
  const [season, setSeason] = useState<string | null>(null);
  const [view, setView] = useState<View>("conference");
  const { data, loading, notFound, error } = useFetch<Standings>(`/api/standings${season ? `?season=${season}` : ""}`);
  if (loading && !data) return <div className="h-96 skeleton rounded-lg bg-surface" aria-busy />;
  if (notFound)
    return <p className="rounded-lg border border-dashed border-line p-6 text-sm text-muted">
      Standings aren’t loaded. <SetupHint cmd={`python -m nbadash.ingest teams`} />.</p>;
  if (!data) return <p role="alert" className="text-muted">Can’t reach the data service{error ? ` (${error})` : ""}.</p>;

  const chip = (on: boolean) => `min-h-11 rounded-full border px-4 text-sm ${on ? "border-accent bg-surface2 font-semibold" : "border-line text-muted hover:text-fg"}`;
  const byRank = (key: "conf_rank" | "div_rank") => (a: StandingRow, b: StandingRow) => a[key] - b[key];
  const confs = ["East", "West"];
  const prev = data.seasons.find((s) => s !== data.season);

  let body;
  if (view === "conference") {
    body = confs.map((c) => (
      <Table key={c} title={`${c}ern Conference`} playoffLines rankKey="conf_rank"
        rows={data.teams.filter((t) => t.team.conference === c).sort(byRank("conf_rank"))} />
    ));
  } else if (view === "division") {
    const divisions = confs.flatMap((c) => [...new Set(data.teams.filter((t) => t.team.conference === c).map((t) => t.team.division!))].sort());
    body = divisions.map((d) => (
      <Table key={d} title={`${d} Division`} rankKey="div_rank" rows={data.teams.filter((t) => t.team.division === d).sort(byRank("div_rank"))} />
    ));
  } else {
    const league = [...data.teams].sort((a, b) => b.pct - a.pct || b.diff - a.diff);
    body = <Table title="League" rankKey="index" rows={league} />;
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <label className="inline-flex items-center gap-2 text-sm text-muted">
          Season
          <select value={data.season} onChange={(e) => setSeason(e.target.value)}
            className="min-h-11 rounded-lg border border-line bg-surface px-3 text-base text-fg">
            {data.seasons.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
        <div role="group" aria-label="Grouping" className="flex gap-2">
          {(["conference", "division", "league"] as const).map((v) => (
            <button key={v} className={chip(view === v)} aria-pressed={view === v} onClick={() => setView(v)}>
              {v[0].toUpperCase() + v.slice(1)}
            </button>
          ))}
        </div>
      </div>
      {data.min_games < 10 && prev && (
        <p role="status" className="rounded-lg border border-line bg-surface p-3 text-sm text-muted">
          The {data.season} season is only {data.min_games} {data.min_games === 1 ? "game" : "games"} old, so these standings will swing a lot.{" "}
          <button className="underline hover:text-fg" onClick={() => setSeason(prev)}>See {prev} final standings</button>
        </p>
      )}
      {body}
      <p className="text-xs text-muted">
        {view === "conference" && "Seeds 1–6 qualify directly; 7–10 enter the play-in tournament (line above seed 7 and below seed 10). "}
        z top seed · y division title · x playoff berth · pi play-in secured · e eliminated. GB = games behind in the conference.
      </p>
    </div>
  );
}
