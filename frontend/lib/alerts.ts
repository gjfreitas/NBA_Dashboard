/** Alerts for followed players and teams: injury-report changes and prop-line moves. Pure logic; storage and polling live elsewhere. */
import type { InjuryChange } from "./types";
import type { WatchItem } from "./watchlist";

// (the same wording as changeText in availability.ts, which this file cannot import: the logic tests run it under plain node)
const changeLine = (c: Pick<InjuryChange, "kind" | "from_status" | "to_status">) =>
  c.kind === "added" ? `Added to the report: ${c.to_status}` : c.kind === "removed" ? `Removed from the report (was ${c.from_status})` : `${c.from_status} → ${c.to_status}`;

export interface LineMoveIn { player_id: number | null; name: string; team_abbr: string | null; game_id: string; market: string; opening: number; now: number; move: number }
export interface Alert { key: string; kind: "injury" | "line"; text: string; href: string; at: string }
export interface AlertState { seen: string[]; items: Alert[]; unread: number; started: boolean }

export const EMPTY_ALERTS: AlertState = { seen: [], items: [], unread: 0, started: false };
export const STORAGE_KEY = "nba-alerts-v1";
const MAX_SEEN = 600, MAX_ITEMS = 50;

const MARKET_WORD: Record<string, string> = { pts: "points", reb: "rebounds", ast: "assists", fg3m: "threes", pra: "pts+reb+ast", pa: "pts+ast", pr: "pts+reb", ra: "reb+ast", stl: "steals", blk: "blocks", sb: "stl+blk", tov: "turnovers", dd: "a double-double", td: "a triple-double", q1pts: "1st-quarter points", q1reb: "1st-quarter rebounds", q1ast: "1st-quarter assists", h1pts: "1st-half points" };

export interface Watching { players: Set<number>; teamIds: Set<number>; teamAbbrs: Set<string> }

export function watching(items: WatchItem[]): Watching {
  return {
    players: new Set(items.filter((i) => i.kind === "player").map((i) => i.id)),
    teamIds: new Set(items.filter((i) => i.kind === "team").map((i) => i.id)),
    teamAbbrs: new Set(items.filter((i) => i.kind === "team" && i.sub).map((i) => i.sub as string)),
  };
}

/** Alerts that are about someone being watched and have not been seen before. */
export function newAlerts(changes: InjuryChange[], moves: LineMoveIn[], w: Watching, seen: Set<string>, now: string): Alert[] {
  const out: Alert[] = [];
  for (const c of changes) {
    const mine = (c.player_id != null && w.players.has(c.player_id)) || (c.team_id != null && w.teamIds.has(c.team_id));
    const key = `inj:${c.report_id}:${c.player_id ?? c.name}:${c.kind}`;
    if (!mine || seen.has(key)) continue;
    out.push({ key, kind: "injury", text: `${c.name}${c.team_abbr ? ` (${c.team_abbr})` : ""}: ${changeLine(c)}`, href: c.game_id ? `/games/${c.game_id}/preview` : "/injuries", at: c.at_utc });
  }
  for (const m of moves) {
    const mine = (m.player_id != null && w.players.has(m.player_id)) || (m.team_abbr != null && w.teamAbbrs.has(m.team_abbr));
    const key = `mv:${m.game_id}:${m.player_id ?? m.name}:${m.market}:${m.now}`;
    if (!mine || seen.has(key)) continue;
    const up = m.move > 0;
    out.push({ key, kind: "line", text: `${m.name}: ${MARKET_WORD[m.market] ?? m.market} line ${up ? "up" : "down"} ${Math.abs(m.move)} to ${m.now} (was ${m.opening})`, href: m.player_id ? `/players/${m.player_id}/stats` : "/props", at: now });
  }
  return out;
}

/** Every key a poll returned, whoever it is about: used to start a fresh browser without a burst of old news. */
export function allKeys(changes: InjuryChange[], moves: LineMoveIn[]): string[] {
  return [
    ...changes.map((c) => `inj:${c.report_id}:${c.player_id ?? c.name}:${c.kind}`),
    ...moves.map((m) => `mv:${m.game_id}:${m.player_id ?? m.name}:${m.market}:${m.now}`),
  ];
}

export function addAlerts(s: AlertState, fresh: Alert[]): AlertState {
  if (!fresh.length) return s;
  return {
    started: true, seen: [...s.seen, ...fresh.map((a) => a.key)].slice(-MAX_SEEN),
    items: [...fresh, ...s.items].slice(0, MAX_ITEMS), unread: Math.min(s.unread + fresh.length, MAX_ITEMS),
  };
}

export const markRead = (s: AlertState): AlertState => (s.unread ? { ...s, unread: 0 } : s);
export const clearAlerts = (s: AlertState): AlertState => ({ ...s, items: [], unread: 0 });

export function parseAlerts(raw: string | null): AlertState {
  if (!raw) return EMPTY_ALERTS;
  try {
    const d = JSON.parse(raw) as Partial<AlertState>;
    const items = Array.isArray(d.items) ? d.items.filter((a): a is Alert => !!a && typeof a.key === "string" && typeof a.text === "string" && typeof a.href === "string").slice(0, MAX_ITEMS) : [];
    return {
      seen: Array.isArray(d.seen) ? d.seen.filter((k): k is string => typeof k === "string").slice(-MAX_SEEN) : [],
      items, unread: Number.isInteger(d.unread) ? Math.max(0, Math.min(d.unread as number, items.length)) : 0, started: d.started === true,
    };
  } catch {
    return EMPTY_ALERTS;
  }
}
