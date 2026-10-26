"use client";
import { periodLabel } from "@/lib/format";
import type { Game, PlayerLine, TeamBox } from "@/lib/types";
import { GameFlow } from "./GameFlow";
import { LeadTracker } from "./LeadTracker";
import { useGameData } from "./GameProvider";

function LineScore({ g }: { g: Game }) {
  const n = Math.max(4, g.home.periods.length, g.away.periods.length);
  const cols = Array.from({ length: n }, (_, i) => i + 1);
  const cell = "px-3 py-2 text-right";
  const row = (t: Game["home"]) => (
    <tr className="border-t border-line">
      <th scope="row" className="px-3 py-2 text-left font-semibold">{t.tricode}</th>
      {cols.map((p) => <td key={p} className={cell}>{t.periods.find((x) => x.period === p)?.score ?? "–"}</td>)}
      <td className={`${cell} font-bold`}>{t.score}</td>
    </tr>
  );
  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-surface">
      <table className="num w-full text-sm">
        <caption className="sr-only">Score by period</caption>
        <thead>
          <tr className="text-xs text-muted">
            <th scope="col" className="px-3 py-2 text-left font-medium">Team</th>
            {cols.map((p) => <th key={p} scope="col" className={`${cell} font-medium`}>{periodLabel(p)}</th>)}
            <th scope="col" className={`${cell} font-medium`}>T</th>
          </tr>
        </thead>
        <tbody>{row(g.away)}{row(g.home)}</tbody>
      </table>
    </div>
  );
}

function Performers({ box }: { box: TeamBox }) {
  const top = [...box.players].filter((p) => p.played).sort((a, b) => b.points - a.points).slice(0, 3);
  return (
    <section className="rounded-lg border border-line bg-surface p-3">
      <h2 className="mb-2 text-xs font-medium text-muted">{box.team.city} {box.team.name}</h2>
      <ul className="space-y-1.5">
        {top.map((p: PlayerLine) => (
          <li key={p.id} className="flex items-baseline justify-between gap-2 text-sm">
            <span className="truncate font-medium">{p.short_name}</span>
            <span className="num shrink-0 text-muted"><b className="text-fg">{p.points}</b> pts · {p.rebounds} reb · {p.assists} ast</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function SummaryView() {
  const { game, plays, box } = useGameData();
  if (!game) return <div className="h-48 skeleton rounded-lg bg-surface" aria-busy />;
  if (game.state === "pre")
    return <p className="rounded-lg border border-line bg-surface p-6 text-center text-muted">Game hasn’t started. Check the Preview tab for the matchup.</p>;
  return (
    <div className="space-y-3">
      <LineScore g={game} />
      <LeadTracker plays={plays} game={game} />
      <GameFlow plays={plays} game={game} />
      {box && (
        <div className="grid gap-3 sm:grid-cols-2">
          <Performers box={box.away} />
          <Performers box={box.home} />
        </div>
      )}
    </div>
  );
}
