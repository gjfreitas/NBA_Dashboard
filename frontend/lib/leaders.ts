/** Leaderboard stat definitions and number formatting. Pure; no React. */

export type Kind = "count" | "pct" | "usg" | "total" | "rating" | "signed";

export interface StatDef {
  key: string;
  label: string;
  /** short column header */
  short: string;
  kind: Kind;
  /** team boards only: the lowest value is best (turnovers, defensive rating) */
  lower?: boolean;
}

/** Chips on the player board, in display order. Keys match the API's `stat` parameter. */
export const PLAYER_STATS: StatDef[] = [
  { key: "pts", label: "Points", short: "PTS", kind: "count" },
  { key: "reb", label: "Rebounds", short: "REB", kind: "count" },
  { key: "ast", label: "Assists", short: "AST", kind: "count" },
  { key: "stl", label: "Steals", short: "STL", kind: "count" },
  { key: "blk", label: "Blocks", short: "BLK", kind: "count" },
  { key: "fg3m", label: "Threes made", short: "3PM", kind: "count" },
  { key: "tov", label: "Turnovers", short: "TOV", kind: "count" },
  { key: "min", label: "Minutes", short: "MIN", kind: "count" },
  { key: "pra", label: "Pts+Reb+Ast", short: "PRA", kind: "count" },
  { key: "fg_pct", label: "FG%", short: "FG%", kind: "pct" },
  { key: "fg3_pct", label: "3P%", short: "3P%", kind: "pct" },
  { key: "ft_pct", label: "FT%", short: "FT%", kind: "pct" },
  { key: "efg_pct", label: "eFG%", short: "eFG%", kind: "pct" },
  { key: "ts_pct", label: "TS%", short: "TS%", kind: "pct" },
  { key: "usg", label: "Usage %", short: "USG%", kind: "usg" },
  { key: "dd", label: "Double-doubles", short: "DD", kind: "total" },
  { key: "td", label: "Triple-doubles", short: "TD", kind: "total" },
];

export const TEAM_STATS: StatDef[] = [
  { key: "net_rtg", label: "Net rating", short: "NET", kind: "signed" },
  { key: "off_rtg", label: "Offensive rating", short: "OFF", kind: "rating" },
  { key: "def_rtg", label: "Defensive rating", short: "DEF", kind: "rating", lower: true },
  { key: "plus_minus", label: "Point differential", short: "+/−", kind: "signed" },
  { key: "pace", label: "Pace", short: "PACE", kind: "rating" },
  { key: "pts", label: "Points", short: "PTS", kind: "count" },
  { key: "reb", label: "Rebounds", short: "REB", kind: "count" },
  { key: "ast", label: "Assists", short: "AST", kind: "count" },
  { key: "stl", label: "Steals", short: "STL", kind: "count" },
  { key: "blk", label: "Blocks", short: "BLK", kind: "count" },
  { key: "tov", label: "Turnovers", short: "TOV", kind: "count", lower: true },
  { key: "fg_pct", label: "FG%", short: "FG%", kind: "pct" },
  { key: "fg3_pct", label: "3P%", short: "3P%", kind: "pct" },
  { key: "ft_pct", label: "FT%", short: "FT%", kind: "pct" },
  { key: "ts_pct", label: "TS%", short: "TS%", kind: "pct" },
];

export const playerStat = (key: string) => PLAYER_STATS.find((s) => s.key === key) ?? PLAYER_STATS[0];
export const teamStat = (key: string) => TEAM_STATS.find((s) => s.key === key) ?? TEAM_STATS[0];

/** Per-game / totals only makes sense for counting stats; rates, usage and double-double counts ignore it. */
export const modeApplies = (s: StatDef) => s.kind === "count";

export function formatStat(kind: Kind, v: number | null | undefined, mode: "pg" | "total" = "pg"): string {
  if (v == null || Number.isNaN(v)) return "–";
  switch (kind) {
    case "pct": return (v * 100).toFixed(1);
    case "usg":
    case "rating": return v.toFixed(1);
    case "signed": return v > 0 ? `+${v.toFixed(1)}` : v.toFixed(1);
    case "total": return Math.round(v).toLocaleString("en-US");
    case "count": return mode === "total" ? Math.round(v).toLocaleString("en-US") : v.toFixed(1);
  }
}

/** Search-param state for the page, with defaults left out of the URL. */
export interface LeadersState {
  view: "players" | "teams";
  stat: string;
  season: string | null;
  type: "regular" | "playoffs";
  mode: "pg" | "total";
  qualified: boolean;
  limit: number;
}

export const DEFAULT_LIMIT = 25;

export function parseState(sp: URLSearchParams): LeadersState {
  const view = sp.get("view") === "teams" ? "teams" : "players";
  const defs = view === "teams" ? TEAM_STATS : PLAYER_STATS;
  const stat = sp.get("stat");
  const limit = Number(sp.get("limit"));
  return {
    view,
    stat: stat && defs.some((d) => d.key === stat) ? stat : defs[0].key,
    season: sp.get("season"),
    type: sp.get("type") === "playoffs" ? "playoffs" : "regular",
    mode: sp.get("mode") === "total" ? "total" : "pg",
    qualified: sp.get("all") !== "1",
    limit: Number.isFinite(limit) && limit >= DEFAULT_LIMIT ? Math.min(Math.floor(limit), 300) : DEFAULT_LIMIT,
  };
}

/** Inverse of parseState: only non-default values are written. */
export function toSearch(s: LeadersState): string {
  const p = new URLSearchParams();
  if (s.view === "teams") p.set("view", "teams");
  const first = (s.view === "teams" ? TEAM_STATS : PLAYER_STATS)[0].key;
  if (s.stat !== first) p.set("stat", s.stat);
  if (s.season) p.set("season", s.season);
  if (s.view === "players") {
    if (s.type === "playoffs") p.set("type", "playoffs");
    if (s.mode === "total") p.set("mode", "total");
    if (!s.qualified) p.set("all", "1");
    if (s.limit !== DEFAULT_LIMIT) p.set("limit", String(s.limit));
  }
  const q = p.toString();
  return q ? `?${q}` : "";
}
