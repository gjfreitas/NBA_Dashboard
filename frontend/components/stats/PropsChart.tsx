"use client";
import { useEffect, useRef } from "react";
import type { PropGame, PropNextGame } from "@/lib/types";
import { TeamLogo } from "../Logo";

const COL = 44; // px per game column
const BAR_AREA = 224; // px height of the bar area

const shortSeason = (s: string) => `${s.slice(2, 4)}/${s.slice(5)}`; // 2025-26 -> 25/26
const shortDate = (d: string) => `${d.slice(5, 7)}/${d.slice(8)}`;

export interface Bar { game: PropGame; value: number }

/** One bar per game, green above the line and red at or below it. Binary markets show achieved / not achieved. */
export function PropsChart({ bars, line, binary, next, marketLabel }: {
  bars: Bar[]; line: number; binary: boolean; next: PropNextGame | null; marketLabel: string;
}) {
  // newest games are on the right; open the chart scrolled to them (matters on narrow screens)
  const scroller = useRef<HTMLDivElement>(null);
  const lastId = bars.length ? bars[bars.length - 1].game.game_id : "";
  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollLeft = el.scrollWidth;
  }, [lastId, bars.length]);

  if (!bars.length)
    return <p className="rounded-lg border border-dashed border-line p-8 text-center text-sm text-muted">No games match these filters.</p>;
  const max = binary ? 1 : Math.max(line, ...bars.map((b) => b.value), 1) * 1.12;
  const hit = (v: number) => (binary ? v >= 1 : v > line);
  const lineBottom = (line / max) * BAR_AREA;
  const width = (bars.length + (next ? 1 : 0)) * COL;

  return (
    <figure className="rounded-lg border border-line bg-surface p-3">
      <div ref={scroller} className="overflow-x-auto pb-2" tabIndex={0} role="group" aria-label={`${marketLabel} by game, oldest to newest`}>
        <div className="relative" style={{ width }}>
          {/* bars */}
          <div className="relative flex items-end" style={{ height: BAR_AREA }}>
            {bars.map(({ game: g, value }, i) => {
              const newSeason = i > 0 && bars[i - 1].game.season !== g.season;
              const over = hit(value);
              const h = binary ? (over ? BAR_AREA : 26) : Math.max((value / max) * BAR_AREA, 22);
              return (
                <div key={g.game_id} className={`relative flex shrink-0 justify-center ${newSeason ? "border-l border-dashed border-line" : ""}`}
                  style={{ width: COL, height: BAR_AREA }}
                  title={`${g.date} ${g.home ? "vs" : "@"} ${g.opp_abbr}${g.result ? ` (${g.result})` : ""}: ${binary ? (over ? "yes" : "no") : value} · ${Math.round(g.min)} min`}>
                  {(i === 0 || newSeason) && <span className="absolute left-1 top-0 text-[10px] font-semibold text-muted">{shortSeason(g.season)}</span>}
                  <div className="num flex items-end justify-center self-end rounded-t pb-1 text-xs font-bold text-white"
                    style={{ width: 32, height: h, background: over ? "var(--win-strong)" : "var(--live-strong)" }}>
                    {binary ? (over ? "✓" : "✗") : value}
                  </div>
                </div>
              );
            })}
            {next && (
              <div className="flex shrink-0 justify-center" style={{ width: COL, height: BAR_AREA }}>
                <div className="grid h-14 w-8 place-items-center self-end rounded border-2 border-dashed border-muted text-sm font-bold text-muted"
                  title={`Next: ${next.home ? "vs" : "@"} ${next.opp_abbr}, ${next.date}`}>?</div>
              </div>
            )}
            {!binary && (
              <div className="pointer-events-none absolute left-0 right-0 border-t-2 border-dashed" style={{ bottom: lineBottom, borderColor: "var(--line-color)" }}>
                <span className="num absolute -top-5 left-0 rounded bg-surface2 px-1.5 text-xs font-semibold" style={{ color: "var(--line-color)" }}>{line}</span>
              </div>
            )}
          </div>
          {/* opponent + date labels */}
          <div className="mt-1 flex">
            {bars.map(({ game: g }) => (
              <div key={g.game_id} className="flex shrink-0 flex-col items-center gap-0.5 text-center text-[10px] leading-tight text-muted" style={{ width: COL }}>
                {g.opp_id ? <TeamLogo id={g.opp_id} tricode={g.opp_abbr} size={22} /> : <span className="grid size-[22px] place-items-center rounded-full bg-surface2 text-[8px] font-bold">{g.opp_abbr}</span>}
                <span className="num">{shortDate(g.date)}</span>
                <span className="font-medium">{g.home ? "" : "@"}{g.opp_abbr}</span>
              </div>
            ))}
            {next && (
              <div className="flex shrink-0 flex-col items-center gap-0.5 text-center text-[10px] leading-tight text-muted" style={{ width: COL }}>
                <TeamLogo id={next.opp_id} tricode={next.opp_abbr} size={22} />
                <span className="num">{shortDate(next.date)}</span>
                <span className="font-medium">{next.home ? "" : "@"}{next.opp_abbr}</span>
              </div>
            )}
          </div>
        </div>
      </div>
      <figcaption className="mt-2 flex flex-wrap items-center justify-center gap-x-5 gap-y-1 text-xs text-muted">
        <span><span className="mr-1 inline-block size-2.5 rounded-sm align-middle" style={{ background: "var(--win-strong)" }} />{binary ? "Achieved" : "Over the line"}</span>
        <span><span className="mr-1 inline-block size-2.5 rounded-sm align-middle" style={{ background: "var(--live-strong)" }} />{binary ? "Not achieved" : "Under the line"}</span>
        {!binary && <span><span className="mr-1 inline-block w-4 border-t-2 border-dashed align-middle" style={{ borderColor: "var(--line-color)" }} />Line</span>}
        <span>? next game</span>
      </figcaption>

      <details className="mt-2 text-xs text-muted">
        <summary className="min-h-8 cursor-pointer">View as table</summary>
        <div className="mt-2 max-h-64 overflow-auto">
          <table className="num w-full border-collapse text-sm text-fg">
            <caption className="sr-only">{marketLabel} by game</caption>
            <thead><tr className="text-left text-xs text-muted"><th className="py-1 pr-3 font-medium">Date</th><th className="pr-3 font-medium">Opp</th><th className="pr-3 font-medium">{marketLabel}</th><th className="font-medium">Result</th></tr></thead>
            <tbody>
              {[...bars].reverse().map(({ game: g, value }) => (
                <tr key={g.game_id} className="border-t border-line">
                  <td className="py-1 pr-3">{g.date}</td><td className="pr-3">{g.home ? "vs" : "@"} {g.opp_abbr}</td>
                  <td className="pr-3">{binary ? (value >= 1 ? "Yes" : "No") : value}</td><td>{hit(value) ? (binary ? "Achieved" : "Over") : binary ? "Not achieved" : "Under"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}
