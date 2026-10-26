"use client";
import Link from "next/link";
import { usePolling } from "@/lib/hooks";
import { statusLabel } from "@/lib/format";
import { teamVars } from "@/lib/teamColors";
import type { Game } from "@/lib/types";
import { AnimatedNumber } from "./AnimatedNumber";

const ORDER = { live: 0, pre: 1, final: 2 } as const;

function Item({ g, hidden }: { g: Game; hidden?: boolean }) {
  const live = g.state === "live", pre = g.state === "pre";
  const awayLead = g.away.score > g.home.score, homeLead = g.home.score > g.away.score;
  return (
    <li className="shrink-0" aria-hidden={hidden || undefined}>
      <Link href={`/games/${g.id}`} tabIndex={hidden ? -1 : undefined}
        className="flex min-h-11 items-center gap-3 border-l border-line px-4 text-xs transition-colors hover:bg-surface2"
        aria-label={`${g.away.tricode} ${pre ? "at" : g.away.score + ","} ${g.home.tricode}${pre ? "" : " " + g.home.score}, ${statusLabel(g)}`}>
        {[[g.away, awayLead], [g.home, homeLead]].map(([t, lead]) => (
          <span key={(t as Game["home"]).id} className="flex items-center gap-1.5" style={teamVars((t as Game["home"]).tricode)}>
            <span aria-hidden className="h-4 w-[3px] rounded-full bg-[var(--t1)]" />
            <b className={`display text-[0.95rem] ${pre || lead ? "text-fg" : "text-muted"}`}>{(t as Game["home"]).tricode}</b>
            {!pre && <AnimatedNumber value={(t as Game["home"]).score} className={`score text-[1.1rem] ${lead ? "text-fg" : "text-muted"}`} />}
          </span>
        ))}
        <span className={`label ${live ? "flex items-center gap-1 text-live" : "text-muted"}`}>
          {live && <span className="live-dot size-1.5 rounded-full bg-live" aria-hidden />}{statusLabel(g)}
        </span>
      </Link>
    </li>
  );
}

/** Every game on the scoreboard in one slow crawl across the top, like a broadcast. It pauses when you point at it or tab into it, and holds still for anyone who asked for less motion. */
export function ScoreTicker() {
  const { data } = usePolling<Game[]>("/api/scoreboard", 15_000);
  if (!data || data.length === 0) return null;
  const games = [...data].sort((a, b) => ORDER[a.state] - ORDER[b.state] || (a.start_utc ?? "").localeCompare(b.start_utc ?? ""));
  const long = games.length >= 5; // a short list has nothing to crawl
  return (
    <nav aria-label="Games today" className="ticker border-b border-line bg-bg/70">
      <div className={`ticker-mask mx-auto max-w-6xl overflow-hidden ${long ? "" : "overflow-x-auto"}`}>
        <ul className={`flex w-max ${long ? "ticker-track" : ""}`} style={{ "--dur": `${games.length * 7}s` } as React.CSSProperties}>
          {games.map((g) => <Item key={g.id} g={g} />)}
          {long && games.map((g) => <Item key={`${g.id}-copy`} g={g} hidden />)}
        </ul>
      </div>
    </nav>
  );
}
