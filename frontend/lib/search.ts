import type { TeamInfo } from "./types";

const fold = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();

/** Teams matching what was typed: abbreviation ("den"), city ("denver"), nickname ("nuggets") or the full name. Best matches first. */
export function matchTeams(teams: TeamInfo[], query: string, limit = 5): TeamInfo[] {
  const q = fold(query);
  if (!q) return [];
  const scored: [number, TeamInfo][] = [];
  for (const t of teams) {
    const full = fold(`${t.city} ${t.name}`);
    const abbr = fold(t.abbr ?? "");
    const rank = abbr === q ? 0 : full.startsWith(q) || fold(t.name).startsWith(q) ? 1 : abbr.startsWith(q) ? 2 : full.includes(q) ? 3 : -1;
    if (rank >= 0) scored.push([rank, t]);
  }
  return scored.sort((a, b) => a[0] - b[0] || a[1].city.localeCompare(b[1].city)).slice(0, limit).map(([, t]) => t);
}

/** Moves a highlighted row up or down a list of `count` rows, wrapping at the ends. */
export function moveIndex(current: number, delta: 1 | -1, count: number): number {
  if (count <= 0) return -1;
  if (current < 0) return delta === 1 ? 0 : count - 1;
  return (current + delta + count) % count;
}
