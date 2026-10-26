/** Team colours, keyed by tricode: [main, secondary]. Used for tints, edges and glows, never as text on its own. */
const RAW: Record<string, [string, string]> = {
  ATL: ["#E03A3E", "#C1D32F"], BOS: ["#007A33", "#BA9653"], BKN: ["#A6A6A6", "#FFFFFF"], CHA: ["#00788C", "#1D1160"], CHI: ["#CE1141", "#FFFFFF"],
  CLE: ["#B1103D", "#FDBB30"], DAL: ["#00538C", "#B8C4CA"], DEN: ["#FEC524", "#4D90CD"], DET: ["#C8102E", "#1D42BA"], GSW: ["#FFC72C", "#1D428A"],
  HOU: ["#CE1141", "#C4CED4"], IND: ["#FDBB30", "#2A5DAA"], LAC: ["#C8102E", "#1D428A"], LAL: ["#FDB927", "#552583"], MEM: ["#5D76A9", "#12173F"],
  MIA: ["#C8102E", "#F9A01B"], MIL: ["#1F9D55", "#EEE1C6"], MIN: ["#2E7DB8", "#78BE20"], NOP: ["#C8102E", "#85714D"], NYK: ["#F58426", "#006BB6"],
  OKC: ["#007AC1", "#EF3B24"], ORL: ["#0077C0", "#C4CED4"], PHI: ["#006BB6", "#ED174C"], PHX: ["#E56020", "#8C6FD6"], POR: ["#E03A3E", "#FFFFFF"],
  SAC: ["#7B4BB0", "#A7B2B8"], SAS: ["#C4CED4", "#FFFFFF"], TOR: ["#CE1141", "#FFFFFF"], UTA: ["#F9A01B", "#5B8DD6"], WAS: ["#E31837", "#5B8DD6"],
};
const FALLBACK: [string, string] = ["#ff6a1f", "#e3a857"];

const channel = (h: string, i: number) => parseInt(h.slice(1 + i * 2, 3 + i * 2), 16);
function luminance(hex: string): number {
  const f = (c: number) => { const s = c / 255; return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4; };
  return 0.2126 * f(channel(hex, 0)) + 0.7152 * f(channel(hex, 1)) + 0.0722 * f(channel(hex, 2));
}
/** Mix toward white until the colour is bright enough to read as a glow on a dark floor. */
export function lift(hex: string, min = 0.1): string {
  let c = hex;
  for (let t = 0; luminance(c) < min && t < 10; t++) {
    const mix = (i: number) => Math.round(channel(c, i) + (255 - channel(c, i)) * 0.12).toString(16).padStart(2, "0");
    c = `#${mix(0)}${mix(1)}${mix(2)}`;
  }
  return c.toUpperCase();
}

export interface TeamColors { main: string; alt: string }
export function teamColors(tricode: string | null | undefined): TeamColors {
  const [main, alt] = RAW[(tricode ?? "").toUpperCase()] ?? FALLBACK;
  return { main: lift(main), alt: lift(alt) };
}

/** CSS custom properties for an element that wants to be tinted by a team: `style={teamVars("DEN")}` then use var(--t1) / var(--t2). */
export const teamVars = (tricode: string | null | undefined) => {
  const c = teamColors(tricode);
  return { "--t1": c.main, "--t2": c.alt } as React.CSSProperties;
};

/** The two teams of a game: --a1/--a2 for the away side, --h1/--h2 for the home side. */
export const gameVars = (away: string | null | undefined, home: string | null | undefined) => {
  const a = teamColors(away), h = teamColors(home);
  return { "--a1": a.main, "--a2": a.alt, "--h1": h.main, "--h2": h.alt } as React.CSSProperties;
};
