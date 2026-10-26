"use client";
import { useState } from "react";
import { useFetch } from "@/lib/hooks";
import type { ShotChart } from "@/lib/types";
import { pct } from "./PlayerOverview";
import { usePlayer } from "./PlayerProvider";
import { SeasonPicker, useDefaultSelection, type Selection } from "./SeasonPicker";
import { ShotCourt, type ShotFilter } from "./ShotCourt";

export function ShotChartView() {
  const { data: p, id } = usePlayer();
  const [picked, setPicked] = useState<Selection | null>(null);
  const [show, setShow] = useState<ShotFilter>("all");
  const avail = p?.available.filter((a) => a.shots > 0) ?? [];
  const sel = useDefaultSelection(avail, picked);
  const { data, loading } = useFetch<ShotChart>(sel ? `/api/players/${id}/shots?season=${sel.season}&season_type=${sel.type}` : null);
  if (!p) return <div className="h-64 skeleton rounded-lg bg-surface" aria-busy />;
  if (!sel) return <p className="rounded-lg border border-dashed border-line p-6 text-sm text-muted">No shot data loaded for this player yet.</p>;
  const chip = (on: boolean) => `min-h-11 rounded-full border px-4 text-sm ${on ? "border-accent bg-surface2 font-semibold" : "border-line text-muted hover:text-fg"}`;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <SeasonPicker available={avail} value={sel} onChange={setPicked} count="shots" />
        <div role="group" aria-label="Show shots" className="flex gap-2">
          {(["all", "made", "missed"] as const).map((v) => (
            <button key={v} className={chip(show === v)} aria-pressed={show === v} onClick={() => setShow(v)}>
              {v === "all" ? "All" : v === "made" ? "Made" : "Missed"}
            </button>
          ))}
        </div>
      </div>
      {loading || !data ? <div className="h-96 skeleton rounded-lg bg-surface" aria-busy /> : (
        <div className="grid gap-3 md:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
          <figure className="rounded-lg border border-line bg-surface p-2">
            <ShotCourt shots={data.shots} show={show}
              label={`Shot chart: ${data.made} of ${data.attempts} field goals made, ${pct(data.fg_pct)} percent`} />
            <figcaption className="mt-1 flex flex-wrap items-center justify-center gap-x-4 text-xs text-muted">
              <span><span className="font-semibold text-win">●</span> Made</span>
              <span><span className="font-semibold text-live">✕</span> Missed</span>
              <span className="num">{data.made}/{data.attempts} FG · {pct(data.fg_pct)}%</span>
            </figcaption>
          </figure>
          <div className="overflow-x-auto rounded-lg border border-line bg-surface">
            <table className="num w-full border-collapse text-sm">
              <caption className="sr-only">Shooting by zone</caption>
              <thead>
                <tr className="border-b border-line text-xs text-muted">
                  <th scope="col" className="px-3 py-2 text-left font-medium">Zone</th>
                  <th scope="col" className="px-2 py-2 text-right font-medium">FGM-FGA</th>
                  <th scope="col" className="px-2 py-2 text-right font-medium">FG%</th>
                </tr>
              </thead>
              <tbody>
                {data.zones.map((z) => (
                  <tr key={z.zone} className="border-b border-line">
                    <th scope="row" className="px-3 py-2 text-left font-normal">{z.zone}</th>
                    <td className="px-2 py-2 text-right">{z.made}-{z.attempts}</td>
                    <td className="px-2 py-2 text-right font-semibold">{pct(z.fg_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
