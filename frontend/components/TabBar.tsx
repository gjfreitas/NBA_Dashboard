"use client";
import Link from "next/link";
import { useEffect, useRef, type ReactNode } from "react";

export interface Tab { href: string; label: string; badge?: ReactNode }

/** A row of page tabs with one orange marker that slides to the current tab instead of each tab drawing its own underline. */
export function TabBar({ label, tabs, active, className = "", linkClass = "" }: { label: string; tabs: Tab[]; active: string | null; className?: string; linkClass?: string }) {
  const nav = useRef<HTMLElement>(null);
  const marker = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const place = () => {
      const el = nav.current?.querySelector<HTMLElement>('a[aria-current="page"]');
      const m = marker.current;
      if (!m) return;
      if (!el) { m.style.opacity = "0"; return; }
      m.style.opacity = "1";
      m.style.width = `${Math.max(0, el.offsetWidth - 16)}px`;
      m.style.transform = `translateX(${el.offsetLeft + 8}px) skewX(-14deg)`;
    };
    place();
    const ro = new ResizeObserver(place);
    if (nav.current) ro.observe(nav.current);
    document.fonts?.ready.then(place);
    return () => ro.disconnect();
  }, [active, tabs.length]);

  return (
    <nav ref={nav} aria-label={label} className={`relative flex overflow-x-auto [scrollbar-width:none] ${className}`}>
      {tabs.map((t) => (
        <Link key={t.href} href={t.href} aria-current={t.href === active ? "page" : undefined}
          className={`display inline-flex min-h-11 shrink-0 items-center whitespace-nowrap px-3 text-[0.95rem] font-semibold tracking-wide transition-colors ${t.href === active ? "text-fg" : "text-muted hover:text-fg"} ${linkClass}`}>
          {t.label}{t.badge}
        </Link>
      ))}
      <span ref={marker} aria-hidden className="tab-marker" />
    </nav>
  );
}
