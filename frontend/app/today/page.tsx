import { TodayView } from "@/components/TodayView";

import { PageHeader } from "@/components/PageHeader";

export default function TodayPage() {
  return (
    <>
      <PageHeader kicker="The day at a glance" title="Today" />
      <TodayView />
    </>
  );
}
