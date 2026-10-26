/** Pure helpers for injury / lineup display. */
import type { InjuryChange, InjuryOut, InjuryStatus, TeamAvailabilitySummary } from "./types";

export const STATUS_ORDER: InjuryStatus[] = ["Out", "Doubtful", "Questionable", "Probable", "Available"];

/** Plain-language meaning of each official status, for tooltips and the page footnote. */
export const STATUS_MEANING: Record<InjuryStatus, string> = {
  Out: "Will not play",
  Doubtful: "Unlikely to play",
  Questionable: "Uncertain: about a 50/50 call",
  Probable: "Likely to play",
  Available: "Cleared to play",
};

export const severity = (s: string) => {
  const i = STATUS_ORDER.indexOf(s as InjuryStatus);
  return i === -1 ? STATUS_ORDER.length : i;
};

/** "Injury/Illness - Left Ankle Sprain" -> { kind: "Injury/Illness", detail: "Left Ankle Sprain" }. Other reasons ("Not With Team") have no detail. */
export function splitReason(reason: string): { kind: string; detail: string } {
  const i = reason.indexOf(" - ");
  return i === -1 ? { kind: reason, detail: "" } : { kind: reason.slice(0, i), detail: reason.slice(i + 3) };
}

/** Short human reason: the injury detail when there is one, otherwise the whole text ("G League - Two-Way", "Not With Team"). */
export function shortReason(reason: string): string {
  const { kind, detail } = splitReason(reason);
  return kind === "Injury/Illness" && detail ? detail : reason;
}

export interface GameGroup { key: string; matchup: string | null; date: string | null; time: string | null; gameId: string | null; entries: InjuryOut[] }

/** Group the report by game (it arrives sorted by date/game), each group's entries most severe first. */
export function groupByGame(entries: InjuryOut[]): GameGroup[] {
  const groups = new Map<string, GameGroup>();
  for (const e of entries) {
    const key = `${e.game_date ?? ""}|${e.matchup ?? e.game_id ?? "?"}`;
    if (!groups.has(key)) groups.set(key, { key, matchup: e.matchup, date: e.game_date, time: e.game_time, gameId: e.game_id, entries: [] });
    groups.get(key)!.entries.push(e);
  }
  for (const g of groups.values()) g.entries.sort((a, b) => severity(a.status) - severity(b.status) || (a.team_abbr ?? "").localeCompare(b.team_abbr ?? "") || a.name.localeCompare(b.name));
  return [...groups.values()];
}

export const countByStatus = (entries: InjuryOut[]) => {
  const out: Record<string, number> = {};
  for (const e of entries) out[e.status] = (out[e.status] ?? 0) + 1;
  return out;
};

/** "CHI@MIL" -> { away: "CHI", home: "MIL" } */
export function teamsOfMatchup(m: string | null): { away: string; home: string } | null {
  const [away, home] = (m ?? "").split("@");
  return away && home ? { away, home } : null;
}

export const ageText = (minutes: number) =>
  minutes < 1 ? "just now" : minutes < 60 ? `${minutes} min ago` : minutes < 48 * 60 ? `${Math.round(minutes / 60)} h ago` : `${Math.round(minutes / 1440)} days ago`;

/** The report's own time is Eastern wall-clock ("2026-10-23T08:00"); show it as-is, labelled ET. */
export function reportTimeText(publishedAt: string): string {
  const [d, t] = publishedAt.split("T");
  const [h, m] = (t ?? "00:00").split(":").map(Number);
  const hour12 = h % 12 === 0 ? 12 : h % 12;
  const date = new Date(`${d}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });
  return `${date}, ${hour12}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"} ET`;
}

/** "2026-11-29" -> "Nov 29"; a different year than `today`'s is shown ("Jul 1, 2027"). */
export function returnText(iso: string | null | undefined, today: Date = new Date()): string {
  if (!iso) return "";
  const d = new Date(`${iso.slice(0, 10)}T12:00:00`);
  if (Number.isNaN(d.getTime())) return "";
  const opts: Intl.DateTimeFormatOptions = d.getFullYear() === today.getFullYear() ? { month: "short", day: "numeric" } : { month: "short", day: "numeric", year: "numeric" };
  return d.toLocaleDateString("en-US", opts);
}

/** One line describing a change between reports, e.g. "Questionable → Out", "Added to the report: Probable", "Removed from the report". */
export function changeText(c: Pick<InjuryChange, "kind" | "from_status" | "to_status">): string {
  if (c.kind === "added") return `Added to the report: ${c.to_status}`;
  if (c.kind === "removed") return `Removed from the report (was ${c.from_status})`;
  return `${c.from_status} → ${c.to_status}`;
}

/** Worse news first (a player ruled out matters more than one cleared), then newest. */
export function sortChanges<T extends Pick<InjuryChange, "kind" | "at_utc">>(list: T[]): T[] {
  const rank = { worsened: 0, added: 1, improved: 2, removed: 3 } as const;
  return [...list].sort((a, b) => b.at_utc.localeCompare(a.at_utc) || rank[a.kind] - rank[b.kind]);
}

/** ESPN says "Day-To-Day"; show it the way people say it. */
export const espnStatusText = (s: string) => (s === "Day-To-Day" ? "Day-to-day" : s);

export const ESPN_NOTE = "ESPN is unofficial and uses its own wording: Day-to-day covers anything from Probable to Doubtful. Return dates are ESPN's estimates.";

/** "Nikola Jokić" -> "Jokić"; suffixes stay with the surname ("Trey Murphy III" -> "Murphy III"). */
export function surname(name: string): string {
  const parts = name.trim().split(/\s+/);
  const suffix = /^(Jr\.?|Sr\.?|II|III|IV|V)$/i;
  return parts.length > 2 && suffix.test(parts[parts.length - 1]) ? parts.slice(-2).join(" ") : parts[parts.length - 1] ?? name;
}

/** What to say about one team on a scoreboard card, or null when there is nothing worth a line. */
export function teamNote(t: TeamAvailabilitySummary): string | null {
  const parts = t.key_players.map((k) => `${surname(k.name)} ${k.status.toLowerCase()}`);
  if (t.others_out > 0) parts.push(`${parts.length ? "+" : ""}${t.others_out} ${parts.length ? "more " : ""}out`);
  return parts.length ? parts.join(", ") : null;
}
