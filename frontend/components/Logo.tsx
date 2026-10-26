"use client";
import { useState } from "react";
import { logoUrl } from "@/lib/format";

export function TeamLogo({ id, tricode, size = 32 }: { id: number; tricode: string; size?: number }) {
  const [failed, setFailed] = useState(false);
  if (failed)
    return (
      <span aria-hidden className="grid place-items-center rounded-full bg-surface2 text-[10px] font-bold text-muted"
        style={{ width: size, height: size }}>{tricode}</span>
    );
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={logoUrl(id)} alt="" width={size} height={size} loading="lazy" onError={() => setFailed(true)} />;
}
