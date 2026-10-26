"use client";
import { useWatchlist } from "@/lib/useWatchlist";
import { isWatched, type WatchItem } from "@/lib/watchlist";

/** Follow / unfollow a player or team. The state lives in this browser. */
export function WatchButton({ item }: { item: WatchItem }) {
  const { list, toggle } = useWatchlist();
  const on = isWatched(list, item.kind, item.id);
  return (
    <button type="button" aria-pressed={on} onClick={() => toggle(item)} title={on ? "Remove from your watchlist" : "Add to your watchlist"}
      className={`inline-flex min-h-11 items-center gap-1 rounded-lg border px-3 text-xs ${on ? "border-accent font-semibold text-fg" : "border-line text-muted hover:text-fg"}`}>
      <span aria-hidden>{on ? "★" : "☆"}</span> {on ? "Following" : "Follow"}
      <span className="sr-only"> {item.name}</span>
    </button>
  );
}
