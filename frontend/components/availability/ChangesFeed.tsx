"use client";
import Link from "next/link";
import { changeText, reportTimeText, sortChanges } from "@/lib/availability";
import { usePolling } from "@/lib/hooks";
import type { InjuryChange, InjuryChanges } from "@/lib/types";
import { StatusPill } from "./StatusPill";

const ICON: Record<InjuryChange["kind"], { mark: string; label: string; tone: string }> = {
  worsened: { mark: "▲", label: "Got worse", tone: "text-live" },
  added: { mark: "＋", label: "Added", tone: "text-live" },
  improved: { mark: "▼", label: "Improved", tone: "text-win" },
  removed: { mark: "－", label: "Removed", tone: "text-win" },
};

/** What changed since the previous official report. `gameId` / `teamId` narrow it; `limit` caps the rows (the Injuries page shows all). */
export function ChangesFeed({ gameId, teamId, playerIds, teamIds, limit, hours = 24, heading = "Changes since the last report" }: {
  gameId?: string; teamId?: number; limit?: number; hours?: number; heading?: string | null;
  /** Only changes for these players, or players of these teams (the watchlist). */
  playerIds?: Set<number>; teamIds?: Set<number>;
}) {
  const qs = new URLSearchParams({ hours: String(hours) });
  if (gameId) qs.set("game_id", gameId);
  if (teamId) qs.set("team_id", String(teamId));
  const { data } = usePolling<InjuryChanges>(`/api/injuries/changes?${qs}`, 2 * 60_000);
  if (!data) return null;
  const scoped = !!(playerIds || teamIds);
  const mine = scoped ? data.changes.filter((c) => (c.player_id != null && playerIds?.has(c.player_id)) || (c.team_id != null && teamIds?.has(c.team_id))) : data.changes;
  const rows = sortChanges(mine).slice(0, limit);
  // Nothing to say, and nothing to compare against yet, is not worth a box on a game page.
  if (!rows.length && (gameId || teamId)) return null;
  return (
    <section aria-label="Injury report changes" className="rounded-lg border border-line bg-surface p-3">
      {heading && <h2 className="mb-1 text-sm font-semibold">{heading}</h2>}
      {rows.length === 0 ? (
        <p className="text-sm text-muted">
          {data.reports_compared < 2
            ? "Not enough reports stored yet to compare."
            : scoped ? `None of your followed players or teams changed in the last ${hours} hours.`
            : `No changes in the last ${hours} hours: the ${data.reports_compared} reports in that time list the same players with the same statuses. Teams update their entries as game time nears.`}
        </p>
      ) : (
        <ul className="divide-y divide-line">
          {rows.map((c, i) => (
            <li key={`${c.report_id}-${c.player_id ?? c.name}-${i}`} className="flex items-start gap-2 py-1.5 text-sm">
              <span aria-hidden className={`mt-0.5 w-4 shrink-0 text-center text-xs ${ICON[c.kind].tone}`}>{ICON[c.kind].mark}</span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <span className="sr-only">{ICON[c.kind].label}: </span>
                  {c.player_id ? <Link href={`/players/${c.player_id}/stats`} className="font-medium hover:underline">{c.name}</Link> : <span className="font-medium">{c.name}</span>}
                  {c.team_abbr && <span className="text-xs text-muted">{c.team_abbr}</span>}
                  {c.kind === "worsened" || c.kind === "improved" ? (
                    <span className="flex items-center gap-1" aria-label={changeText(c)}>
                      <StatusPill status={c.from_status!} className="opacity-60" /><span aria-hidden>→</span><StatusPill status={c.to_status!} />
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-xs text-muted">
                      {c.kind === "added" ? "Added" : "Removed"} {c.kind === "added" ? <StatusPill status={c.to_status!} /> : <>(was <StatusPill status={c.from_status!} className="opacity-60" />)</>}
                    </span>
                  )}
                </div>
                <div className="text-xs text-muted">
                  {c.reason}{c.reason ? " · " : ""}{reportTimeText(c.at)}
                  {!gameId && c.game_id && <> · <Link href={`/games/${c.game_id}/preview`} className="underline hover:text-fg">{c.matchup?.replace("@", " @ ")}</Link></>}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
