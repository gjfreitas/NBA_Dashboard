"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import { usePolling } from "@/lib/hooks";
import { priceText } from "@/lib/lines";
import { gameState, isBinaryMarket, MARKET_LABEL, playersFor, slateMarkets, unplaced, type Slate, type SlateGame, type SlatePlayer } from "@/lib/slate";
import { GamblingNotice } from "../GamblingNotice";
import { Headshot } from "../Headshot";
import { TeamLogo } from "../Logo";
import { PlayerStats } from "./PlayerStatsView";

const chip = (on: boolean) => `min-h-11 shrink-0 whitespace-nowrap rounded-full border px-3 text-sm ${on ? "border-accent bg-surface2 font-semibold" : "border-line text-muted hover:text-fg"}`;

interface Row { player: SlatePlayer; game: SlateGame }

const timeOf = (g: SlateGame) => (g.start_utc ? new Date(g.start_utc).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : "TBD");

function PlayerRow({ r, market, on, onPick }: { r: Row; market: string; on: boolean; onPick: () => void }) {
  const m = r.player.markets[market];
  const binary = isBinaryMarket(market);
  return (
    <li>
      <button type="button" onClick={onPick} aria-pressed={on}
        className={`flex min-h-14 w-full items-center gap-2 border-l-2 px-3 py-2 text-left ${on ? "border-accent bg-surface2" : "border-transparent hover:bg-surface2"}`}>
        {r.player.player_id != null ? <Headshot id={r.player.player_id} name={r.player.name} width={44} /> : <span className="size-8" aria-hidden />}
        <span className="min-w-0 flex-1">
          <span className="display block truncate text-base font-bold">{r.player.name}</span>
          <span className="block truncate text-xs text-muted">{r.player.team_abbr ?? ""}{r.player.position ? ` · ${r.player.position}` : ""}</span>
        </span>
        <span className="num shrink-0 text-right">
          <span className="block text-lg font-bold leading-none">{binary ? "Yes" : m.line}</span>
          <span className="block text-xs text-muted">
            {binary ? "Y" : "O"} <span className="text-win">{m.best_over ? priceText(m.best_over.price) : "–"}</span>
            {" "}{binary ? "N" : "U"} <span className="text-live">{m.best_under ? priceText(m.best_under.price) : "–"}</span>
          </span>
        </span>
      </button>
    </li>
  );
}

