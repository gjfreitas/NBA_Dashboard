import { Suspense } from "react";
import { CompareView } from "@/components/CompareView";

import { PageHeader } from "@/components/PageHeader";

export default function ComparePage() {
  return (
    <>
      <PageHeader kicker="Head to head" title="Compare players" />
      <Suspense fallback={<div className="h-48 skeleton rounded-lg bg-surface" aria-busy />}>
        <CompareView />
      </Suspense>
    </>
  );
}
