"use client";
import Link from "next/link";
import { useState } from "react";
import { useFetch } from "@/lib/hooks";

interface Avg { games: number; min: number | null; pts: number | null; reb: number | null; ast: number | null; usg: number | null }
interface Teammate { player_id: number; name: string; with_player: Avg; without: Avg; pts_diff: number | null; min_diff: number | null; small_sample: boolean }
interface Without { player_id: number; name: string; seasons: string[]; games_with: number; games_without: number; teammates: Teammate[] }

const f = (v: number | null) => (v == null ? "–" : v.toFixed(1));
const signed = (v: number | null) => (v == null ? "" : v > 0 ? `+${v.toFixed(1)}` : v.toFixed(1));

function Body({ id }: { id: number }) {
  const { data, loading } = useFetch<Without>(`/api/players/${id}/without`);
  if (loading) return <div className="h-24 skeleton rounded bg-surface2" aria-busy />;
  if (!data || data.teammates.length === 0)
    return <p className="text-xs text-muted">Not enough games without him on this team to say ({data?.games_without ?? 0} missed in {data?.seasons.join(" and ") || "the last two seasons"}).</p>;
  return (
    <div className="space-y-1">
      <table className="num w-full text-sm">
        <caption className="pb-1 text-left text-xs text-muted">
          Teammates’ averages in the {data.games_with} games he played vs the {data.games_without} his team played without him ({data.seasons.join(", ")}).
        </caption>
        <thead className="text-xs text-muted">
          <tr><th scope="col" className="py-1 text-left font-normal">Player</th><th scope="col" className="py-1 text-right font-normal">Pts with</th><th scope="col" className="py-1 text-right font-normal">Pts without</th><th scope="col" className="py-1 text-right font-normal">Min</th><th scope="col" className="py-1 text-right font-normal">Games</th></tr>
        </thead>
        <tbody>
          {data.teammates.map((t) => (
            <tr key={t.player_id} className="border-t border-line">
              <th scope="row" className="py-1.5 text-left font-normal"><Link href={`/players/${t.player_id}/stats`} className="hover:underline">{t.name}</Link></th>
              <td className="py-1.5 text-right text-muted">{f(t.with_player.pts)}</td>
              <td className="py-1.5 text-right font-semibold">{f(t.without.pts)} <span className={`text-xs ${t.pts_diff != null && t.pts_diff > 0 ? "text-win" : "text-live"}`}>{signed(t.pts_diff)}</span></td>
              <td className="py-1.5 text-right text-muted">{f(t.without.min)} <span className="text-xs">{signed(t.min_diff)}</span></td>
              <td className="py-1.5 text-right text-xs text-muted">{t.without.games}{t.small_sample ? <span title="Small sample"> *</span> : null}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-muted">Games without him are mostly injuries and rest days, so the lineup around him was not always the same. * means fewer than 5 games.</p>
    </div>
  );
}

/** "If he is out": opens on demand, and only then loads the numbers. */
export function WithoutPanel({ playerId, name, status }: { playerId: number; name: string; status: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-lg border border-line bg-surface">
      <button type="button" aria-expanded={open} onClick={() => setOpen((o) => !o)} className="flex min-h-11 w-full items-center justify-between gap-2 px-3 text-left text-sm">
        <span><b>{name}</b> is {status.toLowerCase()}: who steps up?</span><span aria-hidden className="text-muted">{open ? "▴" : "▾"}</span>
      </button>
      {open && <div className="px-3 pb-3"><Body id={playerId} /></div>}
    </div>
  );
}
