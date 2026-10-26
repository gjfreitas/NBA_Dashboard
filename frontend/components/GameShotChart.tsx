"use client";
import { useMemo, useState } from "react";
import { ALL_SHOTS, filterShots, shooters, shotPoints, summarize, type ShotFilters } from "@/lib/gameShots";
import { periodLabel } from "@/lib/format";
import { FeedNotice } from "./FeedNotice";
import { useGameData } from "./GameProvider";
import { ShotCourt } from "./ShotCourt";

const chip = (on: boolean) => `min-h-11 rounded-full border px-3 text-sm ${on ? "border-accent bg-surface2 font-semibold" : "border-line text-muted hover:text-fg"}`;
const pct = (v: number | null) => (v == null ? "–" : `${(v * 100).toFixed(1)}%`);

/** Every field goal of the game on one half court, from the play-by-play. Updates live. */
export function GameShotChart() {
  const { plays, game, box, available } = useGameData();
  const [f, setF] = useState<ShotFilters>({ ...ALL_SHOTS, team: "all" });
  const all = useMemo(() => shotPoints(plays), [plays]);
  const periods = useMemo(() => [...new Set(all.map((s) => s.period))].sort((a, b) => a - b), [all]);
  const shown = useMemo(() => filterShots(all, f), [all, f]);
  const sum = useMemo(() => summarize(shown), [shown]);
  // Players for the picker come from the shots after the team filter, with names from the box score.
  const names = useMemo(() => new Map([...(box?.home.players ?? []), ...(box?.away.players ?? [])].map((p) => [p.id, p.short_name || p.name])), [box]);
  const pickable = useMemo(() => shooters(filterShots(all, { ...f, player: "all", result: "all" })), [all, f]);

  if (game?.state === "pre" || (!plays.length && !available))
    return <p className="rounded-lg border border-line bg-surface p-6 text-center text-muted">The shot chart starts at tip-off.</p>;
  if (!plays.length) return <div className="h-72 skeleton rounded-lg bg-surface" aria-busy />;

  const set = (p: Partial<ShotFilters>) => setF((x) => ({ ...x, ...p }));
  const teams = [game?.away.tricode, game?.home.tricode].filter((t): t is string => !!t);
  return (
    <section aria-label="Game shot chart" className="space-y-3">
      {!available && game?.state === "live" && <FeedNotice />}
      <div className="flex flex-wrap gap-2" role="group" aria-label="Team">
        <button className={chip(f.team === "all")} aria-pressed={f.team === "all"} onClick={() => set({ team: "all", player: "all" })}>Both teams</button>
        {teams.map((t) => <button key={t} className={chip(f.team === t)} aria-pressed={f.team === t} onClick={() => set({ team: t, player: "all" })}>{t}</button>)}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex flex-wrap gap-2" role="group" aria-label="Period">
          <button className={chip(f.period === "all")} aria-pressed={f.period === "all"} onClick={() => set({ period: "all" })}>All periods</button>
          {periods.map((n) => <button key={n} className={chip(f.period === n)} aria-pressed={f.period === n} onClick={() => set({ period: n })}>{periodLabel(n)}</button>)}
        </div>
        <div className="flex gap-2" role="group" aria-label="Result">
          {(["all", "made", "missed"] as const).map((r) => <button key={r} className={chip(f.result === r)} aria-pressed={f.result === r} onClick={() => set({ result: r })}>{r === "all" ? "All shots" : r === "made" ? "Made" : "Missed"}</button>)}
        </div>
        <label className="ml-auto inline-flex items-center gap-2 text-sm text-muted">
          Player
          <select value={f.player} onChange={(e) => set({ player: e.target.value === "all" ? "all" : Number(e.target.value) })}
            className="min-h-11 rounded-lg border border-line bg-surface px-2 text-base text-fg">
            <option value="all">Everyone</option>
            {pickable.map((s) => <option key={s.id} value={s.id}>{names.get(s.id) ?? `#${s.id}`} ({s.fgm}/{s.fga})</option>)}
          </select>
        </label>
      </div>

      <dl className="flex flex-wrap gap-x-6 gap-y-2 rounded-lg border border-line bg-surface p-3" aria-label="Shooting for the selected shots">
        {[["FG", `${sum.fgm}/${sum.fga}`], ["FG%", pct(sum.pct)], ["3PT", `${sum.threeMade}/${sum.threeAtt}`], ["eFG%", pct(sum.efg)],
          ["Avg. distance", sum.avgDistance == null ? "–" : `${sum.avgDistance.toFixed(1)} ft`]].map(([k, v]) => (
          <div key={k}><dt className="text-xs font-medium text-muted">{k}</dt><dd className="num text-lg font-bold">{v}</dd></div>
        ))}
      </dl>

      <div className="rounded-lg border border-line bg-surface p-3">
        <ShotCourt shots={shown} show="all" label={`${shown.length} shots: ${sum.fgm} made, ${sum.fga - sum.fgm} missed`} />
        <p className="mt-2 text-center text-xs text-muted">Made shots are circles, missed shots are crosses. Both teams are drawn attacking the same basket.</p>
      </div>
    </section>
  );
}
