"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { record, statusLabel } from "@/lib/format";
import { gameVars, teamVars } from "@/lib/teamColors";
import type { TeamSummary } from "@/lib/types";
import { AnimatedNumber } from "./AnimatedNumber";
import { useGameData } from "./GameProvider";
import { TeamLogo } from "./Logo";
import { TabBar } from "./TabBar";

function Side({ t, show, lead, right }: { t: TeamSummary; show: boolean; lead: boolean; right?: boolean }) {
  return (
    <div className={`flex min-w-0 flex-1 items-center gap-2.5 sm:gap-4 ${right ? "flex-row-reverse text-right" : ""}`} style={teamVars(t.tricode)}>
      <span className="logo-glow relative grid shrink-0 place-items-center">
        <TeamLogo id={t.id} tricode={t.tricode} size={56} />
      </span>
      <div className="min-w-0 shrink-0 leading-none sm:shrink">
        <div className="display truncate text-2xl font-extrabold group-data-[compact=true]:text-lg sm:text-4xl sm:group-data-[compact=true]:text-2xl">
          <span className="sm:hidden">{t.tricode}</span>
          <span className="hidden sm:inline">{t.name}</span>
        </div>
        <div className="label mt-1 hidden truncate text-muted num transition-opacity group-data-[compact=true]:opacity-0 sm:block">{t.city} · {record(t) || "–"}</div>
      </div>
      <div className={`score ${right ? "mr-auto" : "ml-auto"} text-5xl transition-[font-size] duration-300 group-data-[compact=true]:text-3xl sm:text-7xl sm:group-data-[compact=true]:text-4xl ${lead ? "text-fg" : "text-muted"}`}>
        {show ? <AnimatedNumber value={t.score} /> : null}
      </div>
    </div>
  );
}

/** One of four quarter markers: filled for periods played, pulsing for the one under way. */
function Pips({ period, state }: { period: number; state: string }) {
  const played = state === "final" ? 5 : state === "live" ? Math.min(period, 4) : 0;
  return (
    <div className="mx-auto mt-1.5 grid w-16 grid-cols-4 gap-1 sm:w-24" aria-hidden>
      {[1, 2, 3, 4].map((q) => <span key={q} className="pip" data-on={q < played} data-live={state === "live" && q === played} />)}
    </div>
  );
}

const TABS = [
  { slug: "", label: "Summary" },
  { slug: "play-by-play", label: "Play-by-play" },
  { slug: "box-score", label: "Box score" },
  { slug: "shots", label: "Shot chart" },
  { slug: "props", label: "Props" },
  { slug: "preview", label: "Preview" },
];

export function GameHeader() {
  const { id, game, connected, missing } = useGameData();
  const path = usePathname();
  const [compact, setCompact] = useState(false);
  // The hero shrinks once you have scrolled past it, so the scores stay in view without taking half the screen.
  useEffect(() => {
    const on = () => setCompact(window.scrollY > 90);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);
  // Screen-reader line changes only when the score does (never per clock tick).
  const score = game && game.state !== "pre" ? `${game.away.tricode} ${game.away.score}, ${game.home.tricode} ${game.home.score}` : "";
  if (missing) return <p role="alert" className="p-4 text-muted">Game not found. <Link className="underline" href="/">Back to scores</Link></p>;
  const pre = game?.state === "pre";
  const live = game?.state === "live";
  const tabs = TABS.map((t) => ({ href: `/games/${id}${t.slug ? `/${t.slug}` : ""}`, label: t.label }));
  return (
    <div data-compact={compact} className="game-hero group isolate sticky top-0 z-20 -mx-4 border-b border-line bg-bg/95 px-4 pt-1" style={game ? gameVars(game.away.tricode, game.home.tricode) : undefined}>
      <div className="hero-wash" aria-hidden />
      <Link href="/" className="label inline-flex min-h-11 items-center text-muted transition-colors hover:text-accent group-data-[compact=true]:hidden">‹ All games</Link>
      {game ? (
        <div className="flex items-center gap-2 pb-2 group-data-[compact=true]:pt-2">
          <Side t={game.away} show={!pre} lead={game.away.score > game.home.score} />
          <div className="w-16 shrink-0 text-center sm:w-32">
            {live ? <span className="bug bug-live label inline-flex items-center gap-1 py-0.5 pl-2 pr-4 font-bold"><span className="live-dot size-1.5 rounded-full bg-white" aria-hidden />LIVE</span> : null}
            <div className="display mt-1 text-lg font-bold num sm:text-2xl">{statusLabel(game)}</div>
            <div className="group-data-[compact=true]:hidden"><Pips period={game.period} state={game.state} /></div>
            {live && !connected && <div className="label text-muted">reconnecting…</div>}
          </div>
          <Side t={game.home} show={!pre} lead={game.home.score > game.away.score} right />
        </div>
      ) : (
        <div className="skeleton h-[88px] rounded" aria-busy />
      )}
      {game && <h1 className="sr-only">{game.away.name} at {game.home.name}</h1>}
      <span className="sr-only" role="status" aria-live="polite">{score}</span>
      <TabBar label="Game sections" tabs={tabs} active={tabs.find((t) => t.href === path)?.href ?? null} className="-mb-px" />
    </div>
  );
}
