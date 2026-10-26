"use client";
import { SetupHint } from "./SetupHint";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useFetch } from "@/lib/hooks";
import type { PlayerProfile, SeasonLine, ShotChart } from "@/lib/types";
import { pct } from "./PlayerOverview";
import { PlayerPicker } from "./PlayerPicker";
import { ShotCourt } from "./ShotCourt";

const COLOR_A = "var(--accent)";
const COLOR_B = "var(--focus)";

type Mode = "pg" | "per36";

interface Stat {
  label: string; get: (l: SeasonLine) => number | null; fmt: (v: number) => string;
  lowerBetter?: boolean; scalable?: boolean; // scalable = counting stat that per-36 rescales
}

const one = (v: number) => v.toFixed(1);
const ratio = (v: number) => (v * 100).toFixed(1);

const VOLUME: Stat[] = [
  { label: "Points", get: (l) => l.ppg, fmt: one, scalable: true },
  { label: "Rebounds", get: (l) => l.rpg, fmt: one, scalable: true },
  { label: "Assists", get: (l) => l.apg, fmt: one, scalable: true },
  { label: "Steals", get: (l) => l.spg, fmt: one, scalable: true },
  { label: "Blocks", get: (l) => l.bpg, fmt: one, scalable: true },
  { label: "Turnovers", get: (l) => l.tpg, fmt: one, scalable: true, lowerBetter: true },
];
const EFFICIENCY: Stat[] = [
  { label: "FG%", get: (l) => l.fg_pct, fmt: ratio },
  { label: "3P%", get: (l) => l.fg3_pct, fmt: ratio },
  { label: "FT%", get: (l) => l.ft_pct, fmt: ratio },
  { label: "eFG%", get: (l) => l.efg_pct, fmt: ratio },
  { label: "TS%", get: (l) => l.ts_pct, fmt: ratio },
];

function value(s: Stat, l: SeasonLine, mode: Mode): number | null {
  const v = s.get(l);
  if (v == null) return null;
  return mode === "per36" && s.scalable ? (l.mpg > 0 ? (v * 36) / l.mpg : null) : v;
}

/** One line per player/season: the traded-player TOT row when there is one, else the single team row. */
function lineFor(p: PlayerProfile, season: string): SeasonLine | null {
  if (season === "career") return p.career_regular;
  const rows = p.regular.filter((l) => l.season === season);
  return rows.find((l) => l.team === "TOT") ?? rows[0] ?? null;
}

function Row({ s, a, b, mode }: { s: Stat; a: SeasonLine; b: SeasonLine; mode: Mode }) {
  const va = value(s, a, mode), vb = value(s, b, mode);
  const max = Math.max(va ?? 0, vb ?? 0) || 1;
  const better = va == null || vb == null || va === vb ? 0 : ((va > vb ? 1 : -1) * (s.lowerBetter ? -1 : 1));
  const side = (v: number | null, win: boolean, color: string, right: boolean) => (
    <div className={`flex items-center gap-2 ${right ? "" : "flex-row-reverse"}`}>
      <span className={`w-12 shrink-0 ${right ? "text-left" : "text-right"} ${win ? "font-bold" : "text-muted"}`}>
        {v == null ? "–" : s.fmt(v)}{win && <span className="sr-only"> (better)</span>}
      </span>
      <div className={`h-2 flex-1 ${right ? "" : "flex justify-end"}`} aria-hidden>
        <div className="h-2 rounded-full" style={{ width: `${((v ?? 0) / max) * 100}%`, background: color, opacity: win || better === 0 ? 1 : 0.45 }} />
      </div>
    </div>
  );
  return (
    <div role="row" className="num grid grid-cols-[1fr_5.5rem_1fr] items-center gap-2 border-b border-line px-3 py-2 text-sm last:border-0">
      <div role="cell">{side(va, better === 1, COLOR_A, false)}</div>
      <div role="rowheader" className="text-center text-xs text-muted">{s.label}</div>
      <div role="cell">{side(vb, better === -1, COLOR_B, true)}</div>
    </div>
  );
}

