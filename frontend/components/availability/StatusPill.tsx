import { STATUS_MEANING } from "@/lib/availability";
import type { InjuryStatus } from "@/lib/types";

// White text on each of these is >= 4.5:1; the word is always shown, so colour never carries the meaning alone.
const BG: Record<InjuryStatus, string> = {
  Out: "var(--live-strong)", Doubtful: "#c2410c", Questionable: "#a16207", Probable: "#4d7c0f", Available: "var(--win-strong)",
};

export function StatusPill({ status, className = "" }: { status: string; className?: string }) {
  const known = status in BG;
  return (
    <span title={known ? STATUS_MEANING[status as InjuryStatus] : undefined}
      className={`inline-block shrink-0 rounded px-1.5 py-0.5 text-center text-xs font-bold text-white ${className}`}
      style={{ background: known ? BG[status as InjuryStatus] : "var(--muted)" }}>
      {status}
    </span>
  );
}
