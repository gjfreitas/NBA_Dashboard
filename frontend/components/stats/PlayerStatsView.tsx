"use client";
import { SetupHint } from "../SetupHint";
import { InfoTip } from "../InfoTip";
import { useMemo, useState } from "react";
import { useFetch } from "@/lib/hooks";
import {
  DEFAULT_FILTERS, averages, defaultLine, hitRate, marketByKey, normalizePrefs, selectGames, values, visibleMarkets,
  type Averages, type Filters, type MarketPrefs,
} from "@/lib/props";
import { bookName, consensus, moveText, priceText, sourceName, type PlayerLines } from "@/lib/lines";
import { computeSplits } from "@/lib/splits";
import type { PropsData, TeamInfo } from "@/lib/types";
import { usePlayer } from "../PlayerProvider";
import { activeFilterLabels, FiltersPanel } from "./FiltersPanel";
import { loadPrefs, MarketBar, MarketsDialog, savePrefs } from "./MarketBar";
import { MatchupPanels } from "./MatchupPanels";
import { PropsChart } from "./PropsChart";
import { SplitsPanel } from "./SplitsPanel";

const SIGN = (v: number, nd = 1) => (v > 0 ? `+${v.toFixed(nd)}` : v.toFixed(nd));

function Stat({ label, value, delta, suffix = "", active }: { label: string; value: number | null; delta: number | null; suffix?: string; active?: boolean }) {
  return (
    <div className="min-w-14 text-center">
      <dt className={`text-xs font-medium ${active ? "text-fg underline decoration-accent decoration-2 underline-offset-4" : "text-muted"}`}>{label}</dt>
      <dd className="num text-lg font-bold leading-tight">{value == null ? "–" : `${value.toFixed(1)}${suffix}`}</dd>
      <dd className={`num text-xs ${delta == null || Math.abs(delta) < 0.05 ? "text-muted" : delta > 0 ? "text-win" : "text-live"}`}>
        {delta == null ? "" : Math.abs(delta) < 0.05 ? "0.0" : SIGN(delta)}
        <span className="sr-only"> versus the player’s usual average</span>
      </dd>
    </div>
  );
}

const STAT_FOR_MARKET: Record<string, keyof Averages> = { pts: "pts", ast: "ast", reb: "reb", fg3m: "fg3m" };

/** The Stats tab of a player page. */
export function PlayerStatsView() {
  const { id } = usePlayer();
  return <PlayerStats id={id} />;
}

/**
 * The stats explorer for one player. `market` and `line` are an optional starting point (the Stats page passes the book's market and consensus line);
 * when they change the view follows them, and the visitor can still pick another market or set their own line.
 */
