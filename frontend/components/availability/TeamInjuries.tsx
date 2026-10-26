"use client";
import { ageText } from "@/lib/availability";
import { usePolling } from "@/lib/hooks";
import type { InjuryReport } from "@/lib/types";
import { EspnList, SourceLabel } from "./EspnList";
import { InjuryList } from "./InjuryList";

/** A team's line on the newest official injury report (team page). */
export function TeamInjuries({ teamId }: { teamId: number }) {
  const { data, loading } = usePolling<InjuryReport>(`/api/injuries?team_id=${teamId}`, 5 * 60_000);
  if (loading && !data) return <div className="h-24 skeleton rounded-lg bg-surface" aria-busy />;
  const official = !!data?.report && !data.report.stale;
  const espn = data?.espn ?? [];
  if (!data || (!official && espn.length === 0)) return null; // nothing recent to show: say nothing rather than imply "healthy"
  const waiting = data.pending.length > 0;
  return (
    <section aria-label="Injury report" className="rounded-lg border border-line bg-surface p-3">
      <div className="mb-1 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold">Injury report</h2>
        {official && <span className="text-xs text-muted">NBA report, {ageText(data.report!.age_minutes)}</span>}
      </div>
      {official && <InjuryList entries={data.entries} empty={waiting ? "Hasn’t filed its next injury report yet." : "No players on the injury report."} />}
      {official && waiting && data.entries.length > 0 && <p className="mt-1 text-xs text-muted">Not yet filed for an upcoming game, so this may be incomplete.</p>}
      {espn.length > 0 && (
        <div className={official ? "mt-3" : ""}>
          <h3 className="mb-1 flex items-center gap-2 text-xs font-medium text-muted">Also injured per ESPN <SourceLabel /></h3>
          <EspnList entries={espn} />
        </div>
      )}
    </section>
  );
}
