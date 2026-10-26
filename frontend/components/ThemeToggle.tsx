"use client";
import { useSyncExternalStore } from "react";

type Choice = "system" | "light" | "dark";
const KEY = "theme";
const NEXT: Record<Choice, Choice> = { system: "light", light: "dark", dark: "system" };
const LABEL: Record<Choice, string> = { system: "Theme: follows your device", light: "Theme: light", dark: "Theme: dark" };

const listeners = new Set<() => void>();
const read = (): Choice => {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch { return "system"; }
};
const subscribe = (fn: () => void) => { listeners.add(fn); return () => { listeners.delete(fn); }; };

function apply(c: Choice) {
  const root = document.documentElement;
  if (c === "system") root.removeAttribute("data-theme"); else root.setAttribute("data-theme", c);
  try { if (c === "system") localStorage.removeItem(KEY); else localStorage.setItem(KEY, c); } catch { /* private mode: the choice lasts for this visit only */ }
  listeners.forEach((f) => f());
}

const ICON: Record<Choice, string> = {
  system: "M4 5h16v11H4zM9 20h6M12 16v4",
  light: "M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M5.6 18.4L7 17M17 7l1.4-1.4M12 8a4 4 0 100 8 4 4 0 000-8z",
  dark: "M20 14.5A8 8 0 019.5 4 8 8 0 1020 14.5z",
};

/** Cycles system, light, dark. The choice is remembered in this browser; "system" follows the device setting. */
export function ThemeToggle() {
  const choice = useSyncExternalStore(subscribe, read, () => "system" as Choice);
  return (
    <button type="button" onClick={() => apply(NEXT[choice])} aria-label={`${LABEL[choice]}. Press to change.`} title={LABEL[choice]}
      className="grid size-11 place-items-center rounded-lg border border-line text-muted transition-colors hover:border-accent hover:text-fg">
      <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d={ICON[choice]} /></svg>
    </button>
  );
}
