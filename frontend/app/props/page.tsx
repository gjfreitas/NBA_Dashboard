import { SlateBoard } from "@/components/slate/SlateBoard";

import { PageHeader } from "@/components/PageHeader";

export default function PropsPage() {
  return (
    <>
      <PageHeader kicker="Sportsbook lines" title="Props: today’s slate" />
      <SlateBoard />
    </>
  );
}