export function PlayerStats({ id, market: startMarket, line: startLine, hideMarketBar }: { id: string | number; market?: string; line?: number; hideMarketBar?: boolean }) {
  const props = useFetch<PropsData>(`/api/players/${id}/games`);
  const teams = useFetch<TeamInfo[]>("/api/teams");
  const bookLines = useFetch<PlayerLines>(`/api/players/${id}/lines`).data; // empty unless an odds API key is configured
  const [prefs, setPrefsState] = useState<MarketPrefs>(loadPrefs);
  const [marketKey, setMarketKey] = useState(startMarket ?? "pts");
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [lines, setLines] = useState<Record<string, number>>(startMarket && startLine != null ? { [startMarket]: startLine } : {});
  const preset = `${startMarket ?? ""}|${startLine ?? ""}`;
  const [seenPreset, setSeenPreset] = useState(preset);
  if (seenPreset !== preset) { // the starting point changed (another market picked outside): follow it, during render
    setSeenPreset(preset);
    if (startMarket) setMarketKey(startMarket);
    if (startMarket && startLine != null) setLines((l) => ({ ...l, [startMarket]: startLine }));
  }
  const [opp, setOpp] = useState<number | "none" | null>(null); // null = the next game's opponent
  const [showFilters, setShowFilters] = useState(false);
  const [dialog, setDialog] = useState(false);

  const data = props.data;
  const nextOpp = data?.next_game?.opp_id ?? null;
  const oppId = opp === "none" ? null : opp ?? nextOpp;
  const oppAbbr = oppId == null ? null : teams.data?.find((t) => t.id === oppId)?.abbr ?? (oppId === nextOpp ? data?.next_game?.opp_abbr ?? null : null);

  const markets = useMemo(() => { // a market chosen elsewhere is shown even if the visitor hid it here
    const v = visibleMarkets(prefs);
    return v.some((m) => m.key === marketKey) ? v : [...v, marketByKey(marketKey)];
  }, [prefs, marketKey]);
  const market = markets.find((m) => m.key === marketKey) ?? markets[0] ?? marketByKey("pts");

  const sel = useMemo(
    () => (data ? selectGames(data.games, filters, { oppId, teammates: data.teammates }) : null),
    [data, filters, oppId],
  );
  const bars = useMemo(() => (sel ? values(sel.sample, market) : []), [sel, market]);

  // splits compare conditions within the chosen seasons, so they use the baseline (not the filtered pool) and the current line
  const splitLine = lines[market.key] ?? defaultLine(values(sel?.sample ?? [], market).map((b) => b.value));
  const splits = useMemo(() => (sel ? computeSplits(sel.baseline, market, splitLine, { id: oppId, abbr: oppAbbr }) : []), [sel, market, splitLine, oppId, oppAbbr]);

  if (props.loading) return <div className="h-96 skeleton rounded-lg bg-surface" aria-busy />;
  if (props.notFound || !data || !sel)
    return (
      <p className="rounded-lg border border-dashed border-line p-6 text-sm text-muted">
        {props.error ? `Can’t load game data (${props.error}).` : <>No game logs for this player yet. <SetupHint cmd={`python -m nbadash.ingest props`} />.</>}
      </p>
    );

  const setPrefs = (p: MarketPrefs) => { const n = normalizePrefs(p); setPrefsState(n); savePrefs(n); };
  const patch = (p: Partial<Filters>) => setFilters((f) => ({ ...f, ...p }));
  const nums = bars.map((b) => b.value);
  const auto = defaultLine(nums);
  const line = lines[market.key] ?? auto;
  const hr = hitRate(nums, line, market.binary);
  const avg = averages(sel.sample);
  const base = averages(sel.baseline);
  const delta = (k: keyof Averages) => (avg[k] != null && base[k] != null ? (avg[k] as number) - (base[k] as number) : null);
  const activeStat = STAT_FOR_MARKET[market.key];
  const names = (pid: number) => data.teammates.find((t) => t.player_id === pid)?.name ?? `#${pid}`;
  const active = activeFilterLabels(filters, oppAbbr, names);
  const hitTone = hr.pct == null ? "text-muted" : hr.pct >= 0.55 ? "text-win" : hr.pct <= 0.45 ? "text-live" : "text-fg";
  const setLine = (v: number) => setLines((l) => ({ ...l, [market.key]: Math.max(0.5, Math.round(v * 2) / 2) }));

  return (
    <div className="space-y-3">
      {!hideMarketBar && <MarketBar markets={markets} active={market.key} onSelect={setMarketKey} onCustomize={() => setDialog(true)} />}
      <MarketsDialog open={dialog} prefs={prefs} onChange={setPrefs} onClose={() => setDialog(false)} />

      {/* summary */}
      <section aria-label="Summary" className="flex flex-wrap items-center gap-x-8 gap-y-3 rounded-lg border border-line bg-surface p-3">
        <div className="min-w-40">
          <div className="text-xs font-medium text-muted">HIT RATE · {market.label.toUpperCase()}</div>
          <div className={`num text-2xl font-bold ${hitTone}`}>{hr.pct == null ? "–" : `${(hr.pct * 100).toFixed(1)}%`}
            <span className="ml-1.5 text-base font-semibold">({hr.over}/{hr.total})</span></div>
          <div className="text-xs text-muted">{market.binary ? "games achieved" : `over ${line}`}{hr.total < 10 && hr.total > 0 ? " · small sample" : ""}</div>
        </div>
        <dl className="flex flex-wrap gap-x-4 gap-y-2" aria-label="Averages over this sample">
          <Stat label="PTS" value={avg.pts} delta={delta("pts")} active={activeStat === "pts"} />
          <Stat label="AST" value={avg.ast} delta={delta("ast")} active={activeStat === "ast"} />
          <Stat label="REB" value={avg.reb} delta={delta("reb")} active={activeStat === "reb"} />
          <Stat label="3PM" value={avg.fg3m} delta={delta("fg3m")} active={activeStat === "fg3m"} />
          <Stat label="MINS" value={avg.min} delta={delta("min")} />
          <Stat label="USAGE" value={avg.usg} delta={delta("usg")} suffix="%" />
          <Stat label="FGA" value={avg.fga} delta={delta("fga")} />
        </dl>
      </section>

      {/* controls */}
      <div className="flex flex-wrap items-center gap-3">
        {!market.binary && (
          <div role="group" aria-label="Line" className="inline-flex items-center rounded-lg border border-line bg-surface">
            <button onClick={() => setLine(line - 0.5)} aria-label="Lower the line" className="min-h-11 min-w-11 text-lg text-muted hover:text-fg">−</button>
            <input key={line} type="number" step={0.5} min={0.5} defaultValue={line} aria-label="Line"
              onBlur={(e) => { const v = Number(e.target.value); if (e.target.value !== "" && Number.isFinite(v) && v > 0) setLine(v); else e.target.value = String(line); }}
              onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }}
              className="num w-16 bg-transparent text-center text-base font-bold" />
            <button onClick={() => setLine(line + 0.5)} aria-label="Raise the line" className="min-h-11 min-w-11 text-lg text-muted hover:text-fg">+</button>
          </div>
        )}
        {!market.binary && lines[market.key] != null && (
          <button className="min-h-11 text-sm text-muted underline hover:text-fg" onClick={() => setLines((l) => Object.fromEntries(Object.entries(l).filter(([k]) => k !== market.key)))}>Reset line ({auto})</button>
        )}
        <label className="inline-flex items-center gap-2 text-sm text-muted">
          Opponent
          <select value={opp === null ? "next" : opp} onChange={(e) => setOpp(e.target.value === "next" ? null : e.target.value === "none" ? "none" : Number(e.target.value))}
            className="min-h-11 rounded-lg border border-line bg-surface px-2 text-base text-fg">
            <option value="next">{data.next_game ? `Next: ${data.next_game.home ? "vs" : "@"} ${data.next_game.opp_abbr}` : "No scheduled game"}</option>
            <option value="none">None</option>
            {teams.data?.map((t) => <option key={t.id} value={t.id}>{t.city} {t.name}</option>)}
          </select>
        </label>
        <button onClick={() => setShowFilters((s) => !s)} aria-expanded={showFilters}
          className="ml-auto min-h-11 rounded-lg border border-line bg-surface px-4 text-sm font-semibold hover:bg-surface2">
          Filters{active.length ? ` (${active.length})` : ""}
        </button>
      </div>

      {(bookLines?.markets[market.key] ?? []).length > 0 && !market.binary && (
        <section aria-label="Sportsbook lines" className="rounded-lg border border-line bg-surface p-3">
          <h3 className="text-xs font-medium text-muted">
            Sportsbook lines · {market.label} · consensus {consensus(bookLines!.markets[market.key])}
          </h3>
          <ul className="mt-2 flex flex-wrap gap-2">
            {bookLines!.markets[market.key].map((b) => (
              <li key={b.book}>
                <button onClick={() => setLine(b.line)} aria-pressed={line === b.line}
                  title={b.opening_line !== b.line ? `Opened at ${b.opening_line}` : "Unchanged since it was posted"}
                  className={`min-h-11 rounded-lg border px-3 text-left text-sm ${line === b.line ? "border-accent bg-surface2" : "border-line hover:bg-surface2"}`}>
                  <span className="block text-xs text-muted">{bookName(b.book)}</span>
                  <span className="num font-semibold">{b.line}</span>
                  {moveText(b.line, b.opening_line) && <span className="num ml-1 text-xs text-muted">({moveText(b.line, b.opening_line)})</span>}
                  <span className="num ml-2 text-xs text-muted">{priceText(b.over_price)}{b.under_price != null ? ` / ${priceText(b.under_price)}` : ""}</span>
                </button>
              </li>
            ))}
          </ul>
          <p className="mt-1 flex items-center gap-2 text-xs text-muted">
            {sourceName(bookLines!.source)}, as of {bookLines!.as_of ? new Date(bookLines!.as_of).toLocaleString() : "unknown"}. Press a book to set the line.
            <InfoTip label="About these lines">
              Lines for {bookLines!.game_id ? "the next game" : "a game"}. Over / under prices are American odds. Pressing a book sets the line above. Lines move and books differ: check before relying on them.
            </InfoTip>
          </p>
        </section>
      )}

      {showFilters && <FiltersPanel f={filters} set={patch} seasons={data.seasons} teammates={data.teammates} oppAbbr={oppAbbr} />}

      {active.length > 0 && (
        <ul className="flex flex-wrap gap-2" aria-label="Active filters">
          {active.map((a) => (
            <li key={a.key}>
              <button onClick={() => patch(a.clear)} aria-label={`Remove filter ${a.label}`} className="min-h-9 rounded-full border border-accent bg-surface2 px-3 text-sm font-semibold">{a.label} ✕</button>
            </li>
          ))}
        </ul>
      )}

      <PropsChart bars={bars} line={line} binary={!!market.binary} next={data.next_game} marketLabel={market.label} />
      <p className="flex items-center gap-2 text-xs text-muted" role="status">
        Last {bars.length} of {sel.pool.length} matching games{filters.seasons === "all" ? "" : ` in ${filters.seasons.join(", ")}`}.
        {bars.length < sel.sample.length && ` ${sel.sample.length - bars.length} have no ${market.label} data.`}
        <InfoTip label="About this sample">Deltas compare this sample with all games in the selected seasons. The line is yours to set; sportsbook lines, when available, are offered above as shortcuts.</InfoTip>
      </p>

      <SplitsPanel groups={splits} market={market} line={line} seasonLabel={filters.seasons === "all" ? "All ingested seasons" : filters.seasons.join(", ")} />

      <MatchupPanels playerId={id} oppId={oppId} market={market} />
    </div>
  );
}
