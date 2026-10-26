"use client";
import { useFetch } from "@/lib/hooks";

interface PositionRow { position: string; pts: number; reb: number; ast: number; league_pts: number; pts_rank: number; games: number }
interface ZoneRow { zone: string; shot_share: number; league_share: number; fg_pct_allowed: number | null; league_fg_pct: number | null; def_rank: number | null }
interface TeamDepth { team_id: number; abbr: string | null; defence_by_position: PositionRow[]; offence_vs_opponent_zones: ZoneRow[] }
interface Matchup {
  season: string; is_fallback: boolean;
  pace: { home: number | null; away: number | null; league: number | null; expected: number | null; home_rank: number | null; away_rank: number | null };
  home: TeamDepth; away: TeamDepth;
}

const POSITION_NAME: Record<string, string> = { G: "Guards", F: "Forwards", C: "Centers" };
const pct = (v: number | null) => (v == null ? "–" : `${(v * 100).toFixed(1)}%`);
const share = (v: number) => `${Math.round(v * 100)}%`;
const f1 = (v: number | null) => (v == null ? "–" : v.toFixed(1));
const ord = (n: number | null) => (n == null ? "" : `#${n}`);

/** Positions: rank 1 allows the fewest points. A defence in the bottom third is flagged as soft. */
const soft = (rank: number) => rank >= 21;

function Defence({ m }: { m: Matchup }) {
  return (
    <section aria-label="Defence by position" className="rounded-lg border border-line bg-surface p-3">
      <h3 className="text-sm font-semibold">Defence by position</h3>
      <p className="mb-2 text-xs text-muted">Points allowed per opposing player-game (15+ minutes) at each position, {m.season}{m.is_fallback ? " (last season: the new one is too young)" : ""}. #1 allows the fewest in the league.</p>
      <div className="grid gap-3 sm:grid-cols-2">
        {[m.away, m.home].map((t) => (
          <table key={t.team_id} className="num w-full text-sm">
            <caption className="pb-1 text-left text-xs font-semibold">{t.abbr} defence</caption>
            <thead className="sr-only"><tr><th scope="col">Position</th><th scope="col">Points allowed</th><th scope="col">League average</th><th scope="col">Rank</th></tr></thead>
            <tbody>
              {t.defence_by_position.map((r) => (
                <tr key={r.position} className="border-t border-line">
                  <th scope="row" className="py-1.5 text-left font-normal">{POSITION_NAME[r.position] ?? r.position}</th>
                  <td className="py-1.5 text-right font-semibold">{f1(r.pts)}</td>
                  <td className="py-1.5 text-right text-xs text-muted">avg {f1(r.league_pts)}</td>
                  <td className={`py-1.5 text-right text-xs ${soft(r.pts_rank) ? "font-semibold text-win" : "text-muted"}`}>{ord(r.pts_rank)}{soft(r.pts_rank) && <span className="sr-only"> (soft matchup)</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ))}
      </div>
      <p className="mt-1 text-xs text-muted">Green means a soft spot: that defence is among the ten that give up the most to that position.</p>
    </section>
  );
}

function Zones({ m }: { m: Matchup }) {
  return (
    <section aria-label="Shot zone matchup" className="rounded-lg border border-line bg-surface p-3">
      <h3 className="text-sm font-semibold">Shot-zone matchup</h3>
      <p className="mb-2 text-xs text-muted">How much of each team’s shooting comes from a zone (current roster, {m.season}), against how well the other defence guards it. #1 defends best.</p>
      <div className="grid gap-3 sm:grid-cols-2">
        {([[m.away, m.home], [m.home, m.away]] as const).map(([att, def]) => (
          <table key={att.team_id} className="num w-full text-sm">
            <caption className="pb-1 text-left text-xs font-semibold">{att.abbr} shots vs {def.abbr} defence</caption>
            <thead className="text-xs text-muted"><tr><th scope="col" className="py-1 text-left font-normal">Zone</th><th scope="col" className="py-1 text-right font-normal">Shots</th><th scope="col" className="py-1 text-right font-normal">Allowed</th></tr></thead>
            <tbody>
              {att.offence_vs_opponent_zones.map((z) => {
                const weak = z.def_rank != null && z.def_rank >= 21 && z.shot_share >= z.league_share;
                return (
                  <tr key={z.zone} className="border-t border-line">
                    <th scope="row" className="py-1.5 text-left font-normal">{z.zone.replace("In The Paint (Non-RA)", "Paint (non-RA)")}</th>
                    <td className="py-1.5 text-right">{share(z.shot_share)} <span className="text-xs text-muted">({share(z.league_share)})</span></td>
                    <td className={`py-1.5 text-right ${weak ? "font-semibold text-win" : ""}`}>{pct(z.fg_pct_allowed)} <span className="text-xs text-muted">{ord(z.def_rank)}</span>{weak && <span className="sr-only"> (a zone this team likes against a weak defence)</span>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ))}
      </div>
      <p className="mt-1 text-xs text-muted">Shots: the share of that team’s attempts (league share in brackets). Allowed: the defence’s opponent FG% there. Green: the attacker shoots there more than average and the defence is in the bottom ten.</p>
    </section>
  );
}

/** Tempo, defence by position, and shot-zone matchups for the two teams of a game. */
export function MatchupDepth({ homeId, awayId }: { homeId: number; awayId: number }) {
  const { data } = useFetch<Matchup>(`/api/preview/matchup?home=${homeId}&away=${awayId}`);
  if (!data) return null;
  const p = data.pace;
  const tempo = p.expected == null || p.league == null ? null : p.expected - p.league >= 1 ? "faster than" : p.league - p.expected >= 1 ? "slower than" : "in line with";
  return (
    <div className="space-y-3">
      {p.expected != null && (
        <section aria-label="Tempo" className="rounded-lg border border-line bg-surface p-3 text-sm">
          <h3 className="text-sm font-semibold">Tempo</h3>
          <p className="num mt-1">
            Expected pace <b>{f1(p.expected)}</b> possessions per 48 minutes, {tempo} the league’s {f1(p.league)}.
          </p>
          <p className="text-xs text-muted">Away team {f1(p.away)} ({ord(p.away_rank)} fastest) · home team {f1(p.home)} ({ord(p.home_rank)}). A faster game means more shots and more chances for every counting stat.</p>
        </section>
      )}
      <Defence m={data} />
      <Zones m={data} />
    </div>
  );
}
