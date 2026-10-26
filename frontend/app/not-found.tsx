import Link from "next/link";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-md space-y-3 py-16 text-center">
      <h1 className="page-title">Page not found</h1>
      <p className="text-muted">That address doesn’t exist. Try the scores, or search for a player or team with Ctrl+K.</p>
      <Link href="/" className="inline-flex min-h-11 items-center rounded-lg border border-accent px-4 font-semibold hover:bg-surface2">All games</Link>
    </div>
  );
}
