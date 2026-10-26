"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { returnText, shortReason } from "@/lib/availability";
import { EspnTag } from "./availability/EspnList";
import { StatusPill } from "./availability/StatusPill";
import { Headshot } from "./Headshot";
import { WatchButton } from "./WatchButton";
import { gameVars } from "@/lib/teamColors";
import { usePlayer } from "./PlayerProvider";
import { TabBar } from "./TabBar";

const TABS = [
  { slug: "", label: "Overview" },
  { slug: "stats", label: "Stats" },
  { slug: "game-log", label: "Game log" },
  { slug: "shot-chart", label: "Shot chart" },
];

export function PlayerHeader() {
  const { id, data: p, loading, notFound, error } = usePlayer();
  const path = usePathname();
  const tabs = TABS.map((t) => ({ href: `/players/${id}${t.slug ? `/${t.slug}` : ""}`, label: t.label }));
  if (notFound)
    return <p role="alert" className="p-4 text-muted">Player not found. <Link className="underline" href="/players">Search players</Link></p>;
  if (error && !p)
    return <p role="alert" className="p-4 text-muted">Can’t reach the data service ({error}).</p>;
  const bio = p && [p.height && `${p.height}${p.weight ? `, ${p.weight} lb` : ""}`, p.age != null && `${p.age} yrs`, p.country, p.school]
    .filter(Boolean).join(" · ");
  const meta = p && [p.jersey && `#${p.jersey}`, p.position, p.team_name ?? p.team].filter(Boolean).join(" · ");
  return (
    <div className="isolate sticky top-0 z-20 -mx-4 border-b border-line bg-bg/95 px-4 pt-1" style={gameVars(p?.team, p?.team)}>
      <div className="hero-wash" aria-hidden />
      <div className="flex items-center justify-between">
        <Link href="/players" className="inline-flex min-h-11 items-center text-xs text-muted hover:text-fg">‹ All players</Link>
        <div className="flex items-center gap-1">
          {p && <WatchButton item={{ kind: "player", id: p.id, name: p.name, sub: p.team ?? undefined }} />}
          <Link href={`/compare?a=${id}`} className="inline-flex min-h-11 items-center px-2 text-xs text-muted hover:text-fg">Compare ⇄</Link>
        </div>
      </div>
      {loading || !p ? (
        <div className="h-[72px] skeleton rounded bg-surface" aria-busy />
      ) : (
        <div className="flex items-center gap-3 pb-2">
          <Headshot id={p.id} name={p.name} width={96} />
          <div className="min-w-0">
            <h1 className="truncate text-3xl font-extrabold sm:text-5xl">{p.name}</h1>
            <p className="truncate text-sm">{meta}</p>
            {p.injury && (
              <p className="mt-0.5 flex items-center gap-2 text-sm">
                <StatusPill status={p.injury.status} />
                <span className="truncate text-muted">{shortReason(p.injury.reason)}{p.injury.matchup ? ` · ${p.injury.matchup}` : ""}{p.injury.espn_return_date ? ` · ESPN est. return ${returnText(p.injury.espn_return_date)}` : ""}</span>
              </p>
            )}
            {!p.injury && p.espn_injury && (
              <p className="mt-0.5 flex items-center gap-2 text-sm">
                <EspnTag status={p.espn_injury.status} />
                <span className="truncate text-muted">{p.espn_injury.injury}{p.espn_injury.return_date ? ` · ESPN est. return ${returnText(p.espn_injury.return_date)}` : ""}</span>
              </p>
            )}
            <p className="truncate text-xs text-muted">{bio}</p>
            {p.draft && <p className="hidden truncate text-xs text-muted sm:block">Draft: {p.draft}{p.greatest_75 ? " · NBA 75th Anniversary Team" : ""}</p>}
          </div>
        </div>
      )}
      <TabBar label="Player sections" className="-mb-px" active={tabs.find((t) => t.href === path)?.href ?? null} tabs={tabs} />
    </div>
  );
}
