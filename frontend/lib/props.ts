/** Pure logic for the player Stats tab: markets, filtering, hit rate, averages. No React, no I/O. */
import type { AvgLine, PropGame, PropTeammate, SimilarGame, SimilarPlayer } from "./types";

export interface Market {
  key: string;
  label: string;
  /** value of the market for one game; null = unknown (e.g. quarter data not ingested for that season) */
  get: (g: PropGame) => number | null;
  /** yes/no market (double / triple double): hit = 1, no line */
  binary?: boolean;
}

const sum = (...xs: (number | null)[]) => (xs.some((x) => x == null) ? null : (xs as number[]).reduce((a, b) => a + b, 0));
const categories = (g: PropGame) => [g.pts, g.reb, g.ast, g.stl, g.blk].filter((v) => v >= 10).length;

export const MARKETS: Market[] = [
  { key: "pts", label: "Points", get: (g) => g.pts },
  { key: "ast", label: "Assists", get: (g) => g.ast },
  { key: "reb", label: "Rebounds", get: (g) => g.reb },
  { key: "fg3m", label: "Threes", get: (g) => g.fg3m },
  { key: "pa", label: "Pts+Ast", get: (g) => g.pts + g.ast },
  { key: "pr", label: "Pts+Reb", get: (g) => g.pts + g.reb },
  { key: "ra", label: "Reb+Ast", get: (g) => g.reb + g.ast },
  { key: "pra", label: "Pts+Reb+Ast", get: (g) => g.pts + g.reb + g.ast },
  { key: "dd", label: "Double Double", get: (g) => (categories(g) >= 2 ? 1 : 0), binary: true },
  { key: "td", label: "Triple Double", get: (g) => (categories(g) >= 3 ? 1 : 0), binary: true },
  { key: "q1pts", label: "1Q Points", get: (g) => g.q1_pts },
  { key: "q1ast", label: "1Q Assists", get: (g) => g.q1_ast },
  { key: "q1reb", label: "1Q Rebounds", get: (g) => g.q1_reb },
  { key: "h1pts", label: "1H Points", get: (g) => g.h1_pts },
  { key: "stl", label: "Steals", get: (g) => g.stl },
  { key: "blk", label: "Blocks", get: (g) => g.blk },
  { key: "sb", label: "Stl+Blk", get: (g) => sum(g.stl, g.blk) },
  { key: "tov", label: "Turnovers", get: (g) => g.tov },
  { key: "pf", label: "Fouls", get: (g) => g.pf },
  { key: "fta", label: "FT Attempted", get: (g) => g.fta },
];

export const marketByKey = (key: string) => MARKETS.find((m) => m.key === key) ?? MARKETS[0];

/** Saved market layout: order + hidden set. Points is always on. Unknown keys are dropped, new markets appended. */
export interface MarketPrefs { order: string[]; hidden: string[] }

export function normalizePrefs(raw: unknown): MarketPrefs {
  const known = new Set(MARKETS.map((m) => m.key));
  const r = (raw ?? {}) as Partial<MarketPrefs>;
  const order = (Array.isArray(r.order) ? r.order : []).filter((k): k is string => typeof k === "string" && known.has(k));
  const seen = new Set(order);
  for (const m of MARKETS) if (!seen.has(m.key)) order.push(m.key);
  const hidden = (Array.isArray(r.hidden) ? r.hidden : []).filter((k): k is string => known.has(k) && k !== "pts");
  return { order, hidden };
}

export function visibleMarkets(p: MarketPrefs): Market[] {
  return p.order.filter((k) => !p.hidden.includes(k)).map(marketByKey);
}

// ------------------------------------------------------------------ filters

export interface Filters {
  seasons: string[] | "all";
  games: number | "max";
  venue: "all" | "home" | "away";
  type: "all" | "regular" | "playoffs";
  h2h: boolean;
  b2b: "any" | "yes" | "no";
  result: "any" | "W" | "L";
  minMinutes: number; // 0 = off
  oppDef: "any" | "top10" | "mid" | "bottom10";
  withTm: number[];
  withoutTm: number[];
}

export const DEFAULT_FILTERS: Filters = {
  seasons: "all", games: 20, venue: "all", type: "all", h2h: false, b2b: "any", result: "any", minMinutes: 0,
  oppDef: "any", withTm: [], withoutTm: [],
};

/** Was this teammate on the player's team (same season, same team) on this date? Used for "without X". */
export function wasTeammate(t: PropTeammate, g: PropGame): boolean {
  return t.windows.some((w) => w.season === g.season && w.team_id === g.team_id && g.date >= w.first && g.date <= w.last);
}

export interface Ctx { oppId: number | null; teammates: PropTeammate[] }

