"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useFetch } from "@/lib/hooks";
import type { PlayerSummary } from "@/lib/types";
import { Headshot } from "./Headshot";

export function PlayerSearch() {
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
  const [active, setActive] = useState(true);
  useEffect(() => {
    const t = setTimeout(() => setQ(text.trim()), 250);
    return () => clearTimeout(t);
  }, [text]);
  const { data, loading, error } = useFetch<PlayerSummary[]>(`/api/players?q=${encodeURIComponent(q)}&active=${active}&limit=40`);
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <label className="flex-1">
          <span className="sr-only">Search players</span>
          <input type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder="Search players, e.g. Jokic"
            className="min-h-11 w-full rounded-lg border border-line bg-surface px-3 text-base placeholder:text-muted" />
        </label>
        <label className="flex min-h-11 items-center gap-2 text-sm text-muted">
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} className="size-4" />
          Active only
        </label>
      </div>
      {error && <p role="alert" className="text-muted">Can’t reach the data service ({error}).</p>}
      {loading && !data && <div className="h-40 skeleton rounded-lg bg-surface" aria-busy />}
      {data && (
        <ul className="grid gap-2 sm:grid-cols-2" aria-live="polite">
          {data.map((p) => (
            <li key={p.id}>
              <Link href={`/players/${p.id}`} className="flex min-h-11 items-center gap-3 rounded-lg border border-line bg-surface p-2 hover:bg-surface2">
                <Headshot id={p.id} name={p.name} width={56} />
                <span className="min-w-0">
                  <span className="block truncate font-medium">{p.name}</span>
                  <span className="block truncate text-xs text-muted">
                    {[p.team, p.position, p.is_active ? null : "Retired"].filter(Boolean).join(" · ") || "—"}
                  </span>
                </span>
              </Link>
            </li>
          ))}
          {!data.length && <li className="text-muted">No players match “{q}”.</li>}
        </ul>
      )}
    </div>
  );
}
