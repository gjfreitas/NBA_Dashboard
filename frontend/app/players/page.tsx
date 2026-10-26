import { PlayerSearch } from "@/components/PlayerSearch";

import { PageHeader } from "@/components/PageHeader";

export default function PlayersPage() {
  return (
    <>
      <PageHeader kicker="Search the league" title="Players" />
      <PlayerSearch />
    </>
  );
}
