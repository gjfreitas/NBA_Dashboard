import { Suspense } from "react";
import { LeadersView } from "@/components/leaders/LeadersView";

import { PageHeader } from "@/components/PageHeader";

export default function LeadersPage() {
  return (
    <>
      <PageHeader kicker="Stat boards" title="League leaders" />
      <Suspense fallback={<div className="h-96 skeleton rounded-lg bg-surface" aria-busy />}>
        <LeadersView />
      </Suspense>
    </>
  );
}
