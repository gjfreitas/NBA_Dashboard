"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";
import { useAlertStore } from "@/lib/useAlerts";
import { TabBar } from "./TabBar";

interface Item { href: string; label: string; icon: ReactNode }

const I = (d: string) => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d={d} /></svg>
);
const ICON = {
  scores: I("M3 6h18v12H3z M12 6v12 M3 12h4 M17 12h4"),
  today: I("M4 5h16v15H4z M4 10h16 M9 3v4 M15 3v4"),
  props: I("M4 19V9 M10 19V5 M16 19v-7 M22 19H2"),
  stats: I("M4 20h16 M6 16l4-5 3 3 5-7"),
  standings: I("M8 4h8v5a4 4 0 0 1-8 0z M12 13v4 M8 20h8 M4 5h4 M16 5h4"),
  leaders: I("M6 20V12 M12 20V4 M18 20v-6"),
  injuries: I("M12 5v14 M5 12h14"),
  players: I("M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M4 21c0-4 4-6 8-6s8 2 8 6"),
  compare: I("M7 4v16 M17 4v16 M3 8l4-4 4 4 M13 16l4 4 4-4"),
  watchlist: I("M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z"),
  more: I("M5 12h.01 M12 12h.01 M19 12h.01"),
};

const PRIMARY: Item[] = [
  { href: "/", label: "Scores", icon: ICON.scores },
  { href: "/today", label: "Today", icon: ICON.today },
  { href: "/props", label: "Props", icon: ICON.props },
  { href: "/standings", label: "Standings", icon: ICON.standings },
];
const SECONDARY: Item[] = [
  { href: "/stats", label: "Stats", icon: ICON.stats },
  { href: "/leaders", label: "Leaders", icon: ICON.leaders },
  { href: "/injuries", label: "Injuries", icon: ICON.injuries },
  { href: "/players", label: "Players", icon: ICON.players },
  { href: "/compare", label: "Compare", icon: ICON.compare },
  { href: "/watchlist", label: "Watchlist", icon: ICON.watchlist },
];
const ALL = [...PRIMARY, ...SECONDARY];

const isActive = (path: string, href: string) =>
  href === "/" ? path === "/" || path.startsWith("/games") : path.startsWith(href) || (href === "/standings" && path.startsWith("/teams"));

const TAB = "relative inline-flex min-h-11 shrink-0 items-center px-3 display text-[0.95rem] font-semibold tracking-wide";

/** What shows while the URL isn't known yet (prerendering): the same links, nothing marked current. */
export function MainNavFallback() {
  return (
    <nav aria-label="Main" className="hidden gap-0.5 sm:flex">
      {ALL.map((l) => <Link key={l.href} href={l.href} className={`${TAB} text-muted hover:text-fg`}>{l.label}</Link>)}
    </nav>
  );
}

function Badge({ n }: { n: number }) {
  return n > 0 ? <span className="ml-1.5 rounded-sm bg-live px-1.5 text-[0.7rem] font-bold leading-4 text-white" aria-label={`${n} new alerts`}>{n}</span> : null;
}

/** Site navigation. A row of tabs on wider screens; on a phone a bottom bar with the four pages used most and a "More" sheet for the rest.
 *  Reads the URL, so it must be rendered inside <Suspense> (see layout). */
export function MainNav() {
  const path = usePathname();
  const { state } = useAlertStore();
  const [openAt, setOpenAt] = useState<string | null>(null); // the page the sheet was opened on: it closes by itself when the page changes
  const open = openAt === path;
  const moreActive = SECONDARY.some((l) => isActive(path, l.href));

  return (
    <>
      <TabBar label="Main" className="hidden sm:flex" active={ALL.find((l) => isActive(path, l.href))?.href ?? null}
        tabs={ALL.map((l) => ({ href: l.href, label: l.label, badge: <Badge n={l.href === "/watchlist" ? state.unread : 0} /> }))} />

      {/* phone: bottom bar */}
      <nav aria-label="Main" className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-surface/95 backdrop-blur sm:hidden" onKeyDown={(e) => { if (e.key === "Escape") setOpenAt(null); }}>
        {open && (
          <>
            <button type="button" aria-label="Close menu" className="fixed inset-0 -z-10 cursor-default bg-black/50" onClick={() => setOpenAt(null)} />
            <ul id="more-menu" className="absolute inset-x-2 bottom-[calc(100%+0.5rem)] grid grid-cols-2 gap-1 rounded-xl border border-line bg-surface p-2 shadow-2xl">
              {SECONDARY.map((l) => (
                <li key={l.href}>
                  <Link href={l.href} aria-current={isActive(path, l.href) ? "page" : undefined}
                    className={`flex min-h-12 items-center gap-3 rounded-lg px-3 display text-base font-semibold ${isActive(path, l.href) ? "bg-surface2 text-accent" : "text-fg hover:bg-surface2"}`}>
                    {l.icon}{l.label}<Badge n={l.href === "/watchlist" ? state.unread : 0} />
                  </Link>
                </li>
              ))}
            </ul>
          </>
        )}
        <ul className="mx-auto grid max-w-md grid-cols-5 pb-[env(safe-area-inset-bottom)]">
          {PRIMARY.map((l) => {
            const on = isActive(path, l.href);
            return (
              <li key={l.href}>
                <Link href={l.href} aria-current={on ? "page" : undefined} className={`flex min-h-14 flex-col items-center justify-center gap-0.5 ${on ? "text-accent" : "text-muted"}`}>
                  {l.icon}<span className="label !text-[0.62rem]">{l.label}</span>
                </Link>
              </li>
            );
          })}
          <li>
            <button type="button" aria-expanded={open} aria-controls="more-menu" onClick={() => setOpenAt(open ? null : path)}
              className={`relative flex min-h-14 w-full flex-col items-center justify-center gap-0.5 ${open || moreActive ? "text-accent" : "text-muted"}`}>
              {ICON.more}<span className="label !text-[0.62rem]">More</span>
              {state.unread > 0 && <span className="absolute right-4 top-2 size-2 rounded-full bg-live" aria-label={`${state.unread} new alerts`} />}
            </button>
          </li>
        </ul>
      </nav>
    </>
  );
}
