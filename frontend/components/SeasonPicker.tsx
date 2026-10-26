"use client";
import type { DataAvailability } from "@/lib/types";

export interface Selection { season: string; type: "regular" | "playoffs" }

export function useDefaultSelection(available: DataAvailability[], picked: Selection | null): Selection | null {
  if (picked) return picked;
  const first = available[0];
  return first ? { season: first.season, type: first.season_type } : null;
}

/** Select of the (season, type) pairs for which data was ingested. */
export function SeasonPicker({ available, value, onChange, count }: {
  available: DataAvailability[]; value: Selection; onChange: (s: Selection) => void; count: "games" | "shots";
}) {
  const key = (a: { season: string; type?: string; season_type?: string }) => `${a.season}|${a.type ?? a.season_type}`;
  return (
    <label className="inline-flex items-center gap-2 text-sm text-muted">
      Season
      <select value={key(value)} className="min-h-11 rounded-lg border border-line bg-surface px-3 text-base text-fg"
        onChange={(e) => {
          const [season, type] = e.target.value.split("|");
          onChange({ season, type: type as Selection["type"] });
        }}>
        {available.map((a) => (
          <option key={key(a)} value={key(a)}>
            {a.season}{a.season_type === "playoffs" ? " playoffs" : ""} ({a[count]} {a[count] === 1 ? count.slice(0, -1) : count})
          </option>
        ))}
      </select>
    </label>
  );
}