function ZoneCompare({ a, b, nameA, nameB }: { a: ShotChart; b: ShotChart; nameA: string; nameB: string }) {
  const zones = [...new Set([...a.zones, ...b.zones].map((z) => z.zone))];
  const get = (c: ShotChart, z: string) => c.zones.find((x) => x.zone === z);
  zones.sort((x, y) => (get(b, y)?.attempts ?? 0) + (get(a, y)?.attempts ?? 0) - (get(a, x)?.attempts ?? 0) - (get(b, x)?.attempts ?? 0));
  const cell = (z: ReturnType<typeof get>, win: boolean) => (
    <td className={`px-2 py-2 text-right ${win ? "font-bold" : "text-muted"}`}>
      {z ? <>{pct(z.fg_pct)}<span className="ml-1 text-xs font-normal text-muted">({z.made}/{z.attempts})</span></> : "–"}
    </td>
  );
  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-surface">
      <table className="num w-full border-collapse text-sm">
        <caption className="sr-only">Field goal percentage by zone</caption>
        <thead>
          <tr className="border-b border-line text-xs text-muted">
            <th scope="col" className="px-3 py-2 text-left font-medium">Zone</th>
            <th scope="col" className="px-2 py-2 text-right font-medium" style={{ color: COLOR_A }}>{nameA}</th>
            <th scope="col" className="px-2 py-2 text-right font-medium" style={{ color: COLOR_B }}>{nameB}</th>
          </tr>
        </thead>
        <tbody>
          {zones.map((zn) => {
            const za = get(a, zn), zb = get(b, zn);
            const comparable = za && zb && za.attempts >= 10 && zb.attempts >= 10 && za.fg_pct !== zb.fg_pct; // ignore tiny samples
            return (
              <tr key={zn} className="border-b border-line last:border-0">
                <th scope="row" className="px-3 py-2 text-left font-normal">{zn}</th>
                {cell(za, !!comparable && za!.fg_pct > zb!.fg_pct)}
                {cell(zb, !!comparable && zb!.fg_pct > za!.fg_pct)}
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="border-t border-line px-3 py-2 text-xs text-muted">Zones with fewer than 10 attempts for either player aren’t highlighted.</p>
    </div>
  );
}

function ShotCompare({ a, b, season }: { a: PlayerProfile; b: PlayerProfile; season: string }) {
  const withShots = (p: PlayerProfile) => new Set(p.available.filter((x) => x.season_type === "regular" && x.shots > 0).map((x) => x.season));
  const sa = withShots(a), sb = withShots(b);
  const common = [...sa].filter((s) => sb.has(s)).sort().reverse();
  const shotSeason = common.includes(season) ? season : common[0] ?? null;
  const ca = useFetch<ShotChart>(shotSeason ? `/api/players/${a.id}/shots?season=${shotSeason}&season_type=regular` : null);
  const cb = useFetch<ShotChart>(shotSeason ? `/api/players/${b.id}/shots?season=${shotSeason}&season_type=regular` : null);
  if (!shotSeason)
    return <p className="rounded-lg border border-dashed border-line p-4 text-sm text-muted">No season has shot data loaded for both players yet.</p>;
  return (
    <section aria-label="Shot charts" className="space-y-3">
      <h2 className="text-sm font-medium text-muted">
        Shot charts, {shotSeason}{season !== "career" && season !== shotSeason ? ` (no shot data for ${season} for both players)` : ""}
      </h2>
      <div className="grid gap-3 sm:grid-cols-2">
        {[{ p: a, c: ca, color: COLOR_A }, { p: b, c: cb, color: COLOR_B }].map(({ p, c, color }) => (
          <figure key={p.id} className="rounded-lg border bg-surface p-2" style={{ borderColor: color }}>
            <figcaption className="mb-1 flex justify-between px-1 text-sm">
              <span className="font-semibold">{p.name}</span>
              {c.data && <span className="num text-muted">{c.data.made}/{c.data.attempts} · {pct(c.data.fg_pct)}%</span>}
            </figcaption>
            {c.data ? (
              <ShotCourt shots={c.data.shots} className="w-full"
                label={`${p.name} shot chart ${shotSeason}: ${c.data.made} of ${c.data.attempts} made`} />
            ) : <div className="aspect-[520/490] skeleton rounded bg-surface2" aria-busy />}
          </figure>
        ))}
      </div>
      {ca.data && cb.data && <ZoneCompare a={ca.data} b={cb.data} nameA={a.name.split(" ").slice(-1)[0]} nameB={b.name.split(" ").slice(-1)[0]} />}
    </section>
  );
}

export function CompareView() {
  const router = useRouter();
  const sp = useSearchParams();
  const ida = sp.get("a"), idb = sp.get("b");
  const season = sp.get("season") ?? "career";
  const mode: Mode = sp.get("mode") === "per36" ? "per36" : "pg";
  const pa = useFetch<PlayerProfile>(ida ? `/api/players/${ida}` : null);
  const pb = useFetch<PlayerProfile>(idb ? `/api/players/${idb}` : null);
  const A = pa.data, B = pb.data;

  const set = (patch: Record<string, string | null>) => {
    const n = new URLSearchParams(sp.toString());
    for (const [k, v] of Object.entries(patch)) {
      if (v == null) n.delete(k);
      else n.set(k, v);
    }
    router.replace(`/compare?${n.toString()}`, { scroll: false });
  };

  const seasons = A && B
    ? [...new Set(A.regular.map((l) => l.season))].filter((s) => B.regular.some((l) => l.season === s)).reverse()
    : [];
  const la = A && lineFor(A, season), lb = B && lineFor(B, season);
  const chip = (on: boolean) => `min-h-11 rounded-full border px-4 text-sm ${on ? "border-accent bg-surface2 font-semibold" : "border-line text-muted hover:text-fg"}`;
  const notLoaded = [A, B].filter((p): p is PlayerProfile => !!p && !p.full_bio_loaded);

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-[1fr_auto_1fr] sm:items-center">
        <PlayerPicker label="Player 1" accent={COLOR_A} player={A} loading={pa.loading} onSelect={(id) => set({ a: String(id) })} onClear={() => set({ a: null })} />
        <button disabled={!ida || !idb} onClick={() => set({ a: idb, b: ida })} aria-label="Swap players"
          className="mx-auto min-h-11 min-w-11 rounded-full border border-line text-muted hover:text-fg disabled:opacity-40">⇄</button>
        <PlayerPicker label="Player 2" accent={COLOR_B} player={B} loading={pb.loading} onSelect={(id) => set({ b: String(id) })} onClear={() => set({ b: null })} />
      </div>

      {(pa.notFound || pb.notFound) && <p role="alert" className="text-muted">One of the players wasn’t found.</p>}
      {notLoaded.map((p) => (
        <p key={p.id} className="rounded-lg border border-dashed border-line p-3 text-sm text-muted">
          Stats for {p.name} aren’t loaded. <SetupHint cmd={`python -m nbadash.ingest player ${p.id}`} />.
        </p>
      ))}

      {A && B && A.full_bio_loaded && B.full_bio_loaded && (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <label className="inline-flex items-center gap-2 text-sm text-muted">
              Season
              <select value={season} onChange={(e) => set({ season: e.target.value })}
                className="min-h-11 rounded-lg border border-line bg-surface px-3 text-base text-fg">
                <option value="career">Career</option>
                {seasons.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </label>
            <div role="group" aria-label="Stat basis" className="flex gap-2">
              <button className={chip(mode === "pg")} aria-pressed={mode === "pg"} onClick={() => set({ mode: null })}>Per game</button>
              <button className={chip(mode === "per36")} aria-pressed={mode === "per36"} onClick={() => set({ mode: "per36" })}>Per 36 min</button>
            </div>
          </div>

          {la && lb ? (
            <section aria-label="Stat comparison" className="overflow-hidden rounded-lg border border-line bg-surface">
              <div className="num grid grid-cols-[1fr_5.5rem_1fr] gap-2 border-b border-line px-3 py-2 text-xs font-semibold">
                <span className="text-right" style={{ color: COLOR_A }}>{A.name}</span><span />
                <span style={{ color: COLOR_B }}>{B.name}</span>
              </div>
              <div role="table" aria-label="Stat comparison">
                <div className="num grid grid-cols-[1fr_5.5rem_1fr] gap-2 border-b border-line bg-surface2 px-3 py-1.5 text-xs text-muted">
                  <span className="text-right">{la.gp} GP · {la.mpg.toFixed(1)} MPG</span><span /><span>{lb.gp} GP · {lb.mpg.toFixed(1)} MPG</span>
                </div>
                {[...VOLUME, ...EFFICIENCY].map((s) => <Row key={s.label} s={s} a={la} b={lb} mode={mode} />)}
              </div>
              {mode === "per36" && <p className="border-t border-line px-3 py-2 text-xs text-muted">Per-36 scales counting stats to 36 minutes; shooting percentages are unchanged.</p>}
            </section>
          ) : (
            <p className="rounded-lg border border-dashed border-line p-4 text-sm text-muted">One of the players has no regular-season stats for {season}.</p>
          )}

          <ShotCompare a={A} b={B} season={season} />
        </>
      )}

      {!ida && !idb && (
        <p className="text-sm text-muted">
          Pick two players to compare. Only players whose data has been ingested can be compared — see <Link className="underline" href="/players">Players</Link>.
        </p>
      )}
    </div>
  );
}
