"use client";
import { SetupHint } from "./SetupHint";
import { useState } from "react";
import type { SeasonLine } from "@/lib/types";
import { usePlayer } from "./PlayerProvider";

export const pct = (v: number | null) => (v == null ? "–" : (v * 100).toFixed(1));
const num = (v: number) => v.toFixed(1);

function Tile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg border border-line bg-surface p-3 text-center">
      <div className="num text-2xl font-bold">{value}</div>
      <div className="text-xs text-muted">{label}</div>
      {sub && <div className="num text-xs text-muted">{sub}</div>}
    </div>
  );
}

function Table({ lines, career, caption }: { lines: SeasonLine[]; career: SeasonLine | null; caption: string }) {
  const th = "px-2 py-2 text-right text-xs font-medium text-muted";
  const td = "px-2 py-2 text-right";
  const row = (l: SeasonLine, key: string, strong = false) => (
    <tr key={key} className={`border-b border-line ${strong ? "bg-surface2 font-semibold" : ""} ${l.team === "TOT" ? "" : ""}`}>
      <th scope="row" className={`sticky left-0 whitespace-nowrap px-3 py-2 text-left font-medium ${strong ? "bg-surface2" : "bg-surface"}`}>
        {l.season === "Career" ? "Career" : l.season}
      </th>
      <td className={`${td} text-left`}>{l.team || "–"}</td>
      <td className={td}>{l.gp}</td><td className={td}>{l.gs}</td>
      <td className={td}>{num(l.mpg)}</td>
      <td className={`${td} font-semibold`}>{num(l.ppg)}</td>
      <td className={td}>{num(l.rpg)}</td><td className={td}>{num(l.apg)}</td>
      <td className={td}>{num(l.spg)}</td><td className={td}>{num(l.bpg)}</td>
      <td className={td}>{pct(l.fg_pct)}</td><td className={td}>{pct(l.fg3_pct)}</td>
      <td className={td}>{pct(l.ft_pct)}</td><td className={td}>{pct(l.ts_pct)}</td>
    </tr>
  );
  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-surface">
      <table className="num w-full min-w-[720px] border-collapse text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-line">
            <th scope="col" className="sticky left-0 bg-surface px-3 py-2 text-left text-xs font-medium text-muted">Season</th>
            <th scope="col" className={`${th} text-left`}>Team</th>
            {["GP", "GS", "MPG", "PPG", "RPG", "APG", "SPG", "BPG", "FG%", "3P%", "FT%", "TS%"].map((h) => (
              <th key={h} scope="col" className={th}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {[...lines].reverse().map((l, i) => row(l, `${l.season}-${l.team}-${i}`))}
          {career && row(career, "career", true)}
        </tbody>
      </table>
    </div>
  );
}

export function PlayerOverview() {
  const { data: p, loading } = usePlayer();
  const [type, setType] = useState<"regular" | "playoffs">("regular");
  if (loading || !p) return <div className="h-64 skeleton rounded-lg bg-surface" aria-busy />;
  if (!p.full_bio_loaded)
    return (
      <div className="rounded-lg border border-dashed border-line p-6 text-sm text-muted">
        <p className="font-medium text-fg">Stats for this player haven’t been loaded yet.</p>
        <p className="mt-1"><SetupHint cmd={`python -m nbadash.ingest player ${p.id}`} />.</p>
      </div>
    );
  const lines = type === "regular" ? p.regular : p.playoffs;
  const career = type === "regular" ? p.career_regular : p.career_playoffs;
  // For traded players the "TOT" row is the season total; otherwise the single row.
  const latest = [...p.regular].reverse().find((l) => l.team === "TOT") ?? p.regular[p.regular.length - 1];
  const chip = (on: boolean) => `min-h-11 rounded-full border px-4 text-sm ${on ? "border-accent bg-surface2 font-semibold" : "border-line text-muted hover:text-fg"}`;
  return (
    <div className="space-y-4">
      {latest && (
        <section aria-label={`${latest.season} season averages`}>
          <h2 className="mb-2 text-sm font-medium text-muted">{latest.season} · {latest.gp} games</h2>
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
            <Tile label="PPG" value={num(latest.ppg)} />
            <Tile label="RPG" value={num(latest.rpg)} />
            <Tile label="APG" value={num(latest.apg)} />
            <Tile label="FG%" value={pct(latest.fg_pct)} />
            <Tile label="3P%" value={pct(latest.fg3_pct)} />
            <Tile label="TS%" value={pct(latest.ts_pct)} />
          </div>
        </section>
      )}
      <section aria-label="Season by season">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-medium text-muted">Per game</h2>
          <div role="group" aria-label="Season type" className="flex gap-2">
            <button className={chip(type === "regular")} aria-pressed={type === "regular"} onClick={() => setType("regular")}>Regular season</button>
            <button className={chip(type === "playoffs")} aria-pressed={type === "playoffs"} onClick={() => setType("playoffs")}>Playoffs</button>
          </div>
        </div>
        {lines.length ? <Table lines={lines} career={career} caption={`${p.name} ${type} season per-game stats`} />
          : <p className="rounded-lg border border-line bg-surface p-6 text-center text-muted">No playoff games on record.</p>}
        <p className="mt-2 text-xs text-muted">TS% = true shooting. “TOT” rows combine a season spent with more than one team.</p>
      </section>
    </div>
  );
}
