/** Side-by-side splits of one market: how a player does at home vs away, in wins vs losses, on short vs long rest, and so on. */
import type { Market } from "./props";
import type { PropGame } from "./types";

// Tiny local copies of the props helpers: the logic tests run this file under plain node, which cannot resolve extensionless imports.
const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);

export interface SplitRow { key: string; label: string; n: number; avg: number | null; hit: number | null }
export interface SplitGroup { key: string; label: string; rows: SplitRow[] }

const MIN_SAMPLE = 5; // under this a split is shown but flagged as a small sample

export const SMALL_SAMPLE = MIN_SAMPLE;

export function computeSplits(games: PropGame[], market: Market, line: number, opp: { id: number | null; abbr: string | null }): SplitGroup[] {
  const vals = games.flatMap((game) => { const value = market.get(game); return value == null ? [] : [{ game, value }]; });
  const row = (key: string, label: string, pick: (g: PropGame) => boolean): SplitRow => {
    const v = vals.filter((x) => pick(x.game)).map((x) => x.value);
    return { key, label, n: v.length, avg: mean(v), hit: v.length ? v.filter((x) => (market.binary ? x >= 1 : x > line)).length / v.length : null };
  };
  const known = (g: PropGame) => g.rest_days != null;
  const groups: SplitGroup[] = [
    { key: "venue", label: "Home / away", rows: [row("home", "Home", (g) => g.home), row("away", "Away", (g) => !g.home)] },
    { key: "result", label: "Result", rows: [row("W", "Wins", (g) => g.result === "W"), row("L", "Losses", (g) => g.result === "L")] },
    { key: "rest", label: "Rest", rows: [
      row("b2b", "Back-to-back", (g) => known(g) && g.rest_days === 0),
      row("r1", "1 day off", (g) => g.rest_days === 1),
      row("r2", "2+ days off", (g) => g.rest_days != null && g.rest_days >= 2),
    ] },
    { key: "def", label: "Opponent defence", rows: [
      row("top", "Top 10 defences", (g) => g.opp_def_rank != null && g.opp_def_rank <= 10),
      row("mid", "Middle 11-20", (g) => g.opp_def_rank != null && g.opp_def_rank > 10 && g.opp_def_rank < 21),
      row("bot", "Bottom 10 defences", (g) => g.opp_def_rank != null && g.opp_def_rank >= 21),
    ] },
    { key: "type", label: "Season type", rows: [row("regular", "Regular season", (g) => g.season_type === "regular"), row("playoffs", "Playoffs", (g) => g.season_type === "playoffs")] },
  ];
  if (opp.id != null) groups.push({ key: "opp", label: "This opponent", rows: [row("vs", `vs ${opp.abbr ?? "opponent"}`, (g) => g.opp_id === opp.id)] });
  // A group where only one row has games says nothing (e.g. no playoff games yet): keep only groups that compare at least two rows.
  return groups.filter((g) => g.key === "opp" ? g.rows[0].n > 0 : g.rows.filter((r) => r.n > 0).length >= 2);
}
