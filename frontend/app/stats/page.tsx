import { PageHeader } from "@/components/PageHeader";
import { StatsExplorer } from "@/components/stats/StatsExplorer";

export const metadata = { title: "Stats · NBA Live" };

export default function StatsPage() {
  return (
    <>
      <PageHeader kicker="Hit rates against the book line" title="Stats" />
      <StatsExplorer />
    </>
  );
}
