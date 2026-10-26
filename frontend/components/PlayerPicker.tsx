"use client";
import { useEffect, useState } from "react";
import { useFetch } from "@/lib/hooks";
import type { PlayerProfile, PlayerSummary } from "@/lib/types";
import { Headshot } from "./Headshot";

/** Shows the chosen player (with a Change button) or a search box with results listed beneath it. */
export function PlayerPicker({ label, accent, player, loading, onSelect, onClear }: {
  label: string; accent: string; player: PlayerProfile | null; loading: boolean;
  onSelect: (id: number) => void; onClear: () => void;
}) {
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setQ(text.trim()), 250);
    return () => clearTimeout(t);
  }, [text]);
  const searching = !player && !loading;
  const { data } = useFetch<PlayerSummary[]>(searching && q ? `/api/players?q=${encodeURIComponent(q)}&limit=6` : null);

  return (
    <div className="rounded-lg border bg-surface p-3" style={{ borderColor: accent }}>
      {player ? (
        <div className="flex items-center gap-3">
          <Headshot id={player.id} name={player.name} width={64} />
          <div className="min-w-0 flex-1">
            <div className="truncate font-semibold">{player.name}</div>
            <div className="truncate text-xs text-muted">{[player.team, player.position].filter(Boolean).join(" · ")}</div>
          </div>
          <button onClick={onClear} className="min-h-11 shrink-0 px-2 text-sm text-muted underline hover:text-fg">Change</button>
        </div>
      ) : loading ? (
        <div className="h-12 skeleton rounded bg-surface2" aria-busy />
      ) : (
        <div>
          <label className="block text-xs font-medium text-muted" htmlFor={`pick-${label}`}>{label}</label>
          <input id={`pick-${label}`} type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder="Search a player…"
            className="mt-1 min-h-11 w-full rounded-lg border border-line bg-bg px-3 text-base placeholder:text-muted" />
          <ul className="mt-2 space-y-1" aria-live="polite">
            {data?.map((p) => (
              <li key={p.id}>
                <button onClick={() => onSelect(p.id)} className="flex min-h-11 w-full items-center gap-2 rounded px-2 text-left hover:bg-surface2">
                  <span className="truncate font-medium">{p.name}</span>
                  <span className="shrink-0 text-xs text-muted">{[p.team, p.position].filter(Boolean).join(" · ")}</span>
                </button>
              </li>
            ))}
            {data && !data.length && <li className="px-2 text-sm text-muted">No players match “{q}”.</li>}
          </ul>
        </div>
      )}
    </div>
  );
}
