"use client";
import { useMemo } from "react";
import { flowStats } from "@/lib/gameFlow";
import type { Game, Play } from "@/lib/types";

/** Lead changes, ties, biggest leads and longest scoring runs. (The win-probability line lives on the lead tracker.) */
export function GameFlow({ plays, game }: { plays: Play[]; game: Game }) {
  const stats = useMemo(() => flowStats(plays), [plays]);
  if (!plays.some((p) => p.points > 0)) return null;
  const rows: [string, string | number, string | number][] = [
    ["Biggest lead", stats.biggestLeadAway, stats.biggestLeadHome],
    ["Longest scoring run", stats.longestRunAway, stats.longestRunHome],
  ];
  return (
    <section aria-label="Game flow" className="space-y-3 rounded-lg border border-line bg-surface p-3">
      <table className="num w-full text-sm">
        <caption className="sr-only">Game flow statistics</caption>
        <thead>
          <tr className="text-xs text-muted">
            <th scope="col" className="py-1 text-left font-semibold">{game.away.tricode}</th>
            <th scope="col" className="py-1 text-center font-normal"><span className="sr-only">Measure</span></th>
            <th scope="col" className="py-1 text-right font-semibold">{game.home.tricode}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, a, h]) => (
            <tr key={label} className="border-t border-line">
              <td className="py-1.5 text-left">{a}</td>
              <th scope="row" className="py-1.5 text-center text-xs font-normal text-muted">{label}</th>
              <td className="py-1.5 text-right">{h}</td>
            </tr>
          ))}
          <tr className="border-t border-line">
            <td className="py-1.5 text-left text-muted" colSpan={3}>
              <b className="text-fg">{stats.leadChanges}</b> lead changes · tied <b className="text-fg">{stats.ties}</b> {stats.ties === 1 ? "time" : "times"}
            </td>
          </tr>
        </tbody>
      </table>
    </section>
  );
}
