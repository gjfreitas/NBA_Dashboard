"use client";
import { createContext, useContext, type ReactNode } from "react";
import { useParams } from "next/navigation";
import type { BoxScore, Game, Play } from "@/lib/types";
import { useFetch, usePlayStream, usePolling } from "@/lib/hooks";

interface Ctx {
  id: string; game: Game | null; plays: Play[]; box: BoxScore | null;
  connected: boolean; available: boolean; missing: boolean; boxMissing: boolean;
}
const GameCtx = createContext<Ctx | null>(null);

export function useGameData() {
  const c = useContext(GameCtx);
  if (!c) throw new Error("useGameData outside GameProvider");
  return c;
}

export function GameProvider({ children }: { children: ReactNode }) {
  const { id } = useParams<{ id: string }>();
  const stream = usePlayStream(id);
  // The stream already carries the game; the scoreboard is only a fallback until it arrives.
  const sb = usePolling<Game[]>(stream.game ? null : "/api/scoreboard", 5000);
  const fromBoard = sb.data?.find((g) => g.id === id) ?? null;
  // A game that isn't on today's scoreboard (opened from a team schedule, or not started yet) is found in the schedule or its box score.
  const info = useFetch<Game>(`/api/games/${id}/info`);
  const known = stream.game ?? fromBoard ?? info.data;
  const live = known?.state !== "pre";
  const box = usePolling<BoxScore>(live ? `/api/games/${id}/boxscore` : null, known?.state === "final" ? 600000 : 5000);
  const game = stream.game ?? fromBoard ?? box.data?.game ?? info.data ?? null;
  return (
    <GameCtx.Provider value={{
      id, game, plays: stream.plays, box: box.data, connected: stream.connected,
      available: stream.available, boxMissing: box.notFound,
      missing: !sb.loading && !game && !info.loading && info.notFound && box.notFound,
    }}>
      {children}
    </GameCtx.Provider>
  );
}
