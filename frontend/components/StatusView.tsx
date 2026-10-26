"use client";
import { ageText } from "@/lib/availability";
import { usePolling } from "@/lib/hooks";
import type { Health, HealthItem } from "@/lib/types";

const TONE: Record<HealthItem["status"], { dot: string; label: string }> = {
  ok: { dot: "bg-win", label: "Up to date" },
  stale: { dot: "bg-[#a16207]", label: "Out of date" },
  error: { dot: "bg-live", label: "Failing" },
  never: { dot: "bg-muted", label: "No data yet" },
};

const limitText = (m: number) => (m >= 120 ? `${Math.round(m / 60)} h` : `${m} min`);

export function StatusView() {
  const { data, loading, error } = usePolling<Health>("/api/health", 30_000);
  if (loading && !data) return <div className="h-64 skeleton rounded-lg bg-surface" aria-busy />;
  if (!data) return <p role="alert" className="text-muted">Can’t reach the data service{error ? ` (${error})` : ""}.</p>;
  const headline = data.status === "ok" ? "All data sources are up to date." : data.status === "degraded" ? "Some data is out of date." : "Most data sources are out of date or failing.";
  return (
    <div className="space-y-3">
      <p role="status" className={`rounded-lg border p-3 text-sm font-medium ${data.status === "ok" ? "border-win" : "border-live"}`}>{headline}</p>
      <ul className="divide-y divide-line rounded-lg border border-line bg-surface">
        {data.items.map((i) => (
          <li key={i.key} className="flex items-start gap-3 p-3">
            <span aria-hidden className={`mt-1.5 size-2.5 shrink-0 rounded-full ${TONE[i.status].dot}`} />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                <h2 className="text-sm font-semibold">{i.label}</h2>
                <span className="text-xs font-medium">{TONE[i.status].label}</span>
              </div>
              <p className="text-xs text-muted">
                {i.age_minutes == null ? "Never reached." : `Last reached ${ageText(i.age_minutes)}`} (expected at least every {limitText(i.max_age_minutes)}). {i.detail}
              </p>
              {i.last_error && (
                <p className="mt-0.5 break-words text-xs text-muted">Last error{i.last_error_at ? `, ${new Date(i.last_error_at).toLocaleString()}` : ""}: <code>{i.last_error}</code></p>
              )}
            </div>
          </li>
        ))}
      </ul>
      <p className="text-xs text-muted">
        Player profiles loaded: {data.coverage.players_loaded} of {data.coverage.players_active} active players
        {data.coverage.latest_game_date ? ` · latest game stored: ${data.coverage.latest_game_date}` : ""} · {data.coverage.injury_reports_stored} injury reports stored.
      </p>
    </div>
  );
}
