import { InjuriesView } from "@/components/availability/InjuriesView";

import { PageHeader } from "@/components/PageHeader";

export default function InjuriesPage() {
  return (
    <>
      <PageHeader kicker="Availability" title="Injury report" />
      <InjuriesView />
    </>
  );
}