export function matches(g: PropGame, f: Filters, ctx: Ctx): boolean {
  if (f.seasons !== "all" && !f.seasons.includes(g.season)) return false;
  if (f.type !== "all" && g.season_type !== f.type) return false;
  if (f.venue !== "all" && g.home !== (f.venue === "home")) return false;
  if (f.h2h && (ctx.oppId == null || g.opp_id !== ctx.oppId)) return false;
  if (f.b2b !== "any") {
    if (g.rest_days == null) return false; // first game of a season: unknown
    if ((g.rest_days === 0) !== (f.b2b === "yes")) return false;
  }
  if (f.result !== "any" && g.result !== f.result) return false;
  if (f.minMinutes > 0 && g.min < f.minMinutes) return false;
  if (f.oppDef !== "any") {
    const r = g.opp_def_rank;
    if (r == null) return false;
    if (f.oppDef === "top10" ? r > 10 : f.oppDef === "bottom10" ? r < 21 : r < 11 || r > 20) return false;
  }
  for (const id of f.withTm) if (!g.mates.includes(id)) return false;
  for (const id of f.withoutTm) {
    const t = ctx.teammates.find((x) => x.player_id === id);
    if (g.mates.includes(id) || !t || !wasTeammate(t, g)) return false;
  }
  return true;
}

/** Everything the chart and header need: the filtered pool, and the last-N sample of it (chronological). */
export function selectGames(all: PropGame[], f: Filters, ctx: Ctx) {
  const pool = all.filter((g) => matches(g, f, ctx));
  const sample = f.games === "max" ? pool : pool.slice(-f.games);
  // baseline for the "vs usual" deltas: same seasons, no splits
  const baseline = all.filter((g) => f.seasons === "all" || f.seasons.includes(g.season));
  return { pool, sample, baseline };
}

// ------------------------------------------------------------------- stats

export const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);

/** Market values of a sample, dropping games where the value is unknown. */
export function values(games: PropGame[], m: Market): { game: PropGame; value: number }[] {
  const out: { game: PropGame; value: number }[] = [];
  for (const game of games) {
    const v = m.get(game);
    if (v != null) out.push({ game, value: v });
  }
  return out;
}

/** Default line: the sample's average snapped to a half point (x.5), the way lines are normally set. */
export function defaultLine(vals: number[]): number {
  const avg = mean(vals);
  return avg == null ? 0.5 : Math.max(0.5, Math.floor(avg) + 0.5);
}

export interface HitRate { over: number; total: number; pct: number | null }
export function hitRate(vals: number[], line: number, binary = false): HitRate {
  const over = vals.filter((v) => (binary ? v >= 1 : v > line)).length;
  return { over, total: vals.length, pct: vals.length ? over / vals.length : null };
}

export interface Averages { pts: number | null; ast: number | null; reb: number | null; fg3m: number | null; min: number | null; usg: number | null; fga: number | null }
export function averages(games: PropGame[]): Averages {
  const avg = (f: (g: PropGame) => number | null) => mean(games.map(f).filter((v): v is number => v != null));
  return {
    pts: avg((g) => g.pts), ast: avg((g) => g.ast), reb: avg((g) => g.reb), fg3m: avg((g) => g.fg3m),
    min: avg((g) => g.min), usg: avg((g) => g.usg), fga: avg((g) => g.fga),
  };
}

// ------------------------------------------------------------ similar players

export interface SimilarRow {
  game: SimilarGame;
  value: number;
  /** the player's own season average of this market; the benchmark, since no sportsbook lines are used */
  avg: number | null;
  diff: number | null;
  diffPct: number | null;
}

/** Market value of a season-average line (linear markets only; yes/no markets have no meaningful average). */
export function averageValue(m: Market, avg: AvgLine): number | null {
  if (m.binary) return null;
  return m.get(avg as unknown as PropGame);
}

export function similarRows(games: SimilarGame[], players: SimilarPlayer[], m: Market): SimilarRow[] {
  const avgOf = new Map(players.map((p) => [p.player_id, averageValue(m, p.averages)]));
  const rows: SimilarRow[] = [];
  for (const game of games) {
    const value = m.get(game);
    if (value == null) continue;
    const avg = avgOf.get(game.player_id) ?? null;
    const diff = avg == null ? null : value - avg;
    rows.push({ game, value, avg, diff, diffPct: avg == null || avg === 0 ? null : (diff as number) / avg });
  }
  return rows;
}

export interface SimilarSummary { avgDiff: number | null; avgDiffPct: number | null; hit: HitRate }

/** Hit = beat the player's own average (or achieved, for yes/no markets). A tie with the average is not a hit. */
export function similarSummary(rows: SimilarRow[], binary: boolean): SimilarSummary {
  const diffs = rows.map((r) => r.diff).filter((v): v is number => v != null);
  const pcts = rows.map((r) => r.diffPct).filter((v): v is number => v != null);
  const hits = binary ? rows.filter((r) => r.value >= 1).length : rows.filter((r) => r.diff != null && r.diff > 0).length;
  const total = binary ? rows.length : rows.filter((r) => r.diff != null).length;
  return { avgDiff: mean(diffs), avgDiffPct: mean(pcts), hit: { over: hits, total, pct: total ? hits / total : null } };
}
