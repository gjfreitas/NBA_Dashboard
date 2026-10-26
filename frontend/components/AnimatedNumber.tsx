"use client";
import { useState } from "react";

/**
 * A whole number that rolls to its new value, and glows briefly when it changes after the page has loaded.
 * The roll is done in CSS (a registered integer property the browser interpolates), so there is no timer or re-render per frame; where that
 * is not supported the number simply appears. The real value is always in the text for screen readers.
 */
export function AnimatedNumber({ value, className = "" }: { value: number; className?: string }) {
  const [initial] = useState(value);
  return (
    <span className={`relative inline-block ${className}`}>
      <span className="sr-only">{value}</span>
      <span aria-hidden className="count" style={{ "--n": Math.round(value) } as React.CSSProperties} />
      {value !== initial && <span key={value} aria-hidden className="flash-ring" />}
    </span>
  );
}
