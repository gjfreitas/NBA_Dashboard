"use client";
import { useState } from "react";
import type { PlayerLine, TeamBox } from "@/lib/types";
import { useGameData } from "./GameProvider";

type SortKey = "pts" | "reb" | "ast";

const COLS: { k: string; label: string; get: (p: PlayerLine) => string | number }[] = [
  { k: "min", label: "MIN", get: (p) => p.minutes },
  { k: "pts", label: "PTS", get: (p) => p.points },
  { k: "reb", label: "REB", get: (p) => p.rebounds },
  { k: "ast", label: "AST", get: (p) => p.assists },
  { k: "stl", label: "STL", get: (p) => p.steals },
  { k: "blk", label: "BLK", get: (p) => p.blocks },
  { k: "to", label: "TO", get: (p) => p.turnovers },
  { k: "pf", label: "PF", get: (p) => p.fouls },
  { k: "fg", label: "FG", get: (p) => `${p.fgm}-${p.fga}` },
  { k: "3p", label: "3P", get: (p) => `${p.tpm}-${p.tpa}` },
  { k: "ft", label: "FT", get: (p) => `${p.ftm}-${p.fta}` },
  { k: "pm", label: "+/−", get: (p) => (p.plus_minus > 0 ? `+${p.plus_minus}` : p.plus_minus) },
];

const SORTERS: Record<SortKey, (p: PlayerLine) => number> = {
  pts: (p) => p.points, reb: (p) => p.rebounds, ast: (p) => p.assists,
};
const isSortKey = (k: string): k is SortKey => k in SORTERS;
const sum = (ps: PlayerLine[], f: (p: PlayerLine) => number) => ps.reduce((a, p) => a + f(p), 0);

function Table({ box }: { box: TeamBox }) {
  const [sortKey, setSortKey] = useState<SortKey | null>(null);
  const active = box.players.filter((p) => p.played);
  const dnp = box.players.filter((p) => !p.played);
  const starters = active.filter((p) => p.starter);
  const ordered = sortKey
    ? [...active].sort((a, b) => SORTERS[sortKey](b) - SORTERS[sortKey](a))
    : [...starters, ...active.filter((p) => !p.starter)];
  const totals: (string | number)[] = [
    "", sum(active, (p) => p.points), sum(active, (p) => p.rebounds), sum(active, (p) => p.assists),
    sum(active, (p) => p.steals), sum(active, (p) => p.blocks), sum(active, (p) => p.turnovers), sum(active, (p) => p.fouls),
    `${sum(active, (p) => p.fgm)}-${sum(active, (p) => p.fga)}`, `${sum(active, (p) => p.tpm)}-${sum(active, (p) => p.tpa)}`,
    `${sum(active, (p) => p.ftm)}-${sum(active, (p) => p.fta)}`, "",
  ];
  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-surface">
      <table className="num w-full min-w-[640px] border-collapse text-sm">
        <caption className="sr-only">{box.team.city} {box.team.name} box score</caption>
        <thead>
          <tr className="border-b border-line">
            <th scope="col" className="sticky left-0 bg-surface px-3 py-2 text-left text-xs font-medium text-muted">Player</th>
            {COLS.map((c) => (
              <th key={c.k} scope="col" className="px-2 py-2 text-right text-xs font-medium text-muted"
                aria-sort={sortKey === c.k ? "descending" : undefined}>
                {isSortKey(c.k) ? (
                  <button className="min-h-8 px-1 hover:text-fg" onClick={() => setSortKey(sortKey === c.k ? null : (c.k as SortKey))}>
                    {c.label}{sortKey === c.k ? " ▾" : ""}
                  </button>
                ) : c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ordered.map((p, i) => (
            <tr key={p.id} className={`border-b border-line ${!sortKey && i === starters.length && i > 0 ? "border-t-2 border-t-line" : ""}`}>
              <th scope="row" className="sticky left-0 whitespace-nowrap bg-surface px-3 py-2 text-left font-medium">
                {p.on_court && <span className="mr-1 inline-block size-1.5 rounded-full bg-win align-middle" title="On court" />}
                {p.short_name} <span className="text-xs font-normal text-muted">{p.position}</span>
              </th>
              {COLS.map((c) => <td key={c.k} className={`px-2 py-2 text-right ${c.k === "pts" ? "font-semibold" : ""}`}>{c.get(p)}</td>)}
            </tr>
          ))}
          <tr className="bg-surface2 font-semibold">
            <th scope="row" className="sticky left-0 bg-surface2 px-3 py-2 text-left">Team</th>
            {totals.map((t, i) => <td key={i} className="px-2 py-2 text-right">{t}</td>)}
          </tr>
        </tbody>
      </table>
      {dnp.length > 0 && <p className="border-t border-line px-3 py-2 text-xs text-muted">Did not play: {dnp.map((p) => p.short_name).join(", ")}</p>}
    </div>
  );
}

export function BoxScoreView() {
  const { box, game, boxMissing } = useGameData();
  const [side, setSide] = useState<"away" | "home">("away");
  if (game?.state === "pre" || boxMissing)
    return <p className="rounded-lg border border-line bg-surface p-6 text-center text-muted">Box score is available once the game starts.</p>;
  if (!box) return <div className="h-64 skeleton rounded-lg bg-surface" aria-busy />;
  const meta = [
    box.arena,
    box.attendance ? `${box.attendance.toLocaleString("en-US")} attendance` : null,
    box.officials.length ? `Officials: ${box.officials.join(", ")}` : null,
  ].filter(Boolean).join(" · ");
  return (
    <section aria-label="Box score" className="space-y-3">
      <div role="group" aria-label="Team" className="flex gap-2">
        {(["away", "home"] as const).map((s) => (
          <button key={s} aria-pressed={side === s} onClick={() => setSide(s)}
            className={`min-h-11 flex-1 rounded-lg border text-sm ${side === s ? "border-accent bg-surface2 font-semibold" : "border-line text-muted"}`}>
            {box[s].team.tricode} · {box[s].team.score}
          </button>
        ))}
      </div>
      <Table key={side} box={box[side]} />
      {meta && <p className="text-xs text-muted">{meta}</p>}
    </section>
  );
}
