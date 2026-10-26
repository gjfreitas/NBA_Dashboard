import { memo } from "react";
import type { Shot } from "@/lib/types";

export type ShotFilter = "all" | "made" | "missed";
type Dot = Pick<Shot, "x" | "y" | "made">;

/** Half court in NBA shot-chart units (1 = 1/10 ft). Origin at the rim; +y toward half court. */
const Court = memo(function Court() {
  const line = { fill: "none", stroke: "var(--muted)", strokeWidth: 2, opacity: 0.6 } as const;
  const threeArcY = Math.sqrt(237.5 ** 2 - 220 ** 2); // where the arc meets the corner-three lines
  return (
    <g>
      <rect x={-250} y={-47.5} width={500} height={470} {...line} />
      <rect x={-80} y={-47.5} width={160} height={190} {...line} />
      <rect x={-60} y={-47.5} width={120} height={190} {...line} />
      <circle cx={0} cy={142.5} r={60} {...line} />
      <path d="M -40 0 A 40 40 0 0 0 40 0" {...line} />
      <line x1={-30} x2={30} y1={-7.5} y2={-7.5} {...line} strokeWidth={3} />
      <circle cx={0} cy={0} r={7.5} {...line} stroke="var(--accent)" opacity={1} />
      <path d={`M -220 -47.5 L -220 ${threeArcY} A 237.5 237.5 0 0 0 220 ${threeArcY} L 220 -47.5`} {...line} />
    </g>
  );
});

const Shots = memo(function Shots({ shots, show }: { shots: Dot[]; show: ShotFilter }) {
  return (
    <g>
      {shots.map((s, i) => {
        if (s.made ? show === "missed" : show === "made") return null;
        return s.made ? (
          <circle key={i} className="shot-in" style={{ "--i": i } as React.CSSProperties} cx={s.x} cy={s.y} r={6} fill="var(--win)" opacity={0.75} />
        ) : (
          <g key={i} transform={`translate(${s.x} ${s.y})`}><path className="shot-in" style={{ "--i": i } as React.CSSProperties} d="M -4.5 -4.5 L 4.5 4.5 M -4.5 4.5 L 4.5 -4.5"
            stroke="var(--live)" strokeWidth={2} opacity={0.7} /></g>
        );
      })}
    </g>
  );
});

/** Half court with shots plotted. Made = filled circle, missed = cross (shape, not just colour, carries meaning). */
export function ShotCourt({ shots, show = "all", label, className = "mx-auto w-full max-w-xl" }: {
  shots: Dot[]; show?: ShotFilter; label: string; className?: string;
}) {
  return (
    <svg viewBox="-260 -67.5 520 490" className={className} role="img" aria-label={label}>
      <g transform="translate(0 365) scale(1 -1)">
        <Court />
        <Shots shots={shots} show={show} />
      </g>
    </svg>
  );
}
