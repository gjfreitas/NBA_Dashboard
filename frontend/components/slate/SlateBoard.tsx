"use client";
import { gameVars } from "@/lib/teamColors";
import { InfoTip } from "../InfoTip";
import { useMemo, useState } from "react";
import { bookName, moveText, priceText } from "@/lib/lines";
import { usePolling } from "@/lib/hooks";
import { gameState, isBinaryMarket, MARKET_LABEL, playersFor, slateMarkets, unplaced, type Slate, type SlateGame, type SlateMarket, type SlatePlayer } from "@/lib/slate";
import { StatusPill } from "../availability/StatusPill";
import { GamblingNotice } from "../GamblingNotice";
import { Headshot } from "../Headshot";
import { TeamLogo } from "../Logo";
import { PlayerAnalysis } from "./PlayerAnalysis";

const chip = (on: boolean) => `min-h-11 rounded-full border px-3 text-sm ${on ? "border-accent bg-surface2 font-semibold" : "border-line text-muted hover:text-fg"}`;

function BestPrices({ m, binary, className = "" }: { m: SlateMarket; binary: boolean; className?: string }) {
  return (
    <span className={`num shrink-0 items-center gap-1 rounded-lg bg-surface2 px-2 py-1 text-sm ${className}`}>
      <span className="text-xs text-muted">{binary ? "Y" : "O"}</span><span className="font-semibold text-win">{m.best_over ? priceText(m.best_over.price) : "–"}</span>
      <span className="ml-1 text-xs text-muted">{binary ? "N" : "U"}</span><span className="font-semibold text-live">{m.best_under ? priceText(m.best_under.price) : "–"}</span>
    </span>
  );
}

