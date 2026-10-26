import type { Game } from "./types";

export const periodLabel = (p: number) => (p <= 4 ? `Q${p}` : p === 5 ? "OT" : `${p - 4}OT`);

export function statusLabel(g: Game): string {
  if (g.state === "live") return `${periodLabel(g.period)} ${g.clock}`.trim();
  if (g.state === "final") return g.period > 4 ? `Final/${periodLabel(g.period)}` : "Final";
  return g.start_utc
    ? new Date(g.start_utc).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
    : g.status_text;
}

export const record = (t: { wins: number | null; losses: number | null }) =>
  t.wins == null ? "" : `${t.wins}-${t.losses}`;

export const logoUrl = (teamId: number) => `https://cdn.nba.com/logos/nba/${teamId}/primary/L/logo.svg`;
