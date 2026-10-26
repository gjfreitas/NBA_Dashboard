/** Types and pure helpers for the slate props board. */
export interface SlateBookLine { book: string; line: number; over_price: number | null; under_price: number | null; opening_line: number; updated_at: string | null }
export interface SlatePrice { book: string; price: number }
export interface SlateMarket { line: number; best_over: SlatePrice | null; best_under: SlatePrice | null; books: SlateBookLine[] }
export interface SlatePlayer {
  player_id: number | null; name: string; position: string | null; team_abbr: string | null;
  injury: { status: string; reason: string } | null; markets: Record<string, SlateMarket>;
}
export interface SlateTeam { id: number; abbr: string | null; name: string }
export interface SlateGame { game_id: string; start_utc: string | null; status: number; away: SlateTeam; home: SlateTeam; players: SlatePlayer[] }
export interface Slate { date: string; as_of: string | null; games: SlateGame[] }

/** Market keys in the order the Stats tab uses; anything unknown goes last. */
export const MARKET_ORDER = ["pts", "reb", "ast", "fg3m", "pra", "pa", "pr", "ra", "dd", "td", "q1pts", "q1reb", "q1ast", "h1pts", "stl", "blk", "sb", "tov"];
/** Yes/No markets: the stored line is always 0.5, "over" is the Yes price and "under" the No price. */
export const BINARY_MARKETS = ["dd", "td"];
export const isBinaryMarket = (m: string) => BINARY_MARKETS.includes(m);
export const MARKET_LABEL: Record<string, string> = {
  pts: "Points", reb: "Rebounds", ast: "Assists", fg3m: "Threes", pra: "Pts+Reb+Ast", pa: "Pts+Ast", pr: "Pts+Reb", ra: "Reb+Ast", stl: "Steals", blk: "Blocks", sb: "Stl+Blk", tov: "Turnovers",
  dd: "Double-double", td: "Triple-double", q1pts: "1Q Points", q1reb: "1Q Rebounds", q1ast: "1Q Assists", h1pts: "1H Points",
};

/** Markets that appear anywhere on the slate, in display order. */
export function slateMarkets(s: Slate | null | undefined): string[] {
  const seen = new Set<string>();
  for (const g of s?.games ?? []) for (const p of g.players) for (const m of Object.keys(p.markets)) seen.add(m);
  const rank = (m: string) => { const i = MARKET_ORDER.indexOf(m); return i < 0 ? 99 : i; };
  return [...seen].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
}

/** Players of a team who have a line in this market, filtered by a name search. Order is kept (stars first, from the server). */
export function playersFor(game: SlateGame, side: "away" | "home", market: string, query: string): SlatePlayer[] {
  const abbr = game[side].abbr;
  const q = query.trim().toLowerCase();
  return game.players.filter((p) => p.team_abbr === abbr && market in p.markets && (!q || p.name.toLowerCase().includes(q)));
}

/** Players listed for a game that are not placed on either side (a recent trade, say): shown separately, never dropped. */
export function unplaced(game: SlateGame, market: string, query: string): SlatePlayer[] {
  const q = query.trim().toLowerCase();
  return game.players.filter((p) => p.team_abbr == null && market in p.markets && (!q || p.name.toLowerCase().includes(q)));
}

/** "live" / "final" once a game has started; otherwise null (show the tip time). */
export const gameState = (g: Pick<SlateGame, "status">): "live" | "final" | null => (g.status === 2 ? "live" : g.status === 3 ? "final" : null);
