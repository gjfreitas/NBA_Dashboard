"use client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { returnText, shortReason, surname } from "@/lib/availability";
import { usePolling } from "@/lib/hooks";
import type { InjuryReport } from "@/lib/types";
import { useAlertStore } from "@/lib/useAlerts";
import { useWatchlist } from "@/lib/useWatchlist";
import { idsOf } from "@/lib/watchlist";
import { ChangesFeed } from "../availability/ChangesFeed";
import { EspnTag } from "../availability/EspnList";
import { StatusPill } from "../availability/StatusPill";
import { Headshot } from "../Headshot";
import { TeamLogo } from "../Logo";
import { WatchButton } from "../WatchButton";

/** Followed players and teams, with their injury status from the newest official report (ESPN's list where the report has nothing). */
export function WatchlistView() {
  const { list } = useWatchlist();
  const alerts = useAlertStore();
  const [perm, setPerm] = useState<NotificationPermission | "unsupported">(() => (typeof Notification === "undefined" ? "unsupported" : Notification.permission));
  useEffect(() => { // the list is visible, so what it holds counts as read once the page has been opened
    const t = setTimeout(alerts.read, 1500);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once per visit
  }, []);
  const { data } = usePolling<InjuryReport>("/api/injuries", 5 * 60_000);
  const players = list.items.filter((i) => i.kind === "player");
  const teams = list.items.filter((i) => i.kind === "team");
  const playerIds = useMemo(() => idsOf(list, "player"), [list]);
  const teamIds = useMemo(() => idsOf(list, "team"), [list]);
  const official = useMemo(() => new Map((data?.entries ?? []).filter((e) => e.player_id != null).map((e) => [e.player_id!, e])), [data]);
  const espn = useMemo(() => new Map((data?.espn ?? []).filter((e) => e.player_id != null).map((e) => [e.player_id!, e])), [data]);

  if (!list.items.length)
    return (
      <p className="rounded-lg border border-dashed border-line p-6 text-sm text-muted">
        You aren’t following anyone yet. Press <b className="text-fg">☆ Follow</b> on a player or team page, or use <b className="text-fg">Search</b> (Ctrl K) to find one.
        Your list is saved in this browser only.
      </p>
    );

  return (
    <div className="space-y-4">
      <section aria-label="Alerts" className="rounded-lg border border-line bg-surface p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold">Alerts</h2>
          <div className="flex gap-2">
            {perm === "default" && (
              <button type="button" className="min-h-11 rounded-lg border border-line px-3 text-xs hover:bg-surface2"
                onClick={() => Notification.requestPermission().then(setPerm)}>Turn on browser notifications</button>
            )}
            {alerts.state.items.length > 0 && <button type="button" className="min-h-11 rounded-lg border border-line px-3 text-xs hover:bg-surface2" onClick={alerts.clear}>Clear</button>}
          </div>
        </div>
        {alerts.state.items.length === 0 ? (
          <p className="mt-1 text-xs text-muted">
            Nothing new. While this site is open in a browser tab, it checks every couple of minutes for injury-report changes and prop-line moves of a point or more for the players and teams you follow.
            {perm === "denied" ? " Browser notifications are blocked for this site." : ""}
          </p>
        ) : (
          <ul className="mt-1 divide-y divide-line">
            {alerts.state.items.map((a) => (
              <li key={a.key} className="py-1.5 text-sm">
                <Link href={a.href} className="hover:underline"><span aria-hidden>{a.kind === "injury" ? "✚" : "↕"}</span> <span className="sr-only">{a.kind === "injury" ? "Injury report: " : "Line move: "}</span>{a.text}</Link>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-1 text-xs text-muted">Alerts only arrive while the site is open; nothing runs in the background after you close the tab.</p>
      </section>

      {players.length > 0 && (
        <section aria-label="Followed players" className="space-y-2">
          <h2 className="text-sm font-semibold">Players</h2>
          <ul className="grid gap-2 sm:grid-cols-2">
            {players.map((p) => {
              const o = official.get(p.id), e = espn.get(p.id);
              return (
                <li key={p.id} className="flex items-center gap-3 rounded-lg border border-line bg-surface p-2">
                  <Headshot id={p.id} name={p.name} width={56} />
                  <div className="min-w-0 flex-1">
                    <Link href={`/players/${p.id}`} className="block truncate font-medium hover:underline">{p.name}</Link>
                    <div className="flex items-center gap-2 text-xs text-muted">
                      {o ? <><StatusPill status={o.status} /><span className="truncate">{shortReason(o.reason)}{o.espn_return_date ? ` · ESPN est. return ${returnText(o.espn_return_date)}` : ""}</span></>
                        : e ? <><EspnTag status={e.status} /><span className="truncate">{e.injury}{e.return_date ? ` · ESPN est. return ${returnText(e.return_date)}` : ""}</span></>
                        : <span>{data ? "Not on an injury report" : p.sub ?? ""}</span>}
                    </div>
                  </div>
                  <WatchButton item={p} />
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {teams.length > 0 && (
        <section aria-label="Followed teams" className="space-y-2">
          <h2 className="text-sm font-semibold">Teams</h2>
          <ul className="grid gap-2 sm:grid-cols-2">
            {teams.map((t) => {
              const hurt = (data?.entries ?? []).filter((e) => e.team_id === t.id && (e.status === "Out" || e.status === "Doubtful" || e.status === "Questionable"));
              const names = hurt.slice(0, 3).map((h) => `${surname(h.name)} ${h.status.toLowerCase()}`).join(", ");
              return (
                <li key={t.id} className="flex items-center gap-3 rounded-lg border border-line bg-surface p-2">
                  <TeamLogo id={t.id} tricode={t.sub ?? ""} size={40} />
                  <div className="min-w-0 flex-1">
                    <Link href={`/teams/${t.id}`} className="block truncate font-medium hover:underline">{t.name}</Link>
                    <p className="truncate text-xs text-muted">
                      {data ? (hurt.length ? `${hurt.length} on the injury report: ${names}${hurt.length > 3 ? "…" : ""}` : "None Out, Doubtful or Questionable on the official report") : ""}
                    </p>
                  </div>
                  <WatchButton item={t} />
                </li>
              );
            })}
          </ul>
        </section>
      )}

      <ChangesFeed playerIds={playerIds} teamIds={teamIds} hours={48} heading="Changes for your players and teams" />
    </div>
  );
}
