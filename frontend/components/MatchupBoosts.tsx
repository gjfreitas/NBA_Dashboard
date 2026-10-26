"use client";
import { teamVars } from "@/lib/teamColors";
import { InfoTip } from "./InfoTip";
import Link from "next/link";
import { usePolling } from "@/lib/hooks";
import { boostText, seasonMixText, type Boost, type Boosts } from "@/lib/boosts";

const when = (iso: string | null) => (iso ? new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : "");

function Card({ b, kind }: { b: Boost; kind: "best" | "toughest" }) {
  const good = kind === "best";
  return (
    <li className={`spot reveal rounded-lg border border-line border-l-4 bg-surface p-3 transition-transform duration-300 hover:-translate-y-0.5 ${good ? "border-l-win" : "border-l-live"}`} style={teamVars(b.team_abbr)}>
      <p className="text-xs font-semibold tracking-wide text-muted">{good ? "BEST" : "TOUGHEST"}</p>
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="truncate text-lg font-bold">{b.name}</h3>
        <span className={`num shrink-0 text-lg font-bold ${good ? "text-win" : "text-live"}`}>{boostText(b.boost_pct)}</span>
      </div>
      <p className="text-xs text-muted">{b.home ? "vs" : "at"} {b.opp_abbr} · {when(b.start_utc)}</p>
      <p className="mt-1 text-sm">{b.headline}</p>
      <p className="text-xs text-muted">{b.opp_abbr} defence: {seasonMixText(b.season_weight, b.opp_games)}</p>
      <Link href={`/players/${b.player_id}/stats`} className="mt-1 inline-flex min-h-11 items-center text-sm font-semibold text-accent hover:underline">Try it →</Link>
    </li>
  );
}

/** Which scorers face a soft or a tough defence today, for their style of play, shot types and position. */
export function MatchupBoosts() {
  const { data } = usePolling<Boosts>("/api/today/boosts", 30 * 60_000);
  if (!data || data.all.length === 0) return null;
  return (
    <section aria-label="Matchup boosts" className="space-y-3">
      <div>
        <h2 className="text-sm font-semibold">Matchup boosts
          <InfoTip label="How matchup boosts work">
            How much today’s defence should help or hurt each scorer: his play types, shot types and position against what that defence allows, versus the league average ({data.season}).
            A team’s defence numbers move from last season’s to this season’s between its 10th and 30th game (noisy ones never fully). A pointer to soft and tough spots, not a projection.
          </InfoTip>
        </h2>
        <p className="text-xs text-muted">Where today’s defences are soft or tough for each scorer.</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <ul aria-label="Best matchups" className="space-y-3">{data.best.slice(0, 3).map((b) => <Card key={`b${b.player_id}`} b={b} kind="best" />)}</ul>
        <ul aria-label="Toughest matchups" className="space-y-3">{data.toughest.slice(0, 3).map((b) => <Card key={`t${b.player_id}`} b={b} kind="toughest" />)}</ul>
      </div>
      <details className="rounded-lg border border-line bg-surface">
        <summary className="flex min-h-11 cursor-pointer items-center px-3 text-sm font-medium">All {data.all.length} matchups</summary>
        <div className="overflow-x-auto px-3 pb-3">
          <table className="num w-full text-sm">
            <caption className="pb-1 text-left text-xs text-muted">Boost is the average of the style, shot and position effects (position counts half). Rotation scorers only: 8+ points a game, 15+ games.</caption>
            <thead className="text-xs text-muted">
              <tr>
                <th scope="col" className="py-1 text-left font-normal">Player</th><th scope="col" className="py-1 text-right font-normal">Boost</th>
                <th scope="col" className="py-1 text-right font-normal">Style</th><th scope="col" className="py-1 text-right font-normal">Shots</th><th scope="col" className="py-1 text-right font-normal">Position</th>
              </tr>
            </thead>
            <tbody>
              {data.all.map((b) => (
                <tr key={b.player_id} className="border-t border-line">
                  <th scope="row" className="py-1.5 text-left font-normal"><Link href={`/players/${b.player_id}/stats`} className="hover:underline">{b.name}</Link> <span className="text-xs text-muted">{b.home ? "vs" : "at"} {b.opp_abbr}</span></th>
                  <td className={`py-1.5 text-right font-semibold ${b.boost_pct > 0 ? "text-win" : b.boost_pct < 0 ? "text-live" : ""}`}>{boostText(b.boost_pct)}</td>
                  <td className="py-1.5 text-right text-muted">{b.style_pct == null ? "–" : boostText(b.style_pct)}</td>
                  <td className="py-1.5 text-right text-muted">{b.shot_pct == null ? "–" : boostText(b.shot_pct)}</td>
                  <td className="py-1.5 text-right text-muted">{b.position_pct == null ? "–" : boostText(b.position_pct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}
