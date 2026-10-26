"use client";
import Link from "next/link";
import { useFetch } from "@/lib/hooks";
import type { Roster } from "@/lib/types";
import { Headshot } from "./Headshot";
import { useTeam } from "./TeamProvider";

export function TeamRoster() {
  const { id } = useTeam();
  const { data, loading, notFound } = useFetch<Roster>(`/api/teams/${id}/roster`);
  if (loading) return <div className="h-64 skeleton rounded-lg bg-surface" aria-busy />;
  if (notFound || !data)
    return <p className="rounded-lg border border-dashed border-line p-6 text-sm text-muted">Roster isn’t loaded yet.</p>;
  const td = "px-2 py-2 text-right";
  return (
    <section aria-label="Roster" className="space-y-2">
      <div className="overflow-x-auto rounded-lg border border-line bg-surface">
        <table className="num w-full min-w-[480px] border-collapse text-sm">
          <caption className="border-b border-line px-3 py-2 text-left text-xs text-muted">
            Players who appeared for this team in {data.season}, most minutes first. Per-game averages.
          </caption>
          <thead>
            <tr className="border-b border-line text-xs text-muted">
              <th scope="col" className="sticky left-0 bg-surface px-3 py-2 text-left font-medium">Player</th>
              {["GP", "MPG", "PPG", "RPG", "APG"].map((h) => <th key={h} scope="col" className="px-2 py-2 text-right font-medium">{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {data.players.map((p) => (
              <tr key={p.player_id} className="border-b border-line last:border-0">
                <th scope="row" className="sticky left-0 whitespace-nowrap bg-surface px-3 py-1.5 text-left font-medium">
                  <Link href={`/players/${p.player_id}`} className="inline-flex min-h-10 items-center gap-2 hover:underline">
                    <Headshot id={p.player_id} name={p.name} width={40} />
                    <span>{p.name}{p.position && <span className="ml-1.5 text-xs font-normal text-muted">{p.position}</span>}</span>
                  </Link>
                </th>
                <td className={td}>{p.gp}</td><td className={td}>{p.min.toFixed(1)}</td>
                <td className={`${td} font-semibold`}>{p.pts.toFixed(1)}</td>
                <td className={td}>{p.reb.toFixed(1)}</td><td className={td}>{p.ast.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
