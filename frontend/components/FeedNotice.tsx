/** Shown above anything built from the play-by-play when the NBA's play-by-play file is not coming through but plays are already on screen. */
export function FeedNotice() {
  return (
    <p role="status" className="mb-3 rounded-lg border border-line bg-surface p-3 text-xs text-muted">
      <b className="text-fg">Play-by-play is delayed.</b> The NBA’s play-by-play feed is not responding right now, so this shows the last plays received. The score and box score are still updating, and this resumes by itself when the feed returns.
    </p>
  );
}
