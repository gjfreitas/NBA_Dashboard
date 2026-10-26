/** Pure logic for a game's shot chart, built from the play-by-play. No React, no I/O. */
import type { Play } from "./types";

export interface ShotPoint {
  id: number; team: string | null; player_id: number | null; period: number; clock: string; made: boolean;
  x: number; y: number; three: boolean; distance: number | null; text: string;
}

/** Field goals that have chart coordinates (free throws are not on the chart; a few early live plays may lack coordinates). */
export function shotPoints(plays: Play[]): ShotPoint[] {
  const out: ShotPoint[] = [];
  for (const p of plays) {
    if (!p.is_shot || p.sx == null || p.sy == null || p.made == null) continue;
    out.push({ id: p.id, team: p.team, player_id: p.player_id, period: p.period, clock: p.clock, made: p.made, x: p.sx, y: p.sy,
      three: p.type === "3pt", distance: p.distance ?? null, text: p.text });
  }
  return out;
}

export interface ShotFilters { team: string | "all"; player: number | "all"; period: number | "all"; result: "all" | "made" | "missed" }
export const ALL_SHOTS: ShotFilters = { team: "all", player: "all", period: "all", result: "all" };

export function filterShots(shots: ShotPoint[], f: ShotFilters): ShotPoint[] {
  return shots.filter((s) => (f.team === "all" || s.team === f.team) && (f.player === "all" || s.player_id === f.player) &&
    (f.period === "all" || s.period === f.period) && (f.result === "all" || (f.result === "made") === s.made));
}

export interface ShotSummary { fga: number; fgm: number; pct: number | null; threeAtt: number; threeMade: number; efg: number | null; avgDistance: number | null }

export function summarize(shots: ShotPoint[]): ShotSummary {
  const fga = shots.length, fgm = shots.filter((s) => s.made).length;
  const threeAtt = shots.filter((s) => s.three).length, threeMade = shots.filter((s) => s.three && s.made).length;
  const dists = shots.map((s) => s.distance).filter((d): d is number => d != null);
  return {
    fga, fgm, pct: fga ? fgm / fga : null, threeAtt, threeMade, efg: fga ? (fgm + 0.5 * threeMade) / fga : null,
    avgDistance: dists.length ? dists.reduce((a, b) => a + b, 0) / dists.length : null,
  };
}

/** Players who took shots in `shots`, most attempts first. */
export function shooters(shots: ShotPoint[]): { id: number; fgm: number; fga: number }[] {
  const m = new Map<number, { id: number; fgm: number; fga: number }>();
  for (const s of shots) {
    if (s.player_id == null) continue;
    const r = m.get(s.player_id) ?? { id: s.player_id, fgm: 0, fga: 0 };
    r.fga += 1;
    if (s.made) r.fgm += 1;
    m.set(s.player_id, r);
  }
  return [...m.values()].sort((a, b) => b.fga - a.fga || b.fgm - a.fgm || a.id - b.id);
}
