/** Types and pure helpers for the Today briefing. */
export interface TodayKeyAbsence { player_id: number | null; name: string; status: string; ppg: number | null }
export interface TodayTeam {
  id: number; abbr: string | null; name: string; record: string | null; days_rest: number | null; back_to_back: boolean; streak: string | null;
  lineup_status: "Expected" | "Confirmed" | null; key_out: TodayKeyAbsence[]; others_out: number;
}
export interface TodayGame { game_id: string; start_utc: string | null; status: number; away: TodayTeam; home: TodayTeam; players_with_lines: number }
export interface TodayMove { player_id: number | null; name: string; team_abbr: string | null; game_id: string; market: string; opening: number; now: number; move: number; books: number; injury: string | null }
export interface Today { date: string; games: TodayGame[]; moves: TodayMove[] }

/** "2 days rest", "back-to-back", or "" when unknown. */
export function restLabel(t: Pick<TodayTeam, "days_rest" | "back_to_back">): string {
  if (t.days_rest == null) return "";
  if (t.back_to_back) return "Back-to-back";
  return `${t.days_rest} ${t.days_rest === 1 ? "day" : "days"} rest`;
}

/** Teams on the second night of a back-to-back, e.g. ["CHI", "MIL"]. */
export const backToBackTeams = (games: TodayGame[]): string[] =>
  games.flatMap((g) => [g.away, g.home]).filter((t) => t.back_to_back && t.abbr).map((t) => t.abbr as string);

/** Where a followed team plays today: "at MIL" / "vs CHI" and the game id, or null if it has no game. */
export function gameFor(games: TodayGame[], abbr: string | null | undefined): { game: TodayGame; label: string } | null {
  if (!abbr) return null;
  for (const g of games) {
    if (g.home.abbr === abbr) return { game: g, label: `vs ${g.away.abbr}` };
    if (g.away.abbr === abbr) return { game: g, label: `at ${g.home.abbr}` };
  }
  return null;
}