/** Pick a market and a game, choose a player with a line, and see how he has done against it: hit rate, last games, splits, matchup. */
export function StatsExplorer() {
  const { data, loading, error } = usePolling<Slate>("/api/slate", 5 * 60_000);
  const markets = useMemo(() => slateMarkets(data), [data]);
  const [pickMarket, setPickMarket] = useState<string | null>(null);
  const [gameId, setGameId] = useState("all");
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState<{ id: number; market: string } | null>(null);
  const market = pickMarket && markets.includes(pickMarket) ? pickMarket : markets.includes("pts") ? "pts" : markets[0];

  const groups = useMemo(() => {
    if (!data || !market) return [];
    return data.games
      .filter((g) => gameId === "all" || g.game_id === gameId)
      .map((game) => {
        const rows: Row[] = [
          ...playersFor(game, "away", market, query), ...playersFor(game, "home", market, query), ...unplaced(game, market, query),
        ].filter((p) => p.player_id != null).map((player) => ({ player, game }));
        return { game, rows };
      })
      .filter((g) => g.rows.length > 0);
  }, [data, market, gameId, query]);

  if (loading && !data) return <div className="h-96 skeleton rounded-lg bg-surface" aria-busy />;
  if (!data) return <p role="alert" className="text-muted">Can’t reach the data service{error ? ` (${error})` : ""}.</p>;
  if (!markets.length)
    return (
      <p className="rounded-lg border border-dashed border-line p-6 text-sm text-muted">
        No prop lines are posted yet. Sportsbooks usually post them a few hours before tip-off. You can still open any player’s{" "}
        <Link href="/players" className="underline">Stats tab</Link> and set the line yourself.
      </p>
    );

  const first = groups[0]?.rows[0];
  const selectedId = picked && groups.some((g) => g.rows.some((r) => r.player.player_id === picked.id)) ? picked.id : first?.player.player_id ?? null;
  const selected = groups.flatMap((g) => g.rows).find((r) => r.player.player_id === selectedId) ?? null;
  const line = selected ? selected.player.markets[market]?.line : undefined;
  const choose = (r: Row) => {
    setPicked({ id: r.player.player_id as number, market });
    if (typeof window !== "undefined" && window.innerWidth < 1024) document.getElementById("stats-detail")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className="space-y-3">
      <GamblingNotice />
      <div role="tablist" aria-label="Stat market" className="flex gap-2 overflow-x-auto pb-1 [scrollbar-width:none]">
        {markets.map((m) => (
          <button key={m} role="tab" aria-selected={m === market} className={chip(m === market)} onClick={() => setPickMarket(m)}>{MARKET_LABEL[m] ?? m}</button>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-[22rem_minmax(0,1fr)]">
        <aside aria-label="Players with lines" className="space-y-2 lg:sticky lg:top-3 lg:self-start">
          <div className="flex gap-2">
            <label className="min-w-0 flex-1">
              <span className="sr-only">Game</span>
              <select value={gameId} onChange={(e) => setGameId(e.target.value)} className="min-h-11 w-full rounded-lg border border-line bg-surface px-2 text-base">
                <option value="all">All games</option>
                {data.games.filter((g) => g.players.length > 0).map((g) => (
                  <option key={g.game_id} value={g.game_id}>{g.away.abbr} @ {g.home.abbr} · {gameState(g) ?? timeOf(g)}</option>
                ))}
              </select>
            </label>
          </div>
          <label className="block">
            <span className="sr-only">Search players</span>
            <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search players…"
              className="min-h-11 w-full rounded-lg border border-line bg-surface px-3 text-base placeholder:text-muted" />
          </label>
          <div className="max-h-[70vh] overflow-y-auto rounded-lg border border-line bg-surface lg:max-h-[calc(100vh-14rem)]">
            {groups.length === 0 ? (
              <p role="status" className="p-4 text-sm text-muted">
                {query.trim() ? `No player with a ${MARKET_LABEL[market] ?? market} line matches “${query.trim()}”.` : `No ${MARKET_LABEL[market] ?? market} lines for this game yet.`}
              </p>
            ) : groups.map(({ game, rows }) => (
              <section key={game.game_id} aria-label={`${game.away.name} at ${game.home.name}`}>
                <h2 className="sticky top-0 z-10 flex items-center justify-between gap-2 border-y border-line bg-surface px-3 py-1.5 text-xs font-semibold text-muted first:border-t-0">
                  <span className="flex items-center gap-1.5"><TeamLogo id={game.away.id} tricode={game.away.abbr ?? ""} size={18} />{game.away.abbr} @ <TeamLogo id={game.home.id} tricode={game.home.abbr ?? ""} size={18} />{game.home.abbr}</span>
                  <span className="num font-normal">{gameState(game) === "live" ? "LIVE" : gameState(game) === "final" ? "Final" : timeOf(game)}</span>
                </h2>
                <ul>{rows.map((r) => <PlayerRow key={`${game.game_id}-${r.player.player_id}`} r={r} market={market} on={r.player.player_id === selectedId} onPick={() => choose(r)} />)}</ul>
              </section>
            ))}
          </div>
        </aside>

        <section id="stats-detail" aria-label="Player stats" className="min-w-0 scroll-mt-3">
          {selected && selected.player.player_id != null ? (
            <>
              <div className="mb-3 flex items-center gap-3">
                <Headshot id={selected.player.player_id} name={selected.player.name} width={72} />
                <div className="min-w-0">
                  <h2 className="truncate text-2xl font-extrabold">{selected.player.name}</h2>
                  <p className="text-sm text-muted">
                    {selected.player.team_abbr ?? ""}{selected.player.position ? ` · ${selected.player.position}` : ""} · {selected.game.away.abbr} @ {selected.game.home.abbr}
                    {" · "}<Link href={`/players/${selected.player.player_id}`} className="underline hover:text-fg">Full player page</Link>
                  </p>
                </div>
              </div>
              <PlayerStats key={selected.player.player_id} hideMarketBar id={selected.player.player_id} market={market} line={isBinaryMarket(market) ? undefined : line} />
            </>
          ) : (
            <p className="rounded-lg border border-dashed border-line p-6 text-sm text-muted">Pick a player on the left to see how he has done against his line.</p>
          )}
        </section>
      </div>
    </div>
  );
}
