"use client";
import Link from "next/link";

/** Anything that throws while rendering a page lands here, so a visitor gets a way forward instead of a blank screen. */
export default function Error({ reset }: { error: Error; reset: () => void }) {
  return (
    <div role="alert" className="mx-auto max-w-md space-y-3 py-16 text-center">
      <h1 className="page-title">Something went wrong</h1>
      <p className="text-muted">This page failed to load. Your data is safe; try again, or head back to the scores.</p>
      <div className="flex justify-center gap-3">
        <button type="button" onClick={reset} className="min-h-11 rounded-lg border border-accent px-4 font-semibold hover:bg-surface2">Try again</button>
        <Link href="/" className="inline-flex min-h-11 items-center rounded-lg border border-line px-4 text-muted hover:text-fg">All games</Link>
      </div>
    </div>
  );
}
