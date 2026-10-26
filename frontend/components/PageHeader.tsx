import type { ReactNode } from "react";

/** The top of a page: a small context line above a large title, and room on the right for page-level actions. */
export function PageHeader({ kicker, title, children }: { kicker?: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
      <div>
        {kicker && <p className="kicker mb-1">{kicker}</p>}
        <h1 className="page-title">{title}</h1>
      </div>
      {children}
    </div>
  );
}
