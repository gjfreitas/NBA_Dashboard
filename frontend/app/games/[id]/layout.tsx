import { Suspense } from "react";
import { GameHeader } from "@/components/GameHeader";
import { GameProvider } from "@/components/GameProvider";

export default function GameLayout({ children }: LayoutProps<"/games/[id]">) {
  return (
    <Suspense fallback={<div className="h-32 skeleton rounded bg-surface" aria-busy />}>
      <GameProvider>
        <GameHeader />
        <div className="pt-4">{children}</div>
      </GameProvider>
    </Suspense>
  );
}
