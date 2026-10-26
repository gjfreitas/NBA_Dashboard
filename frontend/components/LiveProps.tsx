"use client";
import { InfoTip } from "./InfoTip";
import { useMemo, useState } from "react";
import { remainingSeconds } from "@/lib/gameFlow";
import { usePolling } from "@/lib/hooks";
import { priceText } from "@/lib/lines";
import { parseMinutes, projection, propState, STATE_TEXT, statFor, type PropState } from "@/lib/liveProp";
import { MARKET_LABEL, slateMarkets, type SlateGame, type SlatePlayer } from "@/lib/slate";
import type { PlayerLine } from "@/lib/types";
import { GamblingNotice } from "./GamblingNotice";
import { useGameData } from "./GameProvider";

interface GameProps { game: SlateGame; avg_min: Record<string, number> }

const chip = (on: boolean) => `min-h-11 rounded-full border px-3 text-sm ${on ? "border-accent bg-surface2 font-semibold" : "border-line text-muted hover:text-fg"}`;
const TONE: Record<PropState, string> = {
  over: "text-win", "final-over": "text-win", "pace-over": "text-win", under: "text-live", "final-under": "text-live", "pace-under": "text-live", waiting: "text-muted", push: "text-muted",
};

function Row({ p, market, line, box, usual, minsLeft, over }: { p: SlatePlayer; market: string; line: number; box: PlayerLine | undefined; usual: number | undefined; minsLeft: number; over: boolean }) {
  const m = p.markets[market];
  const played = !!box?.played;
  const current = box && played ? statFor(market, { points: box.points, rebounds: box.rebounds, assists: box.assists, steals: box.steals, blocks: box.blocks, turnovers: box.turnovers, tpm: box.tpm }) : null;
  const mins = box ? parseMinutes(box.minutes) : 0;
  const proj = current != null ? projection(current, mins, usual, minsLeft) : null;
  const state = propState(current ?? 0, line, proj, over, played);
  const pct = current != null && line > 0 ? Math.min(100, (current / line) * 100) : 0;
  return (
    <li className="px-3 py-2">
      <div className="flex items-baseline justify-between gap-2">
        <span className="min-w-0 truncate font-medium">{p.name}{box?.on_court && <span className="ml-1.5 text-xs text-win" title="On the court">●<span className="sr-only"> on the court</span></span>}</span>
        <span className="num shrink-0 text-sm"><b>{current ?? "–"}</b> <span className="text-muted">/ {line}</span></span>
      </div>
      <div className="mt-1 h-2 overflow-hidden rounded bg-surface2" role="progressbar" aria-valuemin={0} aria-valuemax={line} aria-valuenow={current ?? 0} aria-label={`${p.name} ${MARKET_LABEL[market] ?? market}: ${current ?? 0} of ${line}`}>
        <div className={`h-full ${current != null && current > line ? "bg-win" : "bg-accent"}`} style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-1 flex flex-wrap items-center justify-between gap-x-3 text-xs text-muted">
        <span className={`font-semibold ${TONE[state]}`}>{state === "waiting" && played ? (usual == null ? "No projection: no usual minutes yet" : "No projection yet: too few minutes") : STATE_TEXT[state]}{proj != null && state.startsWith("pace") ? ` · on pace for ${proj.toFixed(1)}` : ""}</span>
        <span className="num">O {m.best_over ? priceText(m.best_over.price) : "–"} · U {m.best_under ? priceText(m.best_under.price) : "–"} · {mins > 0 ? `${mins.toFixed(0)} min` : "not played"}</span>
      </div>
    </li>
  );
}

/** Each player's prop against his live box-score total, with a pace projection. Lines are the consensus from the stored snapshot. */
export function LiveProps() {
  const { id, game, box, available } = useGameData();
  const { data, loading } = usePolling<GameProps>(`/api/games/${id}/props`, 120_000);
  const markets = useMemo(() => slateMarkets(data ? { date: "", as_of: null, games: [data.game] } : null).filter((m) => ["pts", "reb", "ast", "fg3m", "pra", "pa", "pr", "ra", "stl", "blk", "sb", "tov"].includes(m)), [data]);
  const [pick, setPick] = useState<string | null>(null);
  const [onlyPlaying, setOnlyPlaying] = useState(false);
  const market = pick && markets.includes(pick) ? pick : markets.includes("pts") ? "pts" : markets[0];
  const boxById = useMemo(() => new Map([...(box?.home.players ?? []), ...(box?.away.players ?? [])].map((p) => [p.id, p])), [box]);

  if (loading && !data) return <div className="h-64 skeleton rounded-lg bg-surface" aria-busy />;
  if (!data || !markets.length || !market)
    return <p className="rounded-lg border border-dashed border-line p-6 text-sm text-muted">No prop lines stored for this game{available ? "" : " yet"}. They appear once an odds API key is set and a fetch has run.</p>;
  const live = game?.state === "live", over = game?.state === "final";
  const left = game && live ? remainingSeconds(game.period, game.clock) / 60 : over ? 0 : 48;
  const side = (abbr: string | null) => data.game.players.filter((p) => p.team_abbr === abbr && market in p.markets
    && (!onlyPlaying || (p.player_id != null && boxById.get(p.player_id)?.on_court)));
  return (
    <section aria-label="Live props" className="space-y-3">
      <GamblingNotice compact />
      <div className="flex flex-wrap items-center gap-2">
        <div role="group" aria-label="Market" className="flex flex-wrap gap-2">
          {markets.map((m) => <button key={m} className={chip(m === market)} aria-pressed={m === market} onClick={() => setPick(m)}>{MARKET_LABEL[m] ?? m}</button>)}
        </div>
        {live && <button className={`${chip(onlyPlaying)} ml-auto`} aria-pressed={onlyPlaying} onClick={() => setOnlyPlaying((v) => !v)}>On the court</button>}
      </div>
      <p className="flex items-center gap-2 text-xs text-muted" role="status">
        {live ? "Updated with the live box score." : over ? "Final results against the line." : "The game has not started; stats appear at tip-off."}
        <InfoTip label="How pace is worked out">Pace = his rate so far times the minutes he usually plays that are still left. It ignores matchup, fouls and blowouts.</InfoTip>
      </p>
      {([data.game.away, data.game.home]).map((t) => {
        const rows = side(t.abbr);
        if (!rows.length) return null;
        return (
          <section key={t.id} aria-label={`${t.name} props`} className="overflow-hidden rounded-lg border border-line bg-surface">
            <h2 className="border-b border-line px-3 py-1.5 text-xs font-semibold text-muted">{t.name}</h2>
            <ul className="divide-y divide-line">
              {rows.map((p) => <Row key={`${p.player_id}-${p.name}`} p={p} market={market} line={p.markets[market].line} box={p.player_id != null ? boxById.get(p.player_id) : undefined}
                usual={p.player_id != null ? data.avg_min[p.player_id] : undefined} minsLeft={left} over={over} />)}
            </ul>
          </section>
        );
      })}
    </section>
  );
}
