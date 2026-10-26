"use client";
import { SetupHint } from "../SetupHint";
import { useMemo, useState } from "react";
import Link from "next/link";
import { ageText, countByStatus, ESPN_NOTE, groupByGame, reportTimeText, STATUS_MEANING, STATUS_ORDER, teamsOfMatchup } from "@/lib/availability";
import { usePolling } from "@/lib/hooks";
import type { InjuryReport, InjuryStatus } from "@/lib/types";
import { ChangesFeed } from "./ChangesFeed";
import { EspnList, SourceLabel } from "./EspnList";
import { InjuryList } from "./InjuryList";

const chip = (on: boolean) => `min-h-9 rounded-full border px-3 text-sm ${on ? "border-accent bg-surface2 font-semibold" : "border-line text-muted hover:text-fg"}`;
const dateText = (d: string | null) => (d ? new Date(`${d}T12:00:00`).toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" }) : "");

export function InjuriesView() {
  const { data, loading, error } = usePolling<InjuryReport>("/api/injuries", 5 * 60_000);
  const [status, setStatus] = useState<InjuryStatus | "all">("all");
  const [q, setQ] = useState("");

  const entries = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (data?.entries ?? []).filter((e) => (status === "all" || e.status === status) &&
      (!needle || e.name.toLowerCase().includes(needle) || (e.team_abbr ?? "").toLowerCase().includes(needle) || e.reason.toLowerCase().includes(needle)));
  }, [data, status, q]);
  const groups = useMemo(() => groupByGame(entries), [entries]);
  const espnRows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (data?.espn ?? []).filter((e) => (status === "all" || e.status === status) &&
      (!needle || e.name.toLowerCase().includes(needle) || (e.team_abbr ?? "").toLowerCase().includes(needle) || e.injury.toLowerCase().includes(needle)));
  }, [data, status, q]);
  const espnByTeam = useMemo(() => {
    const m = new Map<string, typeof espnRows>();
    for (const e of espnRows) m.set(e.team_abbr ?? "Other", [...(m.get(e.team_abbr ?? "Other") ?? []), e]);
    return [...m.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [espnRows]);
  const counts = useMemo(() => countByStatus(data?.entries ?? []), [data]);

  if (loading && !data) return <div className="h-96 skeleton rounded-lg bg-surface" aria-busy />;
  if (!data) return <p role="alert" className="text-muted">Can’t reach the data service{error ? ` (${error})` : ""}.</p>;
  if (!data.report && !(data.espn ?? []).length)
    return (
      <p className="rounded-lg border border-dashed border-line p-6 text-sm text-muted">
        <SetupHint cmd={`python -m nbadash.injuries once`} />.
      </p>
    );

  const r = data.report;
  const pendingByGame = new Map<string, string[]>();
  for (const p of data.pending) {
    const k = `${p.game_date}|${p.matchup}`;
    pendingByGame.set(k, [...(pendingByGame.get(k) ?? []), p.team ?? "?"]);
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted" role="status">
        {r ? <>
          Official NBA injury report from <span className="font-semibold text-fg">{reportTimeText(r.published_at)}</span> ({ageText(r.age_minutes)}).
          {r.stale ? " This report is old; the NBA files a new one on game days." : ` ${data.pending.length ? `${data.pending.length} teams haven’t filed yet.` : "All teams have filed."}`}
        </> : "There is no official NBA report right now (the NBA files them on game days), so only ESPN’s list is shown below."}
      </p>

      <div className="flex flex-wrap items-center gap-2">
        <div role="group" aria-label="Filter by status" className="flex flex-wrap gap-2">
          <button className={chip(status === "all")} aria-pressed={status === "all"} onClick={() => setStatus("all")}>All ({data.entries.length})</button>
          {STATUS_ORDER.filter((s) => counts[s]).map((s) => (
            <button key={s} className={chip(status === s)} aria-pressed={status === s} onClick={() => setStatus(s)} title={STATUS_MEANING[s]}>{s} ({counts[s]})</button>
          ))}
        </div>
        <label className="ml-auto">
          <span className="sr-only">Search players, teams or injuries</span>
          <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search player, team or injury…"
            className="min-h-11 w-full min-w-56 rounded-lg border border-line bg-surface px-3 text-base placeholder:text-muted" />
        </label>
      </div>

      {r && status === "all" && !q && <ChangesFeed limit={12} />}

      {groups.length === 0 && espnRows.length === 0 && <p className="rounded-lg border border-dashed border-line p-6 text-center text-sm text-muted">No players match.</p>}
      <div className="grid gap-3 lg:grid-cols-2">
        {groups.map((g) => {
          const teams = teamsOfMatchup(g.matchup);
          const waiting = pendingByGame.get(`${g.date}|${g.matchup}`) ?? [];
          return (
            <section key={g.key} aria-label={g.matchup ?? "Game"} className="rounded-lg border border-line bg-surface p-3">
              <h2 className="mb-1 flex items-baseline justify-between gap-2 text-sm font-semibold">
                <span>{teams ? `${teams.away} @ ${teams.home}` : g.matchup}</span>
                <span className="text-xs font-normal text-muted">
                  {dateText(g.date)}{g.time ? ` · ${g.time.replace("(ET)", "ET")}` : ""}
                  {g.gameId && <> · <Link href={`/games/${g.gameId}/preview`} className="underline hover:text-fg">Preview</Link></>}
                </span>
              </h2>
              <InjuryList entries={g.entries} showTeam />
              {waiting.length > 0 && <p className="mt-1 text-xs text-muted">Not filed yet: {waiting.join(", ")}.</p>}
            </section>
          );
        })}
      </div>

      {espnRows.length > 0 && (
        <section aria-label="ESPN injury list" className="space-y-2 rounded-lg border border-dashed border-muted p-3">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-sm font-semibold">Also injured, per ESPN</h2>
            <SourceLabel />
            {data.espn_meta && <span className="text-xs text-muted">ESPN list fetched {ageText(data.espn_meta.age_minutes)}</span>}
          </div>
          <p className="text-xs text-muted">
            Players ESPN lists who are <strong className="font-semibold">not</strong> on the official report above: injuries for teams the report doesn’t cover yet, and long-term absences. {ESPN_NOTE}
          </p>
          <div className="grid gap-x-6 lg:grid-cols-2">
            {espnByTeam.map(([team, rows]) => (
              <div key={team}>
                <h3 className="mt-2 text-xs font-semibold text-muted">{team}</h3>
                <EspnList entries={rows} />
              </div>
            ))}
          </div>
        </section>
      )}

      {r && status === "all" && !q && data.pending.length > 0 && (
        <details className="rounded-lg border border-line bg-surface p-3 text-sm">
          <summary className="cursor-pointer font-medium">Teams that haven’t filed yet ({data.pending.length})</summary>
          <ul className="mt-2 grid gap-1 text-muted sm:grid-cols-2">
            {data.pending.map((p, i) => <li key={i}>{p.team ?? "?"} · {p.matchup} · {dateText(p.game_date)}</li>)}
          </ul>
        </details>
      )}
      <p className="text-xs text-muted">
        Official statuses: {STATUS_ORDER.map((s) => `${s} (${STATUS_MEANING[s].toLowerCase()})`).join(", ")}. A team that has not filed has no official entries, so “no players listed” does not mean “healthy”.
      </p>
    </div>
  );
}
