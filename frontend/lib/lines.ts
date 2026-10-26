/** Sportsbook prop lines: display helpers. */
export interface BookLine { book: string; line: number; over_price: number | null; under_price: number | null; opening_line: number; updated_at: string | null }
export interface PlayerLines { game_id: string | null; source: string | null; as_of: string | null; markets: Record<string, BookLine[]> }

const BOOKS: Record<string, string> = {
  draftkings: "DraftKings", fanduel: "FanDuel", betmgm: "BetMGM", caesars: "Caesars", espnbet: "ESPN BET", bovada: "Bovada", williamhill_us: "Caesars",
  unibet: "Unibet", pointsbet: "PointsBet", fanatics: "Fanatics", pinnacle: "Pinnacle", prizepicks: "PrizePicks", betrivers: "BetRivers", betonlineag: "BetOnline", mybookie: "MyBookie", lowvig: "LowVig", hardrockbet: "Hard Rock",
};

/** "draftkings" -> "DraftKings"; unknown keys are tidied ("some_book" -> "Some Book"). */
export const bookName = (key: string) => BOOKS[key] ?? key.replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

/** American odds with an explicit plus sign for underdogs: 100 -> "+100", -115 -> "-115". */
export const priceText = (p: number | null | undefined) => (p == null ? "" : p > 0 ? `+${p}` : `${p}`);

/** How far the line has moved since it first appeared: "+1" / "-0.5", or "" if unchanged. */
export function moveText(line: number, opening: number): string {
  const d = Math.round((line - opening) * 100) / 100;
  return d === 0 ? "" : d > 0 ? `+${d}` : `${d}`;
}

/** The line most books agree on (the median), for a "consensus" default. Null with no lines. */
export function consensus(lines: BookLine[]): number | null {
  if (!lines.length) return null;
  const s = lines.map((l) => l.line).sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

/** "theoddsapi+sportsgameodds" -> "The Odds API and SportsGameOdds" */
export function sourceName(source: string | null | undefined): string {
  const names: Record<string, string> = { theoddsapi: "The Odds API", sportsgameodds: "SportsGameOdds" };
  const parts = (source ?? "").split("+").filter(Boolean).map((p) => names[p] ?? p);
  return parts.length ? parts.join(" and ") : "an odds provider";
}
