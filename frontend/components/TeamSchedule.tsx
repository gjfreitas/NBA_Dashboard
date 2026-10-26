"use client";
import { SetupHint } from "./SetupHint";
import Link from "next/link";
import { useState } from "react";
import { useFetch } from "@/lib/hooks";
import type { Schedule, ScheduleGame } from "@/lib/types";
import { TeamLogo } from "./Logo";
import { useTeam } from "./TeamProvider";

type Filter = "all" | "results" | "upcoming";

function Row({ g }: { g: ScheduleGame }) {
  const when = g.start_utc
    ? new Date(g.start_utc).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
    : g.status_text;
  const date = new Date(`${g.date}T12:00:00`).toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
  const played = g.status !== "pre";
  const body = (
    <>
      <span className="w-24 shrink-0 text-muted">{date}</span>
      <span className="w-5 shrink-0 text-xs text-muted">{g.home ? "vs" : "@"}</span>
      <TeamLogo id={g.opp_id} tricode={g.opp_abbr} size={24} />
      <span className="min-w-0 flex-1 truncate font-medium">
        {g.opp_name}
        {g.label && <span className="ml-2 rounded-full border border-line px-2 py-0.5 text-xs font-normal text-muted">{g.label}</span>}
      </span>
      {played ? (
        <span className="num shrink-0 text-right">
          <span className={`mr-2 font-bold ${g.result === "W" ? "text-win" : "text-muted"}`}>{g.result}</span>
          {g.team_score}–{g.opp_score}
          {g.status === "live" && <span className="ml-2 text-xs font-semibold text-live">LIVE</span>}
        </span>
      ) : (
        <span className="num shrink-0 text-right text-muted">{when}</span>
      )}
    </>
  );
  const cls = "flex min-h-11 items-center gap-2 border-b border-line px-3 py-1.5 text-sm last:border-0";
  // The game page can show any game with a box score; upcoming games have nothing to show yet.
  return (
    <li>{played ? <Link href={`/games/${g.game_id}`} className={`${cls} hover:bg-surface2`}>{body}</Link> : <div className={cls}>{body}</div>}</li>
  );
}

export function TeamSchedule() {
  const { id } = useTeam();
  const [filter, setFilter] = useState<Filter>("all");
  const { data, loading, notFound } = useFetch<Schedule>(`/api/teams/${id}/schedule`);
  if (loading) return <div className="h-64 skeleton rounded-lg bg-surface" aria-busy />;
  if (notFound || !data)
    return <p className="rounded-lg border border-dashed border-line p-6 text-sm text-muted">
      Schedule isn’t loaded. <SetupHint cmd={`python -m nbadash.ingest teams`} />.</p>;

  const results = data.games.filter((g) => g.status !== "pre");
  const upcoming = data.games.filter((g) => g.status === "pre");
  const shown = filter === "results" ? [...results].reverse() : filter === "upcoming" ? upcoming : data.games;
  const w = results.filter((g) => g.result === "W").length;
  const chip = (on: boolean) => `min-h-11 rounded-full border px-4 text-sm ${on ? "border-accent bg-surface2 font-semibold" : "border-line text-muted hover:text-fg"}`;
  return (
    <section aria-label="Schedule" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div role="group" aria-label="Filter games" className="flex gap-2">
          {([["all", "All"], ["results", `Results (${results.length})`], ["upcoming", `Upcoming (${upcoming.length})`]] as const).map(([v, label]) => (
            <button key={v} className={chip(filter === v)} aria-pressed={filter === v} onClick={() => setFilter(v)}>{label}</button>
          ))}
        </div>
        <span className="num text-sm text-muted">{data.season} · {w}-{results.length - w} so far</span>
      </div>
      {shown.length ? (
        <ul className="overflow-hidden rounded-lg border border-line bg-surface">{shown.map((g) => <Row key={g.game_id} g={g} />)}</ul>
      ) : <p className="rounded-lg border border-line bg-surface p-6 text-center text-muted">No games to show.</p>}
    </section>
  );
}
