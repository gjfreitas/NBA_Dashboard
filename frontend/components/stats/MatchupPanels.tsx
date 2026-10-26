"use client";
import { SetupHint } from "../SetupHint";
import { useState } from "react";
import { useFetch } from "@/lib/hooks";
import type { Market } from "@/lib/props";
import type { Matchup, PlayTypeRow, ShotTypeRow, ZoneRow } from "@/lib/types";
import { SimilarPlayersPanel } from "./SimilarPlayersPanel";

const short = (s: string) => `${s.slice(2, 4)}/${s.slice(5)}`;
const pct = (v: number | null, digits = 0) => (v == null ? "–" : `${(v * 100).toFixed(digits)}%`);

type Tone = "tough" | "even" | "soft" | "none";
/** Defence rank among 30 teams, 1 = allows the least. Tough for the shooter = red, soft = green. */
export const rankTone = (rank: number | null): Tone => (rank == null ? "none" : rank <= 10 ? "tough" : rank <= 20 ? "even" : "soft");
const TONE_BG: Record<Tone, string> = {
  tough: "var(--live-strong)", even: "#a16207", soft: "var(--win-strong)", none: "var(--surface-2)",
};
const TONE_WORD: Record<Tone, string> = { tough: "tough", even: "average", soft: "weak", none: "" };

export function RankPill({ rank }: { rank: number | null }) {
  const t = rankTone(rank);
  return (
    <span className="num inline-block min-w-10 rounded px-1.5 py-0.5 text-center text-xs font-bold text-white"
      style={{ background: TONE_BG[t] }} title={rank ? `Ranks ${rank} of 30 (1 = allows the least) — ${TONE_WORD[t]} matchup` : "No opponent selected"}>
      {rank ? `#${rank}` : "–"}<span className="sr-only">{rank ? ` of 30, ${TONE_WORD[t]} matchup` : ""}</span>
    </span>
  );
}

// ---------------------------------------------------------------- zones ----

/** Zone geometry in NBA shot-chart units (tenths of a foot, rim at the origin, +y toward half court). */
const ARC_Y = Math.sqrt(237.5 ** 2 - 220 ** 2);
const LABEL_AT: Record<string, [number, number]> = {
  "Restricted Area": [0, 30], "In The Paint (Non-RA)": [0, 100], "Mid-Range": [0, 205], "Left Corner 3": [-232, 20],
  "Right Corner 3": [232, 20], "Above the Break 3": [0, 310],
};

/** Fill + opacity for a zone. Player view: green/red by distance from the league average, stronger = further away. */
function zoneStyle(z: ZoneRow, mode: "player" | "opp"): { fill: string; opacity: number } {
  if (mode === "opp") return { fill: TONE_BG[rankTone(z.opp_rank)], opacity: z.opp_rank ? 0.55 + 0.45 * (Math.abs(z.opp_rank - 15.5) / 14.5) : 1 };
  if (z.fg_pct == null || z.league_fg_pct == null || z.fga < 5) return { fill: "var(--surface-2)", opacity: 1 };
  const d = z.fg_pct - z.league_fg_pct;
  const strength = 0.55 + 0.45 * Math.min(Math.abs(d) / 0.12, 1);
  return d >= 0.03 ? { fill: "var(--win-strong)", opacity: strength } : d <= -0.03 ? { fill: "var(--live-strong)", opacity: strength } : { fill: "#a16207", opacity: 0.8 };
}

