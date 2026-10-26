"use client";
import { useMemo, useState } from "react";
import { periodLabel } from "@/lib/format";
import type { Play } from "@/lib/types";
import { FeedNotice } from "./FeedNotice";
import { useGameData } from "./GameProvider";

const PAGE = 150;
const SKIP = new Set(["period", "game"]);

function Row({ p }: { p: Play }) {
  const scoring = p.points > 0;
  return (
    <li className={`play-enter flex gap-3 border-b border-line px-3 py-2 text-sm ${scoring ? "bg-surface2" : ""}`}>
      <span className="w-10 shrink-0 text-muted num">{p.clock}</span>
      <span className="w-9 shrink-0 text-xs font-semibold text-muted">{p.team ?? ""}</span>
      <span className="min-w-0 flex-1">
        {scoring && <span className="mr-1.5 font-semibold text-win" aria-label={`${p.points} points`}>+{p.points}</span>}
        {p.is_shot && !p.made && <span className="mr-1.5 text-muted" aria-label="missed">✕</span>}
        {p.text}
      </span>
      <span className="w-16 shrink-0 text-right text-muted num">{p.away_score}–{p.home_score}</span>
    </li>
  );
}

export function PlayFeed() {
  const { plays, game, available } = useGameData();
  const [scoringOnly, setScoringOnly] = useState(false);
  const [period, setPeriod] = useState<number | "all">("all");
  const [limit, setLimit] = useState(PAGE);

  const periods = useMemo(() => [...new Set(plays.map((p) => p.period))], [plays]);
  const shown = useMemo(
    () =>
      plays
        .filter((p) => !SKIP.has(p.type) && (!scoringOnly || p.points > 0) && (period === "all" || p.period === period))
        .reverse(),
    [plays, scoringOnly, period],
  );

  if (game?.state === "pre" || (!plays.length && !available))
    return <p className="rounded-lg border border-line bg-surface p-6 text-center text-muted">Play-by-play starts at tip-off.</p>;
  if (!plays.length) return <div className="h-40 skeleton rounded-lg bg-surface" aria-busy />;

  const chip = (on: boolean) =>
    `min-h-11 rounded-full border px-3 text-sm ${on ? "border-accent bg-surface2 font-semibold" : "border-line text-muted hover:text-fg"}`;
  return (
    <section aria-label="Play-by-play">
      {!available && game?.state === "live" && <FeedNotice />}
      <div className="mb-3 flex flex-wrap gap-2">
        <button className={chip(!scoringOnly)} aria-pressed={!scoringOnly} onClick={() => setScoringOnly(false)}>All plays</button>
        <button className={chip(scoringOnly)} aria-pressed={scoringOnly} onClick={() => setScoringOnly(true)}>Scoring</button>
        <span className="mx-1 w-px self-stretch bg-line" aria-hidden />
        <button className={chip(period === "all")} aria-pressed={period === "all"} onClick={() => setPeriod("all")}>All periods</button>
        {periods.map((n) => (
          <button key={n} className={chip(period === n)} aria-pressed={period === n} onClick={() => setPeriod(n)}>{periodLabel(n)}</button>
        ))}
      </div>
      <ol className="overflow-hidden rounded-lg border border-line bg-surface">
        {shown.slice(0, limit).map((p) => <Row key={p.id} p={p} />)}
      </ol>
      {shown.length > limit && (
        <button className="mt-3 min-h-11 w-full rounded-lg border border-line text-sm text-muted hover:text-fg" onClick={() => setLimit((l) => l + PAGE)}>
          Show older plays ({shown.length - limit})
        </button>
      )}
      {!shown.length && <p className="p-6 text-center text-muted">No plays match this filter.</p>}
    </section>
  );
}
