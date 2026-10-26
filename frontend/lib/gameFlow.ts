/** Pure logic for a game's flow: lead changes, scoring runs, and a rough win probability. No React, no I/O. */
import type { Play } from "./types";

const clockSeconds = (clock: string) => {
  const [m, s] = clock.split(":").map(Number);
  return (m || 0) * 60 + (s || 0);
};

/** Game time left, in seconds, within regulation or the current overtime. */
export function remainingSeconds(period: number, clock: string): number {
  const left = clockSeconds(clock);
  return period <= 4 ? (4 - period) * 720 + left : left;
}

/** Seconds played since tip-off (overtimes are 5 minutes). */
export function elapsedSeconds(period: number, clock: string): number {
  return period <= 4 ? (period - 1) * 720 + 720 - clockSeconds(clock) : 2880 + (period - 5) * 300 + 300 - clockSeconds(clock);
}

// Standard normal CDF (Abramowitz-Stegun 7.1.26 via erf), accurate to about 1e-7.
function phi(z: number): number {
  if (z === 0) return 0.5;
  const t = 1 / (1 + 0.3275911 * Math.abs(z) / Math.SQRT2);
  const poly = t * (0.254829592 + t * (-0.284496736 + t * (1.421413741 + t * (-1.453152027 + t * 1.061405429))));
  const erf = 1 - poly * Math.exp(-(z * z) / 2);
  return 0.5 * (1 + (z >= 0 ? erf : -erf));
}

/**
 * Spread of the margin over a full game, in points. Published score-and-time models use roughly 12 to 13.5; 13.5 is used because the first
 * version (12) read too sure of itself early (93% for a 15-point lead after one quarter). Still not fitted to data: no quarter-by-quarter history is stored.
 */
export const MARGIN_SD = 13.5;

/**
 * Probability that the home team wins, from the score margin and time left only: the remaining margin is modelled as a random walk,
 * so its spread shrinks with the square root of time left. It knows nothing about team strength, possession or foul trouble,
 * so treat it as a rough guide. `lead` is home minus away.
 */
export function winProbability(lead: number, remaining: number): number {
  const left = Math.max(0, remaining);
  if (left === 0) return lead > 0 ? 1 : lead < 0 ? 0 : 0.5;
  const minutes = left / 60;
  const sd = MARGIN_SD * Math.sqrt(minutes / 48);
  return phi(lead / Math.max(sd, 0.05)); // a tie with time left is a coin flip
}

export interface FlowPoint { t: number; lead: number; prob: number; home: number; away: number; period: number; clock: string }

/** The score after every scoring play, with the win probability at that moment. Starts at tip-off, 50%. */
export function flowPoints(plays: Play[]): FlowPoint[] {
  const out: FlowPoint[] = [{ t: 0, lead: 0, prob: 0.5, home: 0, away: 0, period: 1, clock: "12:00" }];
  for (const p of plays) {
    if (p.points <= 0) continue;
    const lead = p.home_score - p.away_score;
    out.push({ t: elapsedSeconds(p.period, p.clock), lead, prob: winProbability(lead, remainingSeconds(p.period, p.clock)), home: p.home_score, away: p.away_score, period: p.period, clock: p.clock });
  }
  return out;
}

export interface FlowStats {
  leadChanges: number; ties: number;
  biggestLeadHome: number; biggestLeadAway: number;
  longestRunHome: number; longestRunAway: number;
}

/** Lead changes (a different team in front than the last time someone led), times the game was tied, biggest leads, longest unanswered runs. */
export function flowStats(plays: Play[]): FlowStats {
  let home = 0, away = 0, leader = 0, changes = 0, ties = 0;
  let bigH = 0, bigA = 0, runTeam = 0, run = 0, runH = 0, runA = 0;
  for (const p of plays) {
    if (p.points <= 0) continue;
    const dh = p.home_score - home, da = p.away_score - away;
    home = p.home_score; away = p.away_score;
    const scorer = dh > da ? 1 : da > dh ? -1 : 0;
    if (scorer !== 0) {
      run = scorer === runTeam ? run + Math.max(dh, da) : Math.max(dh, da);
      runTeam = scorer;
      if (scorer === 1) runH = Math.max(runH, run); else runA = Math.max(runA, run);
    }
    const lead = home - away;
    if (lead === 0) ties += 1;
    const now = Math.sign(lead);
    if (now !== 0) {
      if (leader !== 0 && now !== leader) changes += 1;
      leader = now;
    }
    bigH = Math.max(bigH, lead); bigA = Math.max(bigA, -lead);
  }
  return { leadChanges: changes, ties, biggestLeadHome: bigH, biggestLeadAway: bigA, longestRunHome: runH, longestRunAway: runA };
}