function ZoneCourt({ zones, mode }: { zones: ZoneRow[]; mode: "player" | "opp" }) {
  const by = Object.fromEntries(zones.map((z) => [z.zone, z]));
  const st = (zone: string) => zoneStyle(by[zone], mode);
  const line = { fill: "none", stroke: "var(--bg)", strokeWidth: 3 } as const;
  const label = (zone: string) => {
    const z = by[zone];
    const [x, y] = LABEL_AT[zone];
    const text = mode === "player" ? [pct(z.fg_pct), `${pct(z.share)} of shots`] : [pct(z.opp_fg_pct), z.opp_rank ? `#${z.opp_rank}` : "–"];
    const w = zone.includes("Corner") ? 62 : 104;
    return (
      <g key={zone} transform={`translate(${x} ${365 - y})`}>
        <rect x={-w / 2} y={-19} width={w} height={38} rx={5} fill="var(--bg)" opacity={0.88} />
        <text textAnchor="middle" y={-3} fontSize={zone.includes("Corner") ? 15 : 18} fontWeight={700} fill="var(--text)">{text[0]}</text>
        <text textAnchor="middle" y={14} fontSize={zone.includes("Corner") ? 11 : 12} fill="var(--muted)">{zone.includes("Corner") && mode === "player" ? text[1].replace(" of shots", "") : text[1]}</text>
      </g>
    );
  };
  const aria = zones.map((z) => (mode === "player" ? `${z.label}: ${pct(z.fg_pct)} on ${z.fga} shots` : `${z.label}: opponent allows ${pct(z.opp_fg_pct)}, rank ${z.opp_rank ?? "n/a"}`)).join("; ");
  return (
    <svg viewBox="-260 -67.5 520 490" className="mx-auto w-full max-w-md" role="img" aria-label={aria}>
      <g transform="translate(0 365) scale(1 -1)">
        <rect x={-250} y={-47.5} width={500} height={470} fill={st("Above the Break 3").fill} fillOpacity={st("Above the Break 3").opacity} />
        <rect x={-250} y={-47.5} width={30} height={47.5 + ARC_Y} fill={st("Left Corner 3").fill} fillOpacity={st("Left Corner 3").opacity} />
        <rect x={220} y={-47.5} width={30} height={47.5 + ARC_Y} fill={st("Right Corner 3").fill} fillOpacity={st("Right Corner 3").opacity} />
        <path d={`M -220 -47.5 L -220 ${ARC_Y} A 237.5 237.5 0 0 0 220 ${ARC_Y} L 220 -47.5 Z`} fill={st("Mid-Range").fill} fillOpacity={st("Mid-Range").opacity} />
        <rect x={-80} y={-47.5} width={160} height={190} fill={st("In The Paint (Non-RA)").fill} fillOpacity={st("In The Paint (Non-RA)").opacity} />
        <circle cx={0} cy={0} r={40} fill={st("Restricted Area").fill} fillOpacity={st("Restricted Area").opacity} />
        {/* lines on top */}
        <rect x={-250} y={-47.5} width={500} height={470} {...line} />
        <path d={`M -220 -47.5 L -220 ${ARC_Y} A 237.5 237.5 0 0 0 220 ${ARC_Y} L 220 -47.5`} {...line} />
        <rect x={-80} y={-47.5} width={160} height={190} {...line} />
        <circle cx={0} cy={0} r={40} {...line} />
        <circle cx={0} cy={0} r={7.5} fill="none" stroke="var(--text)" strokeWidth={2} />
      </g>
      {Object.keys(LABEL_AT).map(label)}
    </svg>
  );
}

function Legend({ mode }: { mode: "player" | "opp" }) {
  const items: [string, string][] = mode === "player"
    ? [["var(--win-strong)", "Above league average"], ["#a16207", "Near average"], ["var(--live-strong)", "Below league average"]]
    : [["var(--live-strong)", "Tough defence (rank 1–10)"], ["#a16207", "Average (11–20)"], ["var(--win-strong)", "Weak defence (21–30)"]];
  return (
    <ul className="mt-2 flex flex-wrap justify-center gap-x-4 gap-y-1 text-xs text-muted">
      {items.map(([c, t]) => <li key={t}><span className="mr-1 inline-block size-2.5 rounded-sm align-middle" style={{ background: c }} />{t}</li>)}
    </ul>
  );
}

function ZonesPanel({ m }: { m: Matchup }) {
  const [mode, setMode] = useState<"player" | "opp">("player");
  const noOpp = mode === "opp" && !m.opponent;
  return (
    <section aria-label="Shooting zones" className="rounded-lg border border-line bg-surface p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">Shooting zones</h3>
        <div role="group" aria-label="Zone view" className="flex rounded-lg border border-line text-sm">
          {([["player", "Player"], ["opp", m.opponent?.abbr ? `${m.opponent.abbr} defence` : "Opp defence"]] as const).map(([v, l]) => (
            <button key={v} aria-pressed={mode === v} onClick={() => setMode(v)}
              className={`min-h-9 px-3 ${mode === v ? "bg-surface2 font-semibold" : "text-muted hover:text-fg"} ${v === "player" ? "rounded-l-lg" : "rounded-r-lg"}`}>{l}</button>
          ))}
        </div>
      </div>
      {noOpp ? <p className="p-6 text-center text-sm text-muted">Choose an opponent to see how their defence ranks by zone.</p> : (
        <>
          <ZoneCourt zones={m.zones} mode={mode} />
          <Legend mode={mode} />
          <p className="mt-1 text-center text-xs text-muted">
            {mode === "player" ? "FG% in each zone and its share of the player’s shots." : "FG% the defence allows in each zone and its rank (1 = allows the lowest)."}
          </p>
        </>
      )}
    </section>
  );
}

// ------------------------------------------------------------ shot types ----

