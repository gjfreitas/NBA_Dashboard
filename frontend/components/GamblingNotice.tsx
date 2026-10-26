/** Shown wherever sportsbook lines appear. The headline is always visible; the detail opens on demand so it does not crowd a phone screen. */
export function GamblingNotice({ compact = false }: { compact?: boolean }) {
  return (
    <aside aria-label="Responsible gambling" className="rounded-lg border border-line bg-surface p-3 text-xs text-muted">
      <p><b className="text-fg">18+ only. Please gamble responsibly.</b> Lines are for information only; this site does not take bets.</p>
      {!compact && (
        <details className="mt-1">
          <summary className="inline-flex min-h-11 cursor-pointer items-center underline">More</summary>
          <p>
            These lines come from sportsbooks. The site gives no betting advice and guarantees no result; lines move and differ between books, so check the book before you act.
            Past hit rates do not predict future games. If gambling is causing you problems, free confidential help is available (in the US call 1-800-GAMBLER;
            elsewhere search for your country&rsquo;s gambling help line).
          </p>
        </details>
      )}
    </aside>
  );
}
