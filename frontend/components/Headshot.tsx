"use client";
import { useState } from "react";

export const headshotUrl = (id: number) => `https://cdn.nba.com/headshots/nba/latest/260x190/${id}.png`;

export function Headshot({ id, name, width = 96 }: { id: number; name: string; width?: number }) {
  const [failed, setFailed] = useState(false);
  const height = Math.round(width * (190 / 260));
  if (failed)
    return (
      <span aria-hidden className="grid shrink-0 place-items-center rounded-full bg-surface2 text-sm font-bold text-muted"
        style={{ width: height, height }}>
        {name.split(" ").map((p) => p[0]).slice(0, 2).join("")}
      </span>
    );
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={headshotUrl(id)} alt="" width={width} height={height} loading="lazy"
    className="shrink-0 rounded-lg bg-surface2 object-cover" onError={() => setFailed(true)} />;
}
