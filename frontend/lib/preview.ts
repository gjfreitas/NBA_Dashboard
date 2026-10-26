/** Pure helpers for the Preview tab's schedule context. */
import type { RecordSplit, TeamContext } from "./types";

export function restText(c: Pick<TeamContext, "days_rest" | "back_to_back"> | null | undefined): string {
  if (!c || c.days_rest == null) return "–";
  if (c.back_to_back) return "Back-to-back";
  return `${c.days_rest} ${c.days_rest === 1 ? "day" : "days"} rest`;
}

/** Who has more rest, and by how much. Nothing when the difference is under a day or either side is unknown. */
export function restEdge(away: TeamContext | null | undefined, home: TeamContext | null | undefined, awayAbbr: string, homeAbbr: string): string | null {
  if (away?.days_rest == null || home?.days_rest == null) return null;
  const d = home.days_rest - away.days_rest;
  if (d === 0) return null;
  const who = d > 0 ? homeAbbr : awayAbbr;
  const n = Math.abs(d);
  return `${who} has ${n} more ${n === 1 ? "day" : "days"} of rest`;
}

export const recordText = (r: RecordSplit | null | undefined) => (r ? `${r.w}-${r.l}` : "–");

export const marginText = (r: RecordSplit | null | undefined) =>
  r?.margin == null ? "" : `${r.margin > 0 ? "+" : ""}${r.margin.toFixed(1)}`;

/** "W3" -> "Won 3", "L1" -> "Lost 1" */
export function streakText(s: string | null | undefined): string {
  const m = /^([WL])(\d+)$/.exec(s ?? "");
  return m ? `${m[1] === "W" ? "Won" : "Lost"} ${m[2]}` : "–";
}
