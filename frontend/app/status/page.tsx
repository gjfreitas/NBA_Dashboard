import { StatusView } from "@/components/StatusView";

import { PageHeader } from "@/components/PageHeader";

export default function StatusPage() {
  return (
    <>
      <PageHeader kicker="System" title="Data status" />
      <StatusView />
    </>
  );
}
