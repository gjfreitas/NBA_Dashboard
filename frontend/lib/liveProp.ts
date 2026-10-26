/** Live prop tracking: where a player stands against a line, and a pace projection. Pure, no I/O. */
export interface LiveStats { points: number; rebounds: number; assists: number; steals: number; blocks: number; turnovers: number; tpm: number }

/** The stat a market counts, from a live box-score line; null for markets we cannot compute live. */
export function statFor(market: string, s: LiveStats): number | null {
  switch (market) {
    case "pts": return s.points;
    case "reb": return s.rebounds;
    case "ast": return s.assists;
    case "fg3m": return s.tpm;
    case "stl": return s.steals;
    case "blk": return s.blocks;
    case "tov": return s.turnovers;
    case "pa": return s.points + s.assists;
    case "pr": return s.points + s.rebounds;
    case "ra": return s.rebounds + s.assists;
    case "pra": return s.points + s.rebounds + s.assists;
    case "sb": return s.steals + s.blocks;
    default: return null;
  }
}

/** "33:15" -> 33.25 */
export function parseMinutes(m: string | null | undefined): number {
  const [mm, ss] = (m ?? "").split(":").map(Number);
  return Number.isFinite(mm) ? mm + (Number.isFinite(ss) ? ss : 0) / 60 : 0;
}

/**
 * Projected final total: what he has now, plus his rate so far times the minutes he is still likely to play. Those are his usual minutes
 * minus the ones already played, but never more than the game time left. Null until he has played `MIN_MINUTES`, when a rate means nothing,
 * and null with no usual minutes to go on. It ignores matchup, foul trouble and blowouts, so it is a pace estimate, not a forecast.
 */
export const MIN_MINUTES = 4;
export function projection(current: number, minutesPlayed: number, usualMinutes: number | null | undefined, gameMinutesLeft: number): number | null {
  if (usualMinutes == null || minutesPlayed < MIN_MINUTES) return null;
  const left = Math.min(Math.max(usualMinutes - minutesPlayed, 0), Math.max(gameMinutesLeft, 0));
  return current + (current / minutesPlayed) * left;
}

export type PropState = "over" | "under" | "pace-over" | "pace-under" | "waiting" | "final-over" | "final-under" | "push";

/** Where the prop stands. "over" means the line is already beaten (the over cannot lose any more). */
export function propState(current: number, line: number, projected: number | null, gameOver: boolean, played: boolean): PropState {
  if (gameOver) return current > line ? "final-over" : current < line ? "final-under" : "push";
  if (current > line) return "over";
  if (!played || projected == null) return "waiting";
  return projected > line ? "pace-over" : "pace-under";
}

export const STATE_TEXT: Record<PropState, string> = {
  over: "Over hit", under: "Under", "pace-over": "Pace: over", "pace-under": "Pace: under", waiting: "Waiting", "final-over": "Over", "final-under": "Under", push: "Push",
};
