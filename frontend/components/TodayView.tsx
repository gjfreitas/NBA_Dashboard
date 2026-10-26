"use client";
import { gameVars } from "@/lib/teamColors";
import Link from "next/link";
import { usePolling } from "@/lib/hooks";
import { MARKET_LABEL } from "@/lib/slate";
import { backToBackTeams, gameFor, restLabel, type Today, type TodayGame, type TodayTeam } from "@/lib/today";
import { useWatchlist } from "@/lib/useWatchlist";
import { GamblingNotice } from "./GamblingNotice";
import { MatchupBoosts } from "./MatchupBoosts";
import { TeamLogo } from "./Logo";

function Side({ t }: { t: TodayTeam }) {
  const rest = restLabel(t);
  return (
    <div className="min-w-0 flex-1">
      <div className="flex items-center gap-2">
        <TeamLogo id={t.id} tricode={t.abbr ?? ""} size={32} />
        <div className="min-w-0">
          <p className="truncate font-semibold">{t.name} <span className="num text-xs font-normal text-muted">{t.record}{t.streak ? ` · ${t.streak}` : ""}</span></p>
          <p className="flex flex-wrap items-center gap-x-2 text-xs text-muted">
            {rest && <span className={t.back_to_back ? "font-semibold text-live" : ""}>{rest}</span>}
            {t.lineup_status && <span className={t.lineup_status === "Confirmed" ? "font-semibold text-win" : ""}>{t.lineup_status === "Confirmed" ? "✓ Lineup confirmed" : "Lineup expected"}</span>}
          </p>
        </div>
      </div>
      {(t.key_out.length > 0 || t.others_out > 0) && (
        <p className="mt-1 text-xs">
          {t.key_out.map((k) => <span key={k.name} className="mr-2"><b>{k.name}</b> <span className="text-live">{k.status.toLowerCase()}</span>{k.ppg ? <span className="text-muted"> ({k.ppg} ppg)</span> : null}</span>)}
          {t.others_out > 0 && <span className="text-muted">+{t.others_out} other{t.others_out === 1 ? "" : "s"} out</span>}
        </p>
      )}
    </div>
  );
}

function Game({ g }: { g: TodayGame }) {
  const when = g.start_utc ? new Date(g.start_utc).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : "TBD";
  return (
    <li className="game-card spot reveal rounded-lg border border-line bg-surface p-3 pt-4" style={gameVars(g.away.abbr, g.home.abbr)}>
      <div className="mb-2 flex items-center justify-between text-xs text-muted">
        <span className="num">{g.status === 2 ? <b className="text-live">LIVE</b> : g.status === 3 ? "Final" : when}</span>
        <span className="flex gap-3">
          <Link href={`/games/${g.game_id}/preview`} className="inline-flex min-h-11 items-center underline hover:text-fg">Preview</Link>
          {g.players_with_lines > 0 && <Link href="/props" className="inline-flex min-h-11 items-center underline hover:text-fg">{g.players_with_lines} players with lines</Link>}
        </span>
      </div>
      <div className="flex flex-col gap-3 sm:flex-row sm:gap-6"><Side t={g.away} /><Side t={g.home} /></div>
    </li>
  );
}

/** One screen for the day: who plays and who is short-handed, who is tired, what the books moved, and where your followed players are. */
export function TodayView() {
  const { data, loading, error } = usePolling<Today>("/api/today", 120_000);
  const { list } = useWatchlist();
  if (loading && !data) return <div className="h-96 skeleton rounded-lg bg-surface" aria-busy />;
  if (!data) return <p role="alert" className="text-muted">Can’t reach the data service{error ? ` (${error})` : ""}.</p>;
  const b2b = backToBackTeams(data.games);
  const mine = list.items.map((i) => ({ i, at: i.kind === "player" ? gameFor(data.games, i.sub) : gameFor(data.games, i.sub) })).filter((x) => x.at);
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted" role="status">
        {data.games.length === 0 ? "No games today." : `${data.games.length} game${data.games.length === 1 ? "" : "s"} on ${new Date(`${data.date}T12:00:00`).toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" })}.`}
        {b2b.length > 0 && <> Second night of a back-to-back: <b className="text-fg">{b2b.join(", ")}</b>.</>}
      </p>

      {mine.length > 0 && (
        <section aria-label="Your players and teams today" className="rounded-lg border border-line bg-surface p-3">
          <h2 className="mb-1 text-sm font-semibold">You follow, playing today</h2>
          <ul className="divide-y divide-line text-sm">
            {mine.map(({ i, at }) => (
              <li key={`${i.kind}${i.id}`} className="flex items-center justify-between gap-2 py-1.5">
                <Link href={i.kind === "player" ? `/players/${i.id}/stats` : `/teams/${i.id}`} className="truncate font-medium hover:underline">{i.name}</Link>
                <Link href={`/games/${at!.game.game_id}/preview`} className="shrink-0 text-xs text-muted underline">{at!.label}</Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <MatchupBoosts />

      <ul className="space-y-3" aria-label="Games">{data.games.map((g) => <Game key={g.game_id} g={g} />)}</ul>

      {data.moves.length > 0 && (
        <section aria-label="Biggest line moves" className="rounded-lg border border-line bg-surface p-3">
          <h2 className="text-sm font-semibold">Biggest prop-line moves</h2>
          <p className="mb-1 text-xs text-muted">Change in the line most books show, since we first stored it (not necessarily since the book opened it).</p>
          <ul className="divide-y divide-line text-sm">
            {data.moves.map((m) => (
              <li key={`${m.game_id}${m.player_id}${m.market}`} className="flex items-center justify-between gap-2 py-1.5">
                <span className="min-w-0 truncate">
                  {m.player_id ? <Link href={`/players/${m.player_id}/stats`} className="font-medium hover:underline">{m.name}</Link> : <b>{m.name}</b>}
                  <span className="text-muted"> {m.team_abbr} · {MARKET_LABEL[m.market] ?? m.market}</span>
                  {m.injury && <span className="ml-1 text-xs text-live">({m.injury.toLowerCase()})</span>}
                </span>
                <span className="num shrink-0"><span className="text-muted">{m.opening} →</span> <b>{m.now}</b> <span className={m.move > 0 ? "text-win" : "text-live"}>({m.move > 0 ? "+" : ""}{m.move})</span></span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {data.games.some((g) => g.players_with_lines > 0) && <GamblingNotice compact />}
    </div>
  );
}
