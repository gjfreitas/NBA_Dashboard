"use client";
import { useId, useState, type ReactNode } from "react";

/** A small "i" button that opens a short note. Replaces the paragraphs of fine print that used to sit under every panel. */
export function InfoTip({ label = "More information", children, align = "left" }: { label?: string; children: ReactNode; align?: "left" | "right" }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <span className="relative inline-flex align-middle" onKeyDown={(e) => { if (e.key === "Escape") setOpen(false); }}>
      <button type="button" aria-expanded={open} aria-controls={id} aria-label={label} onClick={() => setOpen((o) => !o)}
        className="relative grid size-6 place-items-center rounded-full border border-line text-[0.7rem] before:absolute before:-inset-3 before:content-[''] font-bold text-muted transition-colors hover:border-accent hover:text-fg">
        i
      </button>
      {open && (
        <>
          <button type="button" aria-label="Close" tabIndex={-1} className="fixed inset-0 z-30 cursor-default" onClick={() => setOpen(false)} />
          <span id={id} role="note" className={`pop absolute top-8 z-40 w-72 max-w-[80vw] rounded-lg border border-line bg-surface p-3 text-left text-xs font-normal normal-case leading-relaxed tracking-normal text-fg shadow-2xl ${align === "right" ? "right-0" : "left-0"}`}>
            {children}
          </span>
        </>
      )}
    </span>
  );
}
