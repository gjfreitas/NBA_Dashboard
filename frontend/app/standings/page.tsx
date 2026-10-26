import { StandingsView } from "@/components/StandingsView";

import { PageHeader } from "@/components/PageHeader";

export default function StandingsPage() {
  return (
    <>
      <PageHeader kicker="League table" title="Standings" />
      <StandingsView />
    </>
  );
}
