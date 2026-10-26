"use client";
import { useRouter } from "next/navigation";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useFetch } from "@/lib/hooks";
import { matchTeams, moveIndex } from "@/lib/search";
import type { PlayerSummary, TeamInfo } from "@/lib/types";
import { Headshot } from "./Headshot";
import { TeamLogo } from "./Logo";

interface Result { key: string; href: string; label: string; sub: string; team?: TeamInfo; player?: PlayerSummary }

/** Search from anywhere: a button in the header, or Ctrl/Cmd+K. Finds players and teams; arrow keys and Enter work. */
export function GlobalSearch() {
  const router = useRouter();
  const dialog = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const listId = useId();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
  const [active, setActive] = useState(-1);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setOpen(true); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    const d = dialog.current;
    if (!d) return;
    if (open && !d.open) { d.showModal(); input.current?.focus(); }
    if (!open && d.open) d.close();
  }, [open]);

  useEffect(() => {
    const t = setTimeout(() => setQ(text.trim()), 200);
    return () => clearTimeout(t);
  }, [text]);

  const { data: teams } = useFetch<TeamInfo[]>(open ? "/api/teams" : null);
  const { data: players, loading } = useFetch<PlayerSummary[]>(open && q.length >= 2 ? `/api/players?q=${encodeURIComponent(q)}&active=true&limit=6` : null, { keepPrevious: true });

  const results = useMemo<Result[]>(() => {
    const t = matchTeams(teams ?? [], q, 4).map((x) => ({ key: `t${x.id}`, href: `/teams/${x.id}`, label: `${x.city} ${x.name}`, sub: "Team", team: x }));
    const p = (q.length >= 2 ? players ?? [] : []).map((x) => ({ key: `p${x.id}`, href: `/players/${x.id}`, label: x.name, sub: [x.team, x.position].filter(Boolean).join(" · ") || "Player", player: x }));
    return [...t, ...p];
  }, [teams, players, q]);

  const close = () => { setOpen(false); setText(""); setQ(""); setActive(-1); };
  const go = (r: Result) => { close(); router.push(r.href); };

  return (
    <>
      <button type="button" onClick={() => setOpen(true)} aria-haspopup="dialog" aria-keyshortcuts="Control+K Meta+K"
        className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-line px-3 text-sm text-muted hover:text-fg">
        <span aria-hidden>⌕</span> Search <kbd className="hidden rounded border border-line px-1 text-xs sm:inline">Ctrl K</kbd>
      </button>
      <dialog ref={dialog} onClose={close} onClick={(e) => { if (e.target === dialog.current) close(); }} aria-label="Search players and teams"
        className="m-auto mt-16 w-[min(32rem,calc(100vw-2rem))] rounded-xl border border-line bg-surface p-0 text-fg shadow-2xl backdrop:bg-black/50">
        <div className="p-3">
          <input ref={input} type="search" value={text} placeholder="Search players or teams…" autoComplete="off"
            role="combobox" aria-expanded={results.length > 0} aria-controls={listId} aria-autocomplete="list"
            aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
            onChange={(e) => { setText(e.target.value); setActive(-1); }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); setActive((a) => moveIndex(a, e.key === "ArrowDown" ? 1 : -1, results.length)); }
              else if (e.key === "Enter" && results.length) { e.preventDefault(); go(results[active >= 0 ? active : 0]); }
            }}
            className="min-h-11 w-full rounded-lg border border-line bg-bg px-3 text-base placeholder:text-muted" />
          <ul id={listId} role="listbox" aria-label="Results" className="mt-2 max-h-80 overflow-y-auto">
            {results.map((r, i) => (
              <li key={r.key} id={`${listId}-${i}`} role="option" aria-selected={i === active}
                onClick={() => go(r)} onMouseMove={() => setActive(i)}
                className={`flex min-h-11 cursor-pointer items-center gap-3 rounded-lg px-2 py-1 ${i === active ? "bg-surface2" : ""}`}>
                {r.team ? <TeamLogo id={r.team.id} tricode={r.team.abbr ?? ""} size={32} /> : <Headshot id={r.player!.id} name={r.player!.name} width={40} />}
                <span className="min-w-0">
                  <span className="block truncate font-medium">{r.label}</span>
                  <span className="block truncate text-xs text-muted">{r.sub}</span>
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-2 px-1 text-xs text-muted" role="status">
            {q.length < 2 && !results.length ? "Type at least two letters. ↑ ↓ to move, Enter to open, Esc to close."
              : loading && !results.length ? "Searching…" : !results.length ? `No players or teams match “${q}”.` : ""}
          </p>
        </div>
      </dialog>
    </>
  );
}
