"use client";
import { createContext, useContext, type ReactNode } from "react";
import { useParams } from "next/navigation";
import { useFetch, type Loadable } from "@/lib/hooks";
import type { TeamProfile } from "@/lib/types";

const Ctx = createContext<(Loadable<TeamProfile> & { id: string }) | null>(null);

export function useTeam() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useTeam outside TeamProvider");
  return c;
}

export function TeamProvider({ children }: { children: ReactNode }) {
  const { id } = useParams<{ id: string }>();
  const state = useFetch<TeamProfile>(`/api/teams/${id}`);
  return <Ctx.Provider value={{ ...state, id }}>{children}</Ctx.Provider>;
}
