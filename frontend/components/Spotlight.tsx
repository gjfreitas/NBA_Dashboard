"use client";
import { useEffect } from "react";

/** One pointer listener for the whole page: whatever `.spot` element the pointer is over gets --mx/--my, which its CSS uses for a soft light that follows the cursor. */
export function Spotlight() {
  useEffect(() => {
    if (window.matchMedia("(pointer: coarse), (prefers-reduced-motion: reduce)").matches) return;
    let raf = 0;
    const move = (e: PointerEvent) => {
      const el = (e.target as Element | null)?.closest?.<HTMLElement>(".spot");
      if (!el) return;
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const r = el.getBoundingClientRect();
        el.style.setProperty("--mx", `${e.clientX - r.left}px`);
        el.style.setProperty("--my", `${e.clientY - r.top}px`);
      });
    };
    document.addEventListener("pointermove", move, { passive: true });
    return () => { document.removeEventListener("pointermove", move); cancelAnimationFrame(raf); };
  }, []);
  return null;
}
