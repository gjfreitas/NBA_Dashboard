/** The watchlist: players and teams the visitor follows. Kept in this browser only (localStorage), no account. */
export interface WatchItem { kind: "player" | "team"; id: number; name: string; sub?: string }
export interface Watchlist { items: WatchItem[] }

export const STORAGE_KEY = "nba-watchlist-v1";
export const MAX_ITEMS = 100;
export const EMPTY: Watchlist = { items: [] };

/** Reads whatever is in storage without ever throwing: damaged or foreign data is dropped, valid entries are kept. */
export function parseWatchlist(raw: string | null): Watchlist {
  if (!raw) return EMPTY;
  try {
    const data = JSON.parse(raw) as { items?: unknown };
    if (!Array.isArray(data.items)) return EMPTY;
    const seen = new Set<string>();
    const items: WatchItem[] = [];
    for (const x of data.items as Record<string, unknown>[]) {
      if (!x || (x.kind !== "player" && x.kind !== "team") || !Number.isInteger(x.id) || typeof x.name !== "string") continue;
      const key = `${x.kind}:${x.id}`;
      if (seen.has(key)) continue;
      seen.add(key);
      items.push({ kind: x.kind, id: x.id as number, name: x.name, ...(typeof x.sub === "string" ? { sub: x.sub } : {}) });
    }
    return { items: items.slice(0, MAX_ITEMS) };
  } catch {
    return EMPTY;
  }
}

export const isWatched = (w: Watchlist, kind: WatchItem["kind"], id: number) => w.items.some((i) => i.kind === kind && i.id === id);

/** Adds the item if it isn't on the list, removes it if it is. A full list refuses new items rather than dropping old ones. */
export function toggleItem(w: Watchlist, item: WatchItem): Watchlist {
  if (isWatched(w, item.kind, item.id)) return { items: w.items.filter((i) => !(i.kind === item.kind && i.id === item.id)) };
  if (w.items.length >= MAX_ITEMS) return w;
  return { items: [...w.items, item] };
}

export const idsOf = (w: Watchlist, kind: WatchItem["kind"]) => new Set(w.items.filter((i) => i.kind === kind).map((i) => i.id));
