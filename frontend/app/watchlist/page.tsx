import { WatchlistView } from "@/components/watchlist/WatchlistView";

import { PageHeader } from "@/components/PageHeader";

export default function WatchlistPage() {
  return (
    <>
      <PageHeader kicker="Your players and teams" title="Watchlist" />
      <WatchlistView />
    </>
  );
}
