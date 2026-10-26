"use client";
import { InfoTip } from "../InfoTip";
import Link from "next/link";
import { ageText, reportTimeText } from "@/lib/availability";
import { usePolling } from "@/lib/hooks";
import type { GameAvailability, GameAvailabilitySummary, TeamAvailability } from "@/lib/types";
import { TeamLogo } from "../Logo";
import { WithoutPanel } from "./WithoutPanel";
import { ChangesFeed } from "./ChangesFeed";
import { EspnList, SourceLabel } from "./EspnList";
import { InjuryList } from "./InjuryList";
import { StatusPill } from "./StatusPill";

function LineupBadge({ status }: { status: TeamAvailability["lineup_status"] }) {
  if (!status) return <span className="text-xs text-muted">Lineup not published yet</span>;
  const confirmed = status === "Confirmed";
  return (
    <span className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${confirmed ? "border-win text-win" : "border-line text-muted"}`}
      title={confirmed ? "The team has confirmed this starting five" : "Projected by the NBA; the team can still change it"}>
      {confirmed ? "✓ Confirmed" : "Expected"}
    </span>
  );
}

function Side({ t, stars }: { t: TeamAvailability; stars: GameAvailabilitySummary["home"]["key_players"] }) {
  return (
    <section aria-label={`${t.name} availability`} className="rounded-lg border border-line bg-surface p-3">
      <div className="mb-2 flex items-center gap-2">
        <TeamLogo id={t.team_id} tricode={t.abbr ?? ""} size={28} />
        <h3 className="flex-1 truncate font-semibold">{t.name}</h3>
        <LineupBadge status={t.lineup_status} />
      </div>

      <h4 className="mb-1 text-xs font-medium text-muted">Starting five</h4>
      {t.starters.length ? (
        <ol className="mb-3 divide-y divide-line">
          {t.starters.map((s) => (
            <li key={s.player_id} className="flex items-center gap-2 py-1.5 text-sm">
              <span className="w-8 shrink-0 text-xs font-semibold text-muted">{s.position}</span>
              <Link href={`/players/${s.player_id}/stats`} className="min-w-0 flex-1 truncate font-medium hover:underline">{s.name}</Link>
              {s.injury_status && <StatusPill status={s.injury_status} />}
            </li>
          ))}
        </ol>
      ) : <p className="mb-3 text-sm text-muted">The NBA hasn’t published a lineup for this game yet.</p>}

      <h4 className="mb-1 text-xs font-medium text-muted">Injury report</h4>
      <InjuryList entries={t.injuries}
        empty={t.report_pending ? "Hasn’t filed its injury report yet." : "No players on the injury report."} />
      {t.report_pending && t.injuries.length > 0 && <p className="mt-1 text-xs text-muted">This list may be incomplete: the team hasn’t filed for this game yet.</p>}
      {stars.filter((k) => k.player_id != null && (k.status === "Out" || k.status === "Doubtful")).length > 0 && (
        <div className="mt-3 space-y-2">
          {stars.filter((k) => k.player_id != null && (k.status === "Out" || k.status === "Doubtful")).map((k) => (
            <WithoutPanel key={k.player_id} playerId={k.player_id as number} name={k.name} status={k.status} />
          ))}
        </div>
      )}
      {!!t.espn_only?.length && (
        <div className="mt-3">
          <h4 className="mb-1 flex items-center gap-2 text-xs font-medium text-muted">Also injured per ESPN <SourceLabel /></h4>
          <EspnList entries={t.espn_only} />
        </div>
      )}
    </section>
  );
}

/** Starters and injuries for both teams of a game. Refreshes every minute: lineups change before tip-off. */
export function AvailabilityPanel({ gameId }: { gameId: string }) {
  const { data, loading, notFound } = usePolling<GameAvailability>(`/api/games/${gameId}/availability`, 60_000);
  const { data: sums } = usePolling<GameAvailabilitySummary[]>(`/api/availability/summary?game_ids=${gameId}`, 5 * 60_000);
  const sum = sums?.[0];
  if (loading && !data) return <div className="h-48 skeleton rounded-lg bg-surface" aria-busy />;
  if (notFound || !data) return null; // a game that isn't in the schedule has nothing to show
  const r = data.report;
  return (
    <div className="space-y-2">
      <ChangesFeed gameId={gameId} heading="Changed since the previous injury report" />
      <div className="grid gap-3 md:grid-cols-2">
        <Side t={data.away} stars={sum?.away.key_players ?? []} />
        <Side t={data.home} stars={sum?.home.key_players ?? []} />
      </div>
      <p className="flex items-center gap-2 text-xs text-muted" role="status">
        {r ? <>Official NBA injury report from {reportTimeText(r.published_at)} ({ageText(r.age_minutes)}){r.stale ? ". Old: the NBA files a new one on game days." : "."}</> : "No NBA injury report stored yet."}
        <InfoTip label="About lineups and injuries">Lineups are the NBA’s projected or confirmed starters; the injury report is filed by the teams every 15 minutes on game days.</InfoTip>
      </p>
    </div>
  );
}