function ShotTypesPanel({ rows }: { rows: ShotTypeRow[] }) {
  // catch & shoot and pull-ups are exclusive; "under 10 ft" overlaps them, so bars use each type's own share of all shots
  const total = rows.reduce((a, r) => a + (r.share ?? 0), 0) || 1;
  return (
    <section aria-label="Shot type analysis" className="rounded-lg border border-line bg-surface p-3">
      <h3 className="mb-3 text-sm font-semibold">Shot type analysis</h3>
      <div className="flex overflow-hidden rounded-lg" role="img"
        aria-label={rows.map((r) => `${r.label}: ${pct(r.share)} of shots, opponent rank ${r.opp_rank ?? "n/a"}`).join("; ")}>
        {rows.map((r) => (
          <div key={r.key} className="num flex min-h-12 flex-col items-center justify-center px-1 text-center text-xs font-bold text-white"
            style={{ width: `${((r.share ?? 0) / total) * 100}%`, minWidth: 64, background: TONE_BG[rankTone(r.opp_rank)] }}>
            <span>{pct(r.share)}</span><span className="font-normal opacity-90">{r.opp_rank ? `#${r.opp_rank}` : "–"}</span>
          </div>
        ))}
      </div>
      <table className="num mt-3 w-full border-collapse text-sm">
        <caption className="sr-only">Shot types</caption>
        <thead><tr className="text-xs text-muted"><th className="py-1 text-left font-medium">Type</th><th className="text-right font-medium">FG%</th><th className="text-right font-medium">FGM-FGA</th><th className="text-right font-medium">Opp eFG% allowed</th><th className="text-right font-medium">Rank</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key} className="border-t border-line">
              <th scope="row" className="py-1.5 text-left font-normal">{r.label}</th>
              <td className="text-right font-semibold">{pct(r.fg_pct, 1)}</td><td className="text-right text-muted">{r.fgm}-{r.fga}</td>
              <td className="text-right text-muted">{pct(r.opp_efg_pct, 1)}</td><td className="text-right"><RankPill rank={r.opp_rank} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-muted">Bar widths are each type’s share of the player’s attempts (under-10-ft shots overlap the other two). Colour is the opponent’s defensive rank against that shot type.</p>
    </section>
  );
}

// ------------------------------------------------------------ play types ----

function PlayTypesPanel({ rows, opp }: { rows: PlayTypeRow[]; opp: string | null }) {
  if (!rows.length) return <section className="rounded-lg border border-line bg-surface p-3"><h3 className="mb-2 text-sm font-semibold">Play type analysis</h3><p className="text-sm text-muted">No play-type data for this season yet.</p></section>;
  const max = Math.max(...rows.map((r) => r.pts_pg), 0.1);
  return (
    <section aria-label="Play type analysis" className="rounded-lg border border-line bg-surface p-3">
      <h3 className="mb-2 text-sm font-semibold">Play type analysis</h3>
      <table className="num w-full border-collapse text-sm">
        <caption className="sr-only">Points per game by play type and the opponent’s defensive rank</caption>
        <thead><tr className="text-xs text-muted"><th className="py-1 text-left font-medium">Play type</th><th className="text-left font-medium">Points per game</th><th className="text-right font-medium">PPP</th><th className="text-right font-medium">{opp ? `${opp} D rank` : "Opp D rank"}</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key} className="border-t border-line">
              <th scope="row" className="py-1.5 pr-2 text-left font-normal">{r.label}</th>
              <td className="min-w-28 pr-2">
                <div className="flex items-center gap-2">
                  <span className="w-8 shrink-0 font-semibold">{r.pts_pg.toFixed(1)}</span>
                  <div className="h-2 flex-1 rounded-full bg-surface2" aria-hidden><div className="h-2 rounded-full bg-accent" style={{ width: `${(r.pts_pg / max) * 100}%` }} /></div>
                  <span className="w-9 shrink-0 text-right text-xs text-muted">{pct(r.share)}</span>
                </div>
              </td>
              <td className="text-right text-muted">{r.ppp?.toFixed(2) ?? "–"}</td>
              <td className="text-right"><RankPill rank={r.opp_rank} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-muted">Synergy play types, regular season. PPP = points per possession. Rank is the opponent’s points per possession allowed (1 = allows the least); free-throw points are included in each play type.</p>
    </section>
  );
}

export function MatchupPanels({ playerId, oppId, market }: { playerId: string | number; oppId: number | null; market: Market }) {
  const [season, setSeason] = useState<string | null>(null);
  const qs = new URLSearchParams();
  if (season) qs.set("season", season);
  if (oppId != null) qs.set("opp", String(oppId));
  const { data, loading, notFound, error } = useFetch<Matchup>(`/api/players/${playerId}/matchup${qs.size ? `?${qs}` : ""}`);
  if (loading && !data) return <div className="h-80 skeleton rounded-lg bg-surface" aria-busy />;
  if (notFound || !data)
    return <p className="rounded-lg border border-dashed border-line p-4 text-sm text-muted">
      {error ? `Can’t load matchup data (${error}).` : <>No zone or play-type data for this player. <SetupHint cmd={`python -m nbadash.ingest props`} />.</>}</p>;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-medium text-muted">
          Matchup analysis {data.opponent ? <>vs <span className="font-semibold text-fg">{data.opponent.name}</span></> : "(no opponent selected)"}
        </h2>
        <label className="inline-flex items-center gap-2 text-sm text-muted">
          Season
          <select value={data.season} onChange={(e) => setSeason(e.target.value)} className="min-h-9 rounded-lg border border-line bg-surface px-2 text-fg">
            {data.seasons.map((s) => <option key={s} value={s}>{short(s)}</option>)}
          </select>
        </label>
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        <ZonesPanel m={data} />
        <div className="space-y-3">
          <ShotTypesPanel rows={data.shot_types} />
          <PlayTypesPanel rows={data.play_types} opp={data.opponent?.abbr ?? null} />
        </div>
      </div>
      <SimilarPlayersPanel playerId={playerId} season={data.season} oppId={oppId} market={market} oppAbbr={data.opponent?.abbr ?? null} />
    </div>
  );
}
