import { Suspense } from "react";
import { PlayerHeader } from "@/components/PlayerHeader";
import { PlayerProvider } from "@/components/PlayerProvider";

export default function PlayerLayout({ children }: LayoutProps<"/players/[id]">) {
  return (
    <Suspense fallback={<div className="h-32 skeleton rounded bg-surface" aria-busy />}>
      <PlayerProvider>
        <PlayerHeader />
        <div className="pt-4">{children}</div>
      </PlayerProvider>
    </Suspense>
  );
}
