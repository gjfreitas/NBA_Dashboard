"use client";
import Link from "next/link";
import { usePolling } from "@/lib/hooks";
import type { Game } from "@/lib/types";

/** The site name drawn like a broadcast channel bug: NBA in plain type, LIVE in a slanted block that lights up while any game is on. */
export function Wordmark() {
  const { data } = usePolling<Game[]>("/api/scoreboard", 30_000);
  const live = (data ?? []).some((g) => g.state === "live");
  return (
    <Link href="/" aria-label={`NBA Live, home${live ? ", games are live now" : ""}`} className="group flex items-center gap-1.5 py-2.5">
      <span className="display text-[1.9rem] font-black leading-none tracking-[0.02em]">NBA</span>
      <span className={`bug display relative inline-flex items-center gap-1.5 py-[0.2rem] pl-2.5 pr-5 text-[1.15rem] font-black leading-none tracking-[0.06em] transition-colors ${live ? "bg-live text-white" : "bg-accent text-on-accent"}`}>
        {live && <span className="live-dot size-1.5 rounded-full bg-white" aria-hidden />}
        LIVE
      </span>
    </Link>
  );
}
