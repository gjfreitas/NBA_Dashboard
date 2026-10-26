"use client";
import { InfoTip } from "./InfoTip";
import { useId, useMemo, useRef, useState } from "react";
import { gameVars } from "@/lib/teamColors";
import { flowPoints, type FlowPoint } from "@/lib/gameFlow";
import { periodLabel } from "@/lib/format";
import type { Game, Play } from "@/lib/types";

const W = 640, H = 160, PAD = 8;

/** The favoured side and its win probability at a point, e.g. "MIL 87%". */
function favourite(p: FlowPoint, game: Game): string {
  if (Math.abs(p.prob - 0.5) < 0.005) return "Even, 50%";
  const home = p.prob > 0.5;
  return `${home ? game.home.tricode : game.away.tricode} ${Math.round((home ? p.prob : 1 - p.prob) * 100)}%`;
}

/** Score margin over game time (up = home leads). Move the pointer, or use the arrow keys, to read the score and the estimated
 *  win probability at any moment. The probability uses only the score and the time left, so it is a rough guide. */
export function LeadTracker({ plays, game }: { plays: Play[]; game: Game }) {
  const pts = useMemo(() => flowPoints(plays), [plays]);
  const svg = useRef<SVGSVGElement>(null);
  const uid = useId().replace(/:/g, "");
  const [hover, setHover] = useState<number | null>(null); // index into pts

  if (pts.length < 2) return null;
  const maxT = Math.max(2880, ...pts.map((p) => p.t));
  const maxD = Math.max(8, ...pts.map((p) => Math.abs(p.lead)));
  const x = (t: number) => PAD + (t / maxT) * (W - 2 * PAD);
  const y = (d: number) => H / 2 - (d / maxD) * (H / 2 - PAD);
  const line = pts.map((p) => `${x(p.t).toFixed(1)},${y(p.lead).toFixed(1)}`).join(" ");
  const last = pts[pts.length - 1];
  const summary = last.lead === 0 ? "Tied" : `${last.lead > 0 ? game.home.tricode : game.away.tricode} leads by ${Math.abs(last.lead)}`;

  /** The state of the game at the pointer: the last scoring play at or before that moment. */
  const indexAt = (clientX: number): number | null => {
    const r = svg.current!.getBoundingClientRect();
    if (r.width === 0) return null; // not laid out (hidden): nothing to point at
    const t = ((clientX - r.left) / r.width * W - PAD) / (W - 2 * PAD) * maxT;
    let i = 0;
    while (i + 1 < pts.length && pts[i + 1].t <= t) i++;
    return i;
  };
  const shown = hover != null ? pts[Math.min(hover, pts.length - 1)] : null;
  const readout = shown
    ? `${shown.t === 0 ? "Tip-off" : `${periodLabel(shown.period)} ${shown.clock}`} · ${game.away.tricode} ${shown.away}, ${game.home.tricode} ${shown.home} · win probability ${favourite(shown, game)}`
    : summary;

  return (
    <figure className="rounded-lg border border-line bg-surface p-3" style={gameVars(game.away.tricode, game.home.tricode)}>
      <figcaption className="mb-1 flex flex-wrap justify-between gap-x-3 text-xs text-muted">
        <span className="flex items-center gap-2">Lead tracker
          <InfoTip label="About the win probability">Win probability uses only the score and the time left (not team strength, possession or fouls): a rough guide. Move over the line, or use the arrow keys, to read it at any moment.</InfoTip>
        </span>
        <span className={shown ? "font-semibold text-fg" : ""}>{readout}</span>
      </figcaption>
      <svg ref={svg} viewBox={`0 0 ${W} ${H}`} role="img" tabIndex={0} className="w-full touch-pan-y outline-offset-2"
        aria-label={`Lead tracker. ${summary}. Estimated win probability now ${favourite(last, game)}. Use the left and right arrow keys to move through the scoring plays.`}
        onPointerMove={(e) => setHover(indexAt(e.clientX))} onPointerDown={(e) => setHover(indexAt(e.clientX))}
        onPointerLeave={() => setHover(null)} onBlur={() => setHover(null)}
        onKeyDown={(e) => {
          if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
            e.preventDefault();
            setHover((h) => Math.max(0, Math.min(pts.length - 1, (h ?? pts.length - 1) + (e.key === "ArrowRight" ? 1 : -1))));
          } else if (e.key === "Escape") setHover(null);
        }}>
        <text x={PAD} y={12} fontSize="11" fill="var(--muted)">{game.home.tricode}</text>
        <text x={PAD} y={H - 4} fontSize="11" fill="var(--muted)">{game.away.tricode}</text>
        {[1, 2, 3].map((q) => <line key={q} x1={x(q * 720)} x2={x(q * 720)} y1={0} y2={H} stroke="var(--border)" strokeDasharray="3 3" />)}
        <line x1={0} x2={W} y1={H / 2} y2={H / 2} stroke="var(--border)" />
        <defs>
          <clipPath id={`${uid}-up`}><rect x="0" y="0" width={W} height={H / 2} /></clipPath>
          <clipPath id={`${uid}-dn`}><rect x="0" y={H / 2} width={W} height={H / 2} /></clipPath>
        </defs>
        {/* each team's colour fills the space its lead takes up, above the line for home and below for away */}
        <polygon points={`${x(0)},${H / 2} ${line} ${x(last.t)},${H / 2}`} clipPath={`url(#${uid}-up)`} fill="var(--h1)" opacity="0.32" />
        <polygon points={`${x(0)},${H / 2} ${line} ${x(last.t)},${H / 2}`} clipPath={`url(#${uid}-dn)`} fill="var(--a1)" opacity="0.32" />
        <polyline className="draw-line" pathLength={1} points={line} fill="none" stroke="var(--text)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        {shown && (
          <g pointerEvents="none">
            <line x1={x(shown.t)} x2={x(shown.t)} y1={0} y2={H} stroke="var(--muted)" strokeWidth="1" />
            <circle cx={x(shown.t)} cy={y(shown.lead)} r={4.5} fill="var(--accent)" stroke="var(--bg)" strokeWidth="2" />
          </g>
        )}
      </svg>
    </figure>
  );
}
