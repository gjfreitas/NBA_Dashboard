/** A quick look at one player against one line: how recent games, the season, tonight's venue and opponent compare. Pure, no I/O. */
export interface Row { date: string; season: string; home: boolean; opp_id: number | null; value: number }
export interface Avg { avg: number | null; n: number }
export interface Analysis {
  last5: number | null; last10: number | null; season: Avg; seasonLabel: string | null;
  hit10: { over: number; total: number }; hitSeason: { over: number; total: number };
  venue: Avg; vsOpp: Avg; strip: { value: number; over: boolean; push: boolean }[]; games: number;
}

const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);
const avgOf = (xs: number[]): Avg => ({ avg: mean(xs), n: xs.length });

/** `rows` in any order. `home` is tonight's venue for the player; `oppId` tonight's opponent. */
export function analyze(rows: Row[], line: number, home: boolean, oppId: number | null): Analysis {
  const sorted = [...rows].sort((a, b) => a.date.localeCompare(b.date));
  const season = sorted.length ? sorted[sorted.length - 1].season : null;
  const inSeason = sorted.filter((r) => r.season === season);
  const last10 = sorted.slice(-10);
  const hit = (rs: Row[]) => ({ over: rs.filter((r) => r.value > line).length, total: rs.length });
  return {
    last5: mean(sorted.slice(-5).map((r) => r.value)), last10: mean(last10.map((r) => r.value)),
    season: avgOf(inSeason.map((r) => r.value)), seasonLabel: season,
    hit10: hit(last10), hitSeason: hit(inSeason),
    venue: avgOf(inSeason.filter((r) => r.home === home).map((r) => r.value)),
    vsOpp: oppId == null ? { avg: null, n: 0 } : avgOf(sorted.filter((r) => r.opp_id === oppId).map((r) => r.value)),
    strip: last10.map((r) => ({ value: r.value, over: r.value > line, push: r.value === line })), games: sorted.length,
  };
}
