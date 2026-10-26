"use client";
import { useSyncExternalStore } from "react";
import { usePolling } from "@/lib/hooks";
import type { Game } from "@/lib/types";

const noop = () => () => {};
const today = () => new Date().toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });

/** "Mon, Oct 26 · 9 games · 2 live": the line above the Scores title, from the same scoreboard the cards use. The date is read in the browser only (the server render leaves it blank). */
export function ScoresKicker() {
  const { data } = usePolling<Game[]>("/api/scoreboard", 15_000);
  const day = useSyncExternalStore(noop, today, () => "");
  if (!data) return <>{day || "Today"}</>;
  const live = data.filter((g) => g.state === "live").length, done = data.filter((g) => g.state === "final").length;
  return <>{day} · {data.length} {data.length === 1 ? "game" : "games"}{live ? ` · ${live} live` : done === data.length && data.length ? " · all final" : ""}</>;
}
