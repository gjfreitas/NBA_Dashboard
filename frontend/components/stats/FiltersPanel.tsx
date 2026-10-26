"use client";
import { DEFAULT_FILTERS, type Filters } from "@/lib/props";
import type { PropTeammate } from "@/lib/types";

const short = (s: string) => `${s.slice(2, 4)}/${s.slice(5)}`;

function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap items-center gap-2">
      <span className="w-24 shrink-0 text-xs font-medium text-muted">{label}</span>
      {children}
    </div>
  );
}

const chip = (on: boolean) =>
  `min-h-9 rounded-full border px-3 text-sm ${on ? "border-accent bg-surface2 font-semibold" : "border-line text-muted hover:text-fg"}`;

function Chip({ on, onClick, children, disabled }: { on: boolean; onClick: () => void; children: React.ReactNode; disabled?: boolean }) {
  return <button className={`${chip(on)} disabled:cursor-not-allowed disabled:opacity-50`} aria-pressed={on} onClick={onClick} disabled={disabled}>{children}</button>;
}

/** Tick the teammates he played with (or without): ticking in one list takes the player out of the other. */
function TeammateList({ label, hint, ids, other, teammates, onChange }: {
  label: string; hint: string; ids: number[]; other: number[]; teammates: PropTeammate[]; onChange: (ids: number[], other: number[]) => void;
}) {
  return (
    <fieldset className="min-w-0 rounded-lg border border-line p-2">
      <legend className="px-1 text-xs font-medium text-muted">{label} teammate <span className="font-normal">({hint})</span></legend>
      <ul className="max-h-44 space-y-0.5 overflow-y-auto">
        {teammates.map((t) => {
          const on = ids.includes(t.player_id);
          return (
            <li key={t.player_id}>
              <label className={`flex min-h-9 cursor-pointer items-center gap-2 rounded px-2 text-sm ${on ? "bg-surface2 font-semibold" : "hover:bg-surface2"}`}>
                <input type="checkbox" checked={on} className="size-4 accent-[var(--accent)]"
                  onChange={() => onChange(on ? ids.filter((x) => x !== t.player_id) : [...ids, t.player_id], other.filter((x) => x !== t.player_id))} />
                <span className="min-w-0 flex-1 truncate">{t.name}</span>
                <span className="num text-xs text-muted">{t.games}</span>
              </label>
            </li>
          );
        })}
      </ul>
    </fieldset>
  );
}

