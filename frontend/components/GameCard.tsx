import Link from "next/link";
import type { Game, GameAvailabilitySummary, TeamSummary } from "@/lib/types";
import { teamNote } from "@/lib/availability";
import { record, statusLabel } from "@/lib/format";
import { elapsedSeconds } from "@/lib/gameFlow";
import { gameVars, teamVars } from "@/lib/teamColors";
import { AnimatedNumber } from "./AnimatedNumber";
import { TeamLogo } from "./Logo";

/** How far through regulation the game is, 0 to 1. Overtime and finished games read as full. */
function progress(g: Game): number {
  if (g.state === "final") return 1;
  if (g.state === "pre") return 0;
  return Math.min(1, elapsedSeconds(g.period, g.clock || "12:00") / 2880);
}

function Quarters({ t }: { t: TeamSummary }) {
  const by = new Map(t.periods.map((p) => [p.period, p.score]));
  const n = Math.max(4, t.periods.length);
  return (
    <span className="num hidden gap-2 text-[0.8rem] text-muted @[26rem]:flex" aria-hidden>
      {Array.from({ length: n }, (_, i) => <span key={i} className="w-6 text-right">{by.get(i + 1) ?? "·"}</span>)}
    </span>
  );
}

function Row({ t, lead, dim, show }: { t: TeamSummary; lead: boolean; dim: boolean; show: boolean }) {
  return (
    <div className={`relative flex items-center gap-3 py-1.5 transition-opacity ${dim ? "opacity-55" : ""}`} style={teamVars(t.tricode)}>
      <span className="logo-glow relative grid size-11 shrink-0 place-items-center"><TeamLogo id={t.id} tricode={t.tricode} size={40} /></span>
      <div className="min-w-0 flex-1 leading-tight">
        <div className="display truncate text-[1.5rem] font-bold">{t.name}</div>
        <div className="label truncate text-muted num">{t.city}{record(t) ? ` · ${record(t)}` : ""}</div>
      </div>
      {show && <Quarters t={t} />}
      <span className={`score min-w-[3.4rem] text-right text-[2.7rem] ${lead ? "text-fg" : "text-muted"}`}>{show ? <AnimatedNumber value={t.score} /> : "–"}</span>
    </div>
  );
}

function Availability({ a }: { a: GameAvailabilitySummary }) {
  const notes = [a.away, a.home].map((t) => ({ t, note: teamNote(t) }));
  const confirmed = a.away.lineup_status === "Confirmed" && a.home.lineup_status === "Confirmed";
  const lineup = confirmed ? "Lineups confirmed" : a.away.lineup_status || a.home.lineup_status ? "Lineups expected" : null;
  if (!lineup && notes.every((n) => !n.note)) return null;
  return (
    <div className="mt-2 space-y-0.5 border-t border-dashed border-line pt-2 text-xs text-muted">
      {lineup && <p className={`label ${confirmed ? "font-semibold text-win" : ""}`}>{confirmed ? "✓ " : ""}{lineup}</p>}
      {notes.map(({ t, note }) => note && (
        <p key={t.team_id}><b className="display text-sm font-bold text-fg">{t.abbr}</b> {note}</p>
      ))}
    </div>
  );
}

/** A score bug for one game, tinted by both teams' colours: status tab, both teams with rolling numerals, a progress line, and the quarter scores when there is room. */
export function GameCard({ g, avail }: { g: Game; avail?: GameAvailabilitySummary }) {
  const show = g.state !== "pre";
  const homeLead = g.home.score > g.away.score;
  const awayLead = g.away.score > g.home.score;
  const done = g.state === "final";
  const live = g.state === "live";
  return (
    <Link href={`/games/${g.id}`}
      className={`game-card spot group @container relative block min-h-11 overflow-hidden rounded-lg border bg-surface p-3 pt-0 transition-transform duration-300 hover:-translate-y-1 ${live ? "border-live/60" : "border-line"}`}
      style={gameVars(g.away.tricode, g.home.tricode)}
      aria-label={`${g.away.city} ${g.away.name} at ${g.home.city} ${g.home.name}, ${statusLabel(g)}`}>
      <div className="-mx-3 mb-1 flex items-center justify-between pr-3">
        <span className={`bug label inline-flex min-h-7 items-center gap-1.5 py-1 pl-3 pr-6 font-semibold ${live ? "bug-live" : "bg-surface2 text-fg"}`}>
          {live && <span className="live-dot size-1.5 rounded-full bg-white" aria-hidden />}
          {live ? `LIVE · ${statusLabel(g)}` : statusLabel(g)}
        </span>
        <span className="label text-muted transition-colors group-hover:text-accent">{g.state === "pre" ? "Preview" : "Box score"} ›</span>
      </div>
      <Row t={g.away} lead={awayLead} dim={done && homeLead} show={show} />
      <Row t={g.home} lead={homeLead} dim={done && awayLead} show={show} />
      {show && (
        <div className="mt-2 h-1 overflow-hidden rounded-full bg-line" aria-hidden>
          <div className="game-progress h-full rounded-full" style={{ width: `${Math.round(progress(g) * 100)}%` }} />
        </div>
      )}
      {g.state === "pre" && avail && <Availability a={avail} />}
    </Link>
  );
}
