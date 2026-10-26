"use client";
import { createContext, useContext, type ReactNode } from "react";
import { useParams } from "next/navigation";
import { useFetch, type Loadable } from "@/lib/hooks";
import type { PlayerProfile } from "@/lib/types";

const Ctx = createContext<(Loadable<PlayerProfile> & { id: string }) | null>(null);

export function usePlayer() {
  const c = useContext(Ctx);
  if (!c) throw new Error("usePlayer outside PlayerProvider");
  return c;
}

export function PlayerProvider({ children }: { children: ReactNode }) {
  const { id } = useParams<{ id: string }>();
  const state = useFetch<PlayerProfile>(`/api/players/${id}`);
  return <Ctx.Provider value={{ ...state, id }}>{children}</Ctx.Provider>;
}
