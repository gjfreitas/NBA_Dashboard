import { Suspense } from "react";
import { TeamHeader } from "@/components/TeamHeader";
import { TeamProvider } from "@/components/TeamProvider";

export default function TeamLayout({ children }: LayoutProps<"/teams/[id]">) {
  return (
    <Suspense fallback={<div className="h-32 skeleton rounded bg-surface" aria-busy />}>
      <TeamProvider>
        <TeamHeader />
        <div className="pt-4">{children}</div>
      </TeamProvider>
    </Suspense>
  );
}
