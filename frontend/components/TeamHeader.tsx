"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { TeamLogo } from "./Logo";
import { TabBar } from "./TabBar";
import { WatchButton } from "./WatchButton";
import { gameVars } from "@/lib/teamColors";
import { useTeam } from "./TeamProvider";

const TABS = [
  { slug: "", label: "Overview" },
  { slug: "roster", label: "Roster" },
  { slug: "schedule", label: "Schedule" },
];

const ordinal = (n: number) => {
  const suffix = ["th", "st", "nd", "rd"], v = n % 100;
  return n + (suffix[(v - 20) % 10] || suffix[v] || suffix[0]);
};

export function TeamHeader() {
  const { id, data, loading, notFound, error } = useTeam();
  const path = usePathname();
  const tabs = TABS.map((t) => ({ href: `/teams/${id}${t.slug ? `/${t.slug}` : ""}`, label: t.label }));
  if (notFound)
    return <p role="alert" className="p-4 text-muted">Team not found. <Link className="underline" href="/standings">Back to standings</Link></p>;
  if (error && !data) return <p role="alert" className="p-4 text-muted">Can’t reach the data service ({error}).</p>;
  const s = data?.standing;
  return (
    <div className="isolate sticky top-0 z-20 -mx-4 border-b border-line bg-bg/95 px-4 pt-1" style={gameVars(data?.team.abbr, data?.team.abbr)}>
      <div className="hero-wash" aria-hidden />
      <div className="flex items-center justify-between">
        <Link href="/standings" className="inline-flex min-h-11 items-center text-xs text-muted hover:text-fg">‹ Standings</Link>
        {data && <WatchButton item={{ kind: "team", id: data.team.id, name: `${data.team.city} ${data.team.name}`, sub: data.team.abbr ?? undefined }} />}
      </div>
      {loading || !data ? (
        <div className="h-[72px] skeleton rounded bg-surface" aria-busy />
      ) : (
        <div className="flex items-center gap-3 pb-2">
          <TeamLogo id={data.team.id} tricode={data.team.abbr ?? ""} size={64} />
          <div className="min-w-0">
            <h1 className="truncate text-3xl font-extrabold sm:text-5xl">{data.team.city} {data.team.name}</h1>
            <p className="num truncate text-sm">
              {s ? <>{s.w}-{s.l} · {ordinal(s.conf_rank)} in the {data.team.conference}ern Conference{s.streak ? ` · ${s.streak}` : ""}</> : "Record not loaded"}
            </p>
            <p className="truncate text-xs text-muted">{data.team.division} Division{data.standings_season ? ` · ${data.standings_season}` : ""}</p>
          </div>
        </div>
      )}
      <TabBar label="Team sections" className="-mb-px" active={tabs.find((t) => t.href === path)?.href ?? null} tabs={tabs} />
    </div>
  );
}
