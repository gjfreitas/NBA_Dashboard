"use client";
import { useEffect, useRef } from "react";
import { MARKETS, normalizePrefs, type Market, type MarketPrefs } from "@/lib/props";

export const PREFS_KEY = "nba-dashboard.markets.v1";

export function loadPrefs(): MarketPrefs {
  if (typeof window === "undefined") return normalizePrefs(null);
  try {
    return normalizePrefs(JSON.parse(window.localStorage.getItem(PREFS_KEY) ?? "null"));
  } catch {
    return normalizePrefs(null);
  }
}

export function savePrefs(p: MarketPrefs) {
  try {
    window.localStorage.setItem(PREFS_KEY, JSON.stringify(p));
  } catch {
    /* private mode / quota: preferences just won't persist */
  }
}

export function MarketBar({ markets, active, onSelect, onCustomize }: {
  markets: Market[]; active: string; onSelect: (key: string) => void; onCustomize: () => void;
}) {
  return (
    <div className="flex items-center gap-1 rounded-lg border border-line bg-surface">
      <div role="tablist" aria-label="Stat market" className="flex flex-1 gap-1 overflow-x-auto px-1 [scrollbar-width:none]">
        {markets.map((m) => (
          <button key={m.key} role="tab" aria-selected={m.key === active} onClick={() => onSelect(m.key)}
            className={`min-h-11 shrink-0 whitespace-nowrap border-b-2 px-3 text-sm ${m.key === active ? "border-accent font-semibold text-fg" : "border-transparent text-muted hover:text-fg"}`}>
            {m.label}
          </button>
        ))}
      </div>
      <button onClick={onCustomize} aria-label="Customize markets" title="Customize markets"
        className="grid min-h-11 min-w-11 shrink-0 place-items-center text-lg text-muted hover:text-fg">⚙</button>
    </div>
  );
}

/** Show / hide and reorder markets. Uses a native <dialog> (focus trap + Esc come for free). */
export function MarketsDialog({ open, prefs, onChange, onClose }: {
  open: boolean; prefs: MarketPrefs; onChange: (p: MarketPrefs) => void; onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);

  const label = (k: string) => MARKETS.find((m) => m.key === k)?.label ?? k;
  const move = (i: number, by: -1 | 1) => {
    const order = [...prefs.order];
    const j = i + by;
    if (j < 0 || j >= order.length) return;
    [order[i], order[j]] = [order[j], order[i]];
    onChange({ ...prefs, order });
  };
  const toggle = (k: string) =>
    onChange({ ...prefs, hidden: prefs.hidden.includes(k) ? prefs.hidden.filter((x) => x !== k) : [...prefs.hidden, k] });

  return (
    <dialog ref={ref} onClose={onClose} onClick={(e) => e.target === ref.current && onClose()}
      aria-labelledby="markets-title" className="m-auto w-[min(26rem,calc(100vw-2rem))] rounded-xl border border-line bg-surface p-0 text-fg backdrop:bg-black/60">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <h2 id="markets-title" className="font-semibold">Customize markets</h2>
        <button onClick={onClose} aria-label="Close" className="grid min-h-11 min-w-11 place-items-center text-muted hover:text-fg">✕</button>
      </div>
      <p className="px-4 pt-3 text-sm text-muted">Turn off the markets you never use and move the rest into the order you want. Saved in this browser.</p>
      <ul className="max-h-[55vh] overflow-y-auto px-2 py-2">
        {prefs.order.map((k, i) => (
          <li key={k} className="flex items-center gap-1 rounded px-2 py-1 hover:bg-surface2">
            <span className="flex-1 text-sm">{label(k)}</span>
            <button aria-label={`Move ${label(k)} up`} disabled={i === 0} onClick={() => move(i, -1)} className="min-h-11 min-w-9 text-muted hover:text-fg disabled:opacity-30">↑</button>
            <button aria-label={`Move ${label(k)} down`} disabled={i === prefs.order.length - 1} onClick={() => move(i, 1)} className="min-h-11 min-w-9 text-muted hover:text-fg disabled:opacity-30">↓</button>
            {k === "pts" ? (
              <span className="w-20 text-right text-xs font-semibold text-muted">ALWAYS ON</span>
            ) : (
              <label className="flex w-20 items-center justify-end">
                <span className="sr-only">Show {label(k)}</span>
                <input type="checkbox" role="switch" checked={!prefs.hidden.includes(k)} onChange={() => toggle(k)} className="size-5 accent-[var(--accent)]" />
              </label>
            )}
          </li>
        ))}
      </ul>
      <div className="flex justify-between border-t border-line px-4 py-3">
        <button onClick={() => onChange(normalizePrefs(null))} className="min-h-11 px-2 text-sm text-muted underline hover:text-fg">Reset</button>
        <button onClick={onClose} className="min-h-11 rounded-lg bg-surface2 px-5 text-sm font-semibold hover:bg-line">Done</button>
      </div>
    </dialog>
  );
}
