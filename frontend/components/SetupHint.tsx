/** Empty state for data the backend has not loaded: plain wording for visitors, the command in small print for whoever runs the site. */
export function SetupHint({ cmd }: { cmd: string }) {
  return (
    <>
      This isn’t available yet.
      <span className="mt-1 block text-xs">Site owner: <code className="rounded bg-surface2 px-1.5 py-0.5">{cmd}</code></span>
    </>
  );
}