function PlayerRow({ p, market, game, side }: { p: SlatePlayer; market: string; game: SlateGame; side: "away" | "home" }) {
  const [open, setOpen] = useState(false);
  const m = p.markets[market];
  const binary = isBinaryMarket(market);
  const opp = game[side === "home" ? "away" : "home"];
  const panel = `${game.game_id}-${p.player_id ?? p.name}-${market}`.replace(/\s+/g, "");
  return (
    <li className="border-b border-line last:border-0">
      <button type="button" aria-expanded={open} aria-controls={panel} onClick={() => setOpen((o) => !o)}
        className="flex min-h-14 w-full items-center gap-3 px-3 py-2 text-left hover:bg-surface2">
        {p.player_id != null ? <Headshot id={p.player_id} name={p.name} width={52} /> : <span className="size-9" aria-hidden />}
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2">
            <span className="display truncate text-lg font-bold">{p.name}</span>
            {p.position && <span className="shrink-0 rounded bg-surface2 px-1.5 text-xs text-muted">{p.position}</span>}
          </span>
          <BestPrices m={m} binary={binary} className="mt-1 inline-flex sm:hidden" />
          {p.injury && <span className="mt-0.5 flex items-center gap-1.5 text-xs"><StatusPill status={p.injury.status} /><span className="truncate text-muted">{p.injury.reason.replace(/^Injury\/Illness - /, "")}</span></span>}
        </span>
        <span className="text-right">
          <span className="score block text-3xl">{binary ? "YES" : m.line}</span>
          <span className="block text-xs text-muted">{m.books.length} {m.books.length === 1 ? "book" : "books"}</span>
        </span>
        <BestPrices m={m} binary={binary} className="hidden sm:flex" />
        <span aria-hidden className="text-muted">{open ? "▴" : "▾"}</span>
      </button>
      {open && (
        <div id={panel} className="space-y-3 bg-surface2/40 px-3 py-3">
          <table className="num w-full text-sm">
            <caption className="pb-1 text-left text-xs text-muted">{MARKET_LABEL[market] ?? market}: every book. {binary ? "Best Yes and No prices are in bold." : `Best prices at the ${m.line} line are in bold.`}</caption>
            <thead className="text-xs text-muted">
              <tr><th scope="col" className="py-1 text-left font-normal">Book</th>{!binary && <th scope="col" className="py-1 text-right font-normal">Line</th>}<th scope="col" className="py-1 text-right font-normal">{binary ? "Yes" : "Over"}</th><th scope="col" className="py-1 text-right font-normal">{binary ? "No" : "Under"}</th></tr>
            </thead>
            <tbody>
              {m.books.map((b) => {
                const bestO = b.line === m.line && m.best_over?.book === b.book, bestU = b.line === m.line && m.best_under?.book === b.book;
                return (
                  <tr key={b.book} className="border-t border-line">
                    <th scope="row" className="py-1.5 text-left font-normal">{bookName(b.book)}</th>
                    {!binary && <td className="py-1.5 text-right">{b.line}{moveText(b.line, b.opening_line) && <span className="ml-1 text-xs text-muted">({moveText(b.line, b.opening_line)})</span>}</td>}
                    <td className={`py-1.5 text-right ${bestO ? "font-bold text-win" : ""}`}>{priceText(b.over_price) || "–"}{bestO && <span className="sr-only"> (best)</span>}</td>
                    <td className={`py-1.5 text-right ${bestU ? "font-bold text-live" : ""}`}>{priceText(b.under_price) || "–"}{bestU && <span className="sr-only"> (best)</span>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {p.player_id != null && <PlayerAnalysis playerId={p.player_id} market={market} line={m.line} home={side === "home"} oppId={opp.id} oppAbbr={opp.abbr} />}
        </div>
      )}
    </li>
  );
}

function TeamBlock({ game, side, market, query }: { game: SlateGame; side: "away" | "home"; market: string; query: string }) {
  const t = game[side];
  const players = playersFor(game, side, market, query);
  if (!players.length) return null;
  return (
    <section aria-label={`${t.name} players`}>
      <h2 className="flex items-center gap-2 border-y border-line bg-surface px-3 py-1.5 text-xs font-semibold text-muted"><TeamLogo id={t.id} tricode={t.abbr ?? ""} size={20} />{t.name}</h2>
      <ul>{players.map((p) => <PlayerRow key={`${p.player_id}-${p.name}`} p={p} market={market} game={game} side={side} />)}</ul>
    </section>
  );
}

const matchCount = (g: SlateGame, market: string, query: string) =>
  playersFor(g, "away", market, query).length + playersFor(g, "home", market, query).length + unplaced(g, market, query).length;

function GameCard({ game, market, query, defaultOpen }: { game: SlateGame; market: string; query: string; defaultOpen: boolean }) {
  const [openState, setOpen] = useState(defaultOpen);
  const searching = query.trim() !== "";
  if (searching && matchCount(game, market, query) === 0) return null;
  const open = searching || openState; // a search opens every game that has a match
  const state = gameState(game);
  const n = game.players.filter((p) => market in p.markets).length;
  const when = game.start_utc ? new Date(game.start_utc).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : "TBD";
  const day = game.start_utc ? new Date(game.start_utc).toLocaleDateString([], { weekday: "short" }) : "";
  const loose = unplaced(game, market, query);
  return (
    <li className="game-card spot overflow-hidden rounded-lg border border-line bg-surface" style={gameVars(game.away.abbr, game.home.abbr)}>
      <button type="button" aria-expanded={open} onClick={() => setOpen((o) => !o)}
        className="grid min-h-16 w-full grid-cols-[1fr_auto_1fr] items-center gap-2 px-3 py-2 hover:bg-surface2"
        aria-label={`${game.away.name} at ${game.home.name}, ${state ?? `${day} ${when}`}, ${n} players with lines`}>
        <span className="display flex flex-col items-center gap-1 text-xl font-bold"><TeamLogo id={game.away.id} tricode={game.away.abbr ?? ""} size={44} />{game.away.name.split(" ").slice(-1)[0]}</span>
        <span className="num text-center text-xs text-muted">
          {state === "live" ? <b className="text-live">LIVE</b> : state === "final" ? "Final" : <>{day}<br />{when}</>}
          <br /><span aria-hidden>{open ? "▴" : "▾"}</span>
        </span>
        <span className="display flex flex-col items-center gap-1 text-xl font-bold"><TeamLogo id={game.home.id} tricode={game.home.abbr ?? ""} size={44} />{game.home.name.split(" ").slice(-1)[0]}</span>
      </button>
      {open && (
        <div>
          {n === 0 ? <p className="border-t border-line px-3 py-3 text-sm text-muted">No lines posted for this market yet.</p> : (
            <>
              <TeamBlock game={game} side="away" market={market} query={query} />
              <TeamBlock game={game} side="home" market={market} query={query} />
              {loose.length > 0 && (
                <section aria-label="Other players"><h2 className="border-y border-line bg-surface px-3 py-1.5 text-xs font-semibold text-muted">Team not confirmed</h2>
                  <ul>{loose.map((p) => <PlayerRow key={p.name} p={p} market={market} game={game} side="home" />)}</ul></section>
              )}
            </>
          )}
        </div>
      )}
    </li>
  );
}

/** Tonight's games, each expanding into its players' lines; a row expands again into every book and a quick analysis. */
export function SlateBoard() {
  const { data, loading, error } = usePolling<Slate>("/api/slate", 5 * 60_000);
  const markets = useMemo(() => slateMarkets(data), [data]);
  const [pick, setPick] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const market = pick && markets.includes(pick) ? pick : markets.includes("pts") ? "pts" : markets[0];

  if (loading && !data) return <div className="h-96 skeleton rounded-lg bg-surface" aria-busy />;
  if (!data) return <p role="alert" className="text-muted">Can’t reach the data service{error ? ` (${error})` : ""}.</p>;
  const withLines = data.games.filter((g) => g.players.length > 0);
  return (
    <div className="space-y-3">
      <GamblingNotice />
      {!markets.length ? (
        <p className="rounded-lg border border-dashed border-line p-6 text-sm text-muted">
          {data.games.length === 0 ? "No games scheduled today." : "No prop lines posted for today’s games yet."} Sportsbooks usually post them a few hours before tip-off, so check back later.
        </p>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <div role="group" aria-label="Market" className="flex flex-wrap gap-2">
              {markets.map((m) => <button key={m} className={chip(m === market)} aria-pressed={m === market} onClick={() => setPick(m)}>{MARKET_LABEL[m] ?? m}</button>)}
            </div>
            <label className="w-full sm:ml-auto sm:w-auto">
              <span className="sr-only">Search players</span>
              <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search players…"
                className="min-h-11 w-full rounded-lg border border-line bg-surface px-3 text-base placeholder:text-muted" />
            </label>
          </div>
          <p className="flex items-center gap-2 text-xs text-muted" role="status">
            Best price at the consensus line. Press a player for every book.
            <InfoTip label="About these lines">
              Each row shows the line most books agree on and the best over and under price among them. Opening a player lists every book and a quick analysis.
              {data.as_of ? ` Lines stored ${new Date(data.as_of).toLocaleString()}.` : ""}
            </InfoTip>
          </p>
          {query.trim() !== "" && !withLines.some((g) => matchCount(g, market, query) > 0) && (
            <p role="status" className="rounded-lg border border-dashed border-line p-6 text-sm text-muted">No player with a {MARKET_LABEL[market] ?? market} line matches “{query.trim()}”. Try another market or a shorter name.</p>
          )}
          <ul className="space-y-3">
            {withLines.map((g, i) => <GameCard key={g.game_id} game={g} market={market} query={query} defaultOpen={i === 0} />)}
          </ul>
        </>
      )}
    </div>
  );
}