export function FiltersPanel({ f, set, seasons, teammates, oppAbbr }: {
  f: Filters; set: (patch: Partial<Filters>) => void; seasons: string[]; teammates: PropTeammate[]; oppAbbr: string | null;
}) {
  const allSeasons = f.seasons === "all";
  const toggleSeason = (s: string) => {
    if (f.seasons === "all") { set({ seasons: [s] }); return; } // from "All", a season chip means "only this one"
    const cur = f.seasons;
    const next = cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s];
    set({ seasons: next.length === 0 || next.length === seasons.length ? "all" : next });
  };

  return (
    <section aria-label="Filters" className="space-y-3 rounded-lg border border-line bg-surface p-3">
      <Group label="Season">
        {seasons.map((s) => <Chip key={s} on={!allSeasons && f.seasons.includes(s)} onClick={() => toggleSeason(s)}>{short(s)}</Chip>)}
        <Chip on={allSeasons} onClick={() => set({ seasons: "all" })}>All</Chip>
      </Group>
      <Group label="Games">
        {[5, 10, 20, 30, 40].map((n) => <Chip key={n} on={f.games === n} onClick={() => set({ games: n })}>{n}</Chip>)}
        <Chip on={f.games === "max"} onClick={() => set({ games: "max" })}>Max</Chip>
      </Group>
      <Group label="Venue">
        {(["all", "home", "away"] as const).map((v) => <Chip key={v} on={f.venue === v} onClick={() => set({ venue: v })}>{v === "all" ? "All" : v === "home" ? "Home" : "Away"}</Chip>)}
      </Group>
      <Group label="Season type">
        {(["all", "regular", "playoffs"] as const).map((v) => <Chip key={v} on={f.type === v} onClick={() => set({ type: v })}>{v === "all" ? "All" : v === "regular" ? "Regular season" : "Playoffs"}</Chip>)}
      </Group>
      <Group label="Result">
        {([["any", "Any"], ["W", "Wins"], ["L", "Losses"]] as const).map(([v, l]) => <Chip key={v} on={f.result === v} onClick={() => set({ result: v })}>{l}</Chip>)}
      </Group>
      <Group label="Rest">
        {([["any", "Any"], ["yes", "Back-to-back"], ["no", "Not back-to-back"]] as const).map(([v, l]) => <Chip key={v} on={f.b2b === v} onClick={() => set({ b2b: v })}>{l}</Chip>)}
      </Group>
      <Group label="Minutes">
        {[0, 20, 25, 30].map((m) => <Chip key={m} on={f.minMinutes === m} onClick={() => set({ minMinutes: m })}>{m === 0 ? "Any" : `${m}+`}</Chip>)}
      </Group>
      <Group label="Opp. defence">
        {([["any", "Any"], ["top10", "Top 10"], ["mid", "Middle"], ["bottom10", "Bottom 10"]] as const).map(([v, l]) => <Chip key={v} on={f.oppDef === v} onClick={() => set({ oppDef: v })}>{l}</Chip>)}
        <span className="text-xs text-muted">by season-end defensive rating</span>
      </Group>
      <Group label="Head to head">
        <Chip on={f.h2h} disabled={!oppAbbr} onClick={() => set({ h2h: !f.h2h })}>{oppAbbr ? `Only vs ${oppAbbr}` : "No next opponent to compare"}</Chip>
      </Group>
      <div className="grid gap-3 sm:grid-cols-2">
        <TeammateList label="With" hint="games he played in" ids={f.withTm} other={f.withoutTm} teammates={teammates} onChange={(ids, other) => set({ withTm: ids, withoutTm: other })} />
        <TeammateList label="Without" hint="games he missed" ids={f.withoutTm} other={f.withTm} teammates={teammates} onChange={(ids, other) => set({ withoutTm: ids, withTm: other })} />
      </div>
      {!teammates.length && <p className="text-xs text-muted">No regular teammates in this sample.</p>}

      <button className="min-h-9 text-sm text-muted underline hover:text-fg" onClick={() => set({ ...DEFAULT_FILTERS })}>Reset filters</button>
    </section>
  );
}

/** A removable chip for every filter that narrows the sample (seasons and game count live in the panel). */
export function activeFilterLabels(f: Filters, oppAbbr: string | null, name: (id: number) => string): { key: string; label: string; clear: Partial<Filters> }[] {
  const out: { key: string; label: string; clear: Partial<Filters> }[] = [];
  if (f.venue !== "all") out.push({ key: "venue", label: f.venue === "home" ? "Home" : "Away", clear: { venue: "all" } });
  if (f.type !== "all") out.push({ key: "type", label: f.type === "regular" ? "Regular season" : "Playoffs", clear: { type: "all" } });
  if (f.result !== "any") out.push({ key: "result", label: f.result === "W" ? "Wins" : "Losses", clear: { result: "any" } });
  if (f.b2b !== "any") out.push({ key: "b2b", label: f.b2b === "yes" ? "Back-to-back" : "Not back-to-back", clear: { b2b: "any" } });
  if (f.minMinutes > 0) out.push({ key: "min", label: `${f.minMinutes}+ min`, clear: { minMinutes: 0 } });
  if (f.oppDef !== "any") out.push({ key: "def", label: `Opp defence: ${f.oppDef === "top10" ? "top 10" : f.oppDef === "bottom10" ? "bottom 10" : "middle"}`, clear: { oppDef: "any" } });
  if (f.h2h) out.push({ key: "h2h", label: `vs ${oppAbbr ?? "opponent"}`, clear: { h2h: false } });
  for (const id of f.withTm) out.push({ key: `w${id}`, label: `With ${name(id)}`, clear: { withTm: f.withTm.filter((x) => x !== id) } });
  for (const id of f.withoutTm) out.push({ key: `o${id}`, label: `Without ${name(id)}`, clear: { withoutTm: f.withoutTm.filter((x) => x !== id) } });
  return out;
}
