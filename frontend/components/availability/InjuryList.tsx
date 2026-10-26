import Link from "next/link";
import { returnText, shortReason } from "@/lib/availability";
import type { InjuryOut } from "@/lib/types";
import { StatusPill } from "./StatusPill";

/** Players on the official injury report, most severe first. Matched players link to their stats page. */
export function InjuryList({ entries, empty = "No injuries reported.", showTeam = false }: { entries: InjuryOut[]; empty?: string; showTeam?: boolean }) {
  if (!entries.length) return <p className="text-sm text-muted">{empty}</p>;
  return (
    <ul className="divide-y divide-line">
      {entries.map((e, i) => (
        <li key={`${e.player_id ?? e.name}-${i}`} className="flex items-start gap-2 py-1.5 text-sm">
          <StatusPill status={e.status} className="mt-0.5 w-24" />
          <div className="min-w-0 flex-1">
            {e.player_id ? <Link href={`/players/${e.player_id}/stats`} className="font-medium hover:underline">{e.name}</Link> : <span className="font-medium">{e.name}</span>}
            {showTeam && e.team_abbr && <span className="ml-1.5 text-xs text-muted">{e.team_abbr}</span>}
            <div className="text-xs text-muted">{shortReason(e.reason)}{e.espn_return_date ? ` · ESPN est. return ${returnText(e.espn_return_date)}` : ""}</div>
          </div>
        </li>
      ))}
    </ul>
  );
}
