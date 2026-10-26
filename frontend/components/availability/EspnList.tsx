import Link from "next/link";
import { ESPN_NOTE, espnStatusText, returnText } from "@/lib/availability";
import type { EspnInjury } from "@/lib/types";

/** ESPN's status. Dashed outline (not the official pills' solid colours) so the two sources are never confused. */
export function EspnTag({ status, className = "" }: { status: string; className?: string }) {
  return (
    <span title={ESPN_NOTE} className={`inline-block shrink-0 rounded border border-dashed border-muted px-1.5 py-0.5 text-center text-xs font-bold text-muted ${className}`}>
      <span className="sr-only">ESPN: </span>{espnStatusText(status)}
    </span>
  );
}

export function SourceLabel({ children = "ESPN, unofficial" }: { children?: string }) {
  return <span title={ESPN_NOTE} className="rounded-full border border-dashed border-muted px-2 py-0.5 text-[11px] font-semibold text-muted">{children}</span>;
}

/** Injured players from ESPN's list who are not on the official NBA report. Always labelled as ESPN. */
export function EspnList({ entries, showTeam = false }: { entries: EspnInjury[]; showTeam?: boolean }) {
  return (
    <ul className="divide-y divide-line">
      {entries.map((e) => {
        const back = returnText(e.return_date);
        return (
          <li key={`${e.player_id ?? e.name}-${e.team_abbr}`} className="flex items-start gap-2 py-1.5 text-sm">
            <EspnTag status={e.status} className="mt-0.5 w-24" />
            <div className="min-w-0 flex-1">
              {e.player_id ? <Link href={`/players/${e.player_id}/stats`} className="font-medium hover:underline">{e.name}</Link> : <span className="font-medium">{e.name}</span>}
              {showTeam && e.team_abbr && <span className="ml-1.5 text-xs text-muted">{e.team_abbr}</span>}
              <div className="text-xs text-muted">{e.injury}{back ? ` · ESPN est. return ${back}` : ""}</div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
