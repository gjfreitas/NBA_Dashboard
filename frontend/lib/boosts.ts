/** Types and display helpers for the matchup boosts on the Today page. */
export interface BoostDriver { kind: "style" | "shot" | "position"; label: string; share: number | null; effect_pct: number; detail: string }
export interface Boost {
  player_id: number; name: string; team_abbr: string | null; opp_abbr: string | null; game_id: string; start_utc: string | null; home: boolean;
  boost_pct: number; style_pct: number | null; shot_pct: number | null; position_pct: number | null; headline: string; drivers: BoostDriver[]; ppg: number;
  profile_season: string; opp_games: number; season_weight: number;
}
export interface Boosts { date: string; season: string | null; previous_season: string | null; best: Boost[]; toughest: Boost[]; all: Boost[] }

/** "+8.7%", "-9.4%", "0.0%": a real minus sign is not needed, the colour and the sign carry it. */
export function boostText(v: number): string {
  const r = Math.round(v * 10) / 10;
  return `${r > 0 ? "+" : ""}${r.toFixed(1)}%`;
}

/** How much of the opponent's defence numbers is this season's, in words: "all this season", "40% this season, 60% last", "all last season". */
export function seasonMixText(weight: number, games: number): string {
  if (weight >= 0.995) return `${games} games played: this season’s numbers`;
  if (weight <= 0.005) return `${games} games played: last season’s numbers`;
  const pct = Math.round(weight * 100);
  return `${games} games played: ${pct}% this season, ${100 - pct}% last`;
}
