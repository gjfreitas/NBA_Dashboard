"use client";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo } from "react";
import { useFetch } from "@/lib/hooks";
import { DEFAULT_LIMIT, modeApplies, parseState, PLAYER_STATS, playerStat, TEAM_STATS, toSearch, type LeadersState } from "@/lib/leaders";
import type { PlayerLeaders } from "@/lib/types";
import { PlayerBoard } from "./PlayerBoard";
import { TeamBoard } from "./TeamBoard";

const chip = (on: boolean) =>
  `min-h-9 rounded-full border px-3 text-sm ${on ? "border-accent bg-surface2 font-semibold" : "border-line text-muted hover:text-fg"}`;

const PCT_KEYS = ["fg_pct", "fg3_pct", "ft_pct", "efg_pct", "ts_pct"];

export function LeadersView() {
  const router = useRouter();
  const sp = useSearchParams();
  const state = useMemo(() => parseState(new URLSearchParams(sp.toString())), [sp]);
  // a tiny request just for the season list and how far into the season we are
  const meta = useFetch<PlayerLeaders>("/api/leaders/players?limit=1", { keepPrevious: true });

  const update = (patch: Partial<LeadersState>) => {
    const next = { ...state, ...patch };
    // anything that changes the board starts again from the top 25 (only "show more" and column clicks keep a limit)
    if (!("limit" in patch)) next.limit = DEFAULT_LIMIT;
    router.replace(`/leaders${toSearch(next)}`, { scroll: false });
  };
  const setView = (view: LeadersState["view"]) =>
    update({ view, stat: (view === "teams" ? TEAM_STATS : PLAYER_STATS)[0].key });

  const seasons = meta.data?.seasons ?? [];
  const current = state.season ?? meta.data?.season ?? "";
  const previous = seasons.find((s) => s < current);
  const young = state.season === null && meta.data && meta.data.team_games < 10 && previous;
  const def = playerStat(state.stat);
  const stats = state.view === "teams" ? TEAM_STATS : PLAYER_STATS;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <div role="group" aria-label="Leaderboard type" className="flex rounded-lg border border-line text-sm">
          {(["players", "teams"] as const).map((v, i) => (
            <button key={v} aria-pressed={state.view === v} onClick={() => setView(v)}
              className={`min-h-11 px-4 ${state.view === v ? "bg-surface2 font-semibold" : "text-muted hover:text-fg"} ${i === 0 ? "rounded-l-lg" : "rounded-r-lg"}`}>
              {v === "players" ? "Players" : "Teams"}
            </button>
          ))}
        </div>
        <label className="inline-flex items-center gap-2 text-sm text-muted">
          Season
          <select value={current} onChange={(e) => update({ season: e.target.value })} disabled={!seasons.length}
            className="min-h-11 rounded-lg border border-line bg-surface px-3 text-base text-fg">
            {seasons.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>

        {state.view === "players" && (
          <>
            <div role="group" aria-label="Season type" className="flex gap-2">
              {(["regular", "playoffs"] as const).map((t) => (
                <button key={t} className={chip(state.type === t)} aria-pressed={state.type === t} onClick={() => update({ type: t })}>
                  {t === "regular" ? "Regular season" : "Playoffs"}
                </button>
              ))}
            </div>
            <div role="group" aria-label="Per game or totals" className="flex gap-2">
              {(["pg", "total"] as const).map((m) => (
                <button key={m} className={chip(state.mode === m && modeApplies(def))} aria-pressed={state.mode === m} disabled={!modeApplies(def)}
                  title={modeApplies(def) ? undefined : `${def.label} is a rate, so per game / totals doesn’t apply`}
                  onClick={() => update({ mode: m })}>
                  {m === "pg" ? "Per game" : "Totals"}
                </button>
              ))}
            </div>
            <label className="inline-flex min-h-11 items-center gap-2 text-sm text-muted">
              <input type="checkbox" checked={state.qualified} onChange={(e) => update({ qualified: e.target.checked })} className="size-4 accent-[var(--accent)]" />
              Qualified players only
            </label>
          </>
        )}
      </div>

      {young && (
        <p role="status" className="rounded-lg border border-line bg-surface p-3 text-sm text-muted">
          {current} is only {meta.data!.team_games} {meta.data!.team_games === 1 ? "game" : "games"} old, so these leaders will change a lot.{" "}
          <button className="underline hover:text-fg" onClick={() => update({ season: previous })}>See {previous}</button>
        </p>
      )}

      <div role="group" aria-label="Statistic" className="flex flex-wrap gap-2">
        {stats.map((s) => (
          <button key={s.key} className={chip(state.stat === s.key)} aria-pressed={state.stat === s.key} onClick={() => update({ stat: s.key })}>
            {s.label}
            {state.view === "teams" && s.lower ? <span className="sr-only"> (lowest is best)</span> : null}
          </button>
        ))}
      </div>
      {state.view === "players" && PCT_KEYS.includes(state.stat) && (
        <p className="text-xs text-muted">Percentages need a minimum number of made shots to qualify, so one lucky night can’t top the list.</p>
      )}

      <h2 className="sr-only">{state.view === "teams" ? "Team" : "Player"} leaders</h2>
      {state.view === "teams" ? <TeamBoard state={state} update={update} /> : <PlayerBoard state={state} update={update} />}
    </div>
  );
}
