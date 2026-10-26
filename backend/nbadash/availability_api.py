"""Injury report + starting lineups over HTTP (SQLite-backed; filled by `nbadash.injuries` and `nbadash.lineups`)."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from . import db
from .injuries import flip, latest_report, norm_name
from .injury_changes import recent_changes

SEVERITY = {"Out": 0, "Doubtful": 1, "Questionable": 2, "Probable": 3, "Available": 4}
POSITION_ORDER = {"PG": 0, "SG": 1, "G": 2, "SF": 3, "PF": 4, "F": 5, "C": 6}
STALE_AFTER_HOURS = 36  # a report older than this is history, not "who is hurt right now"


class InjuryOut(BaseModel):
    player_id: Optional[int]
    name: str
    team_id: Optional[int]
    team_abbr: Optional[str]
    status: str
    reason: str
    matchup: Optional[str]
    game_id: Optional[str]
    game_date: Optional[str]
    game_time: Optional[str]
    espn_return_date: Optional[str] = None  # ESPN's estimated return, when ESPN lists this player


class EspnInjury(BaseModel):
    """One line of ESPN's injury list. Unofficial and in ESPN's own words: status is "Out" or "Day-To-Day"."""
    player_id: Optional[int]
    name: str
    team_id: Optional[int]
    team_abbr: Optional[str]
    status: str
    injury: str
    return_date: Optional[str]  # ESPN's estimate
    updated_at: Optional[str]


class EspnMeta(BaseModel):
    fetched_at: str
    age_minutes: int


class PendingTeam(BaseModel):
    team_id: Optional[int]
    team: Optional[str]
    matchup: Optional[str]
    game_date: Optional[str]


class ReportMeta(BaseModel):
    report_id: str
    published_at: str  # Eastern wall clock
    published_utc: str
    age_minutes: int
    stale: bool


class InjuryReport(BaseModel):
    report: Optional[ReportMeta]
    entries: list[InjuryOut]
    pending: list[PendingTeam]
    espn: list[EspnInjury] = []  # ESPN's list, only for players who are NOT on the official report above
    espn_meta: Optional[EspnMeta] = None


class InjuryChange(BaseModel):
    """A difference between two consecutive official reports."""
    report_id: str
    at: str  # Eastern wall clock of the newer report
    at_utc: str
    kind: str  # added | removed | worsened | improved
    player_id: Optional[int]
    name: str
    team_id: Optional[int]
    team_abbr: Optional[str]
    matchup: Optional[str]
    game_id: Optional[str]
    game_date: Optional[str]
    from_status: Optional[str]
    to_status: Optional[str]
    reason: str


class InjuryChanges(BaseModel):
    changes: list[InjuryChange]
    reports_compared: int  # how many stored reports the window covers (0-1 means there is nothing to compare yet)


class Starter(BaseModel):
    player_id: int
    name: str
    position: Optional[str]
    injury_status: Optional[str]  # a starter who is also on the injury report (e.g. Questionable)
    injury_reason: Optional[str]


class TeamAvailability(BaseModel):
    team_id: int
    abbr: Optional[str]
    name: str
    lineup_status: Optional[str]  # "Expected" | "Confirmed" | None (no lineup published yet)
    lineup_updated: Optional[str]
    starters: list[Starter]
    injuries: list[InjuryOut]
    report_pending: bool  # the team hasn't filed its injury report yet
    espn_only: list[EspnInjury] = []  # on ESPN's list but not on the official report


class GameAvailability(BaseModel):
    game_id: str
    report: Optional[ReportMeta]
    home: TeamAvailability
    away: TeamAvailability


class KeyAbsence(BaseModel):
    player_id: Optional[int]
    name: str
    status: str
    ppg: Optional[float]


class TeamSummary(BaseModel):
    team_id: int
    abbr: Optional[str]
    lineup_status: Optional[str]
    key_players: list[KeyAbsence]  # top scorers who are Out / Doubtful / Questionable, most severe first
    others_out: int  # other players listed Out
    report_pending: bool


class GameSummary(BaseModel):
    game_id: str
    away: TeamSummary
    home: TeamSummary


class PlayerInjury(BaseModel):
    status: str
    reason: str
    matchup: Optional[str]
    game_date: Optional[str]
    reported_at: str
    espn_return_date: Optional[str] = None


def report_meta(rep: Optional[sqlite3.Row], now: Optional[datetime] = None) -> Optional[ReportMeta]:
    if rep is None:
        return None
    age = int(((now or datetime.now(timezone.utc)) - datetime.fromisoformat(rep["published_utc"])).total_seconds() // 60)
    return ReportMeta(report_id=rep["report_id"], published_at=rep["published_at"], published_utc=rep["published_utc"], age_minutes=age,
                      stale=age > STALE_AFTER_HOURS * 60)


def injury_out(r: sqlite3.Row, names: Optional[dict[int, str]] = None, returns: Optional[tuple[dict, dict]] = None) -> InjuryOut:
    name = (names or {}).get(r["player_id"]) or flip(r["player_name"])
    back = None
    if returns:
        back = returns[0].get(r["player_id"]) or returns[1].get(norm_name(flip(r["player_name"])))
    return InjuryOut(player_id=r["player_id"], name=name, team_id=r["team_id"], team_abbr=r["team_abbr"], status=r["status"], reason=r["reason"] or "",
                     matchup=r["matchup"], game_id=r["game_id"], game_date=r["game_date"], game_time=r["game_time"], espn_return_date=back)


def espn_state(conn: sqlite3.Connection, now: Optional[datetime] = None) -> tuple[list[sqlite3.Row], Optional[EspnMeta]]:
    """ESPN's stored list and how old it is. A snapshot older than the staleness limit is ignored (no rows)."""
    last = conn.execute("SELECT synced_at FROM sync WHERE player_id=0 AND kind='espn_injuries'").fetchone()
    if last is None:
        return [], None
    age = int(((now or datetime.now(timezone.utc)) - datetime.fromisoformat(last["synced_at"])).total_seconds() // 60)
    meta = EspnMeta(fetched_at=last["synced_at"], age_minutes=age)
    return ([] if age > STALE_AFTER_HOURS * 60 else conn.execute("SELECT * FROM espn_injuries").fetchall()), meta


def espn_out(r: sqlite3.Row) -> EspnInjury:
    return EspnInjury(player_id=r["player_id"], name=r["player_name"], team_id=r["team_id"], team_abbr=r["team_abbr"], status=r["status"],
                      injury=r["injury"] or "", return_date=r["return_date"], updated_at=r["updated_at"])


def _official_keys(rows: list[sqlite3.Row]) -> tuple[set[int], set[str]]:
    """Who is on the official report: matched ids, and normalised names for the few we couldn't match."""
    return ({r["player_id"] for r in rows if r["player_id"]}, {norm_name(flip(r["player_name"])) for r in rows})


def espn_supplement(espn_rows: list[sqlite3.Row], official: list[sqlite3.Row]) -> list[sqlite3.Row]:
    """ESPN entries for players the official report does not list."""
    ids, names = _official_keys(official)
    return [r for r in espn_rows if not ((r["player_id"] and r["player_id"] in ids) or norm_name(r["player_name"]) in names)]


def espn_return_lookup(espn_rows: list[sqlite3.Row]) -> tuple[dict[int, str], dict[str, str]]:
    by_id = {r["player_id"]: r["return_date"] for r in espn_rows if r["player_id"] and r["return_date"]}
    by_name = {norm_name(r["player_name"]): r["return_date"] for r in espn_rows if r["return_date"]}
    return by_id, by_name


def _names(conn: sqlite3.Connection, rows: list[sqlite3.Row]) -> dict[int, str]:
    ids = sorted({r["player_id"] for r in rows if r["player_id"]})
    if not ids:
        return {}
    return {r["id"]: r["full_name"] for r in conn.execute(f"SELECT id, full_name FROM players WHERE id IN ({','.join('?' * len(ids))})", ids)}


def current_injury(conn: sqlite3.Connection, player_id: int, now: Optional[datetime] = None) -> Optional[PlayerInjury]:
    """The player's line on the newest injury report, if that report is recent enough to mean anything."""
    rep = latest_report(conn)
    meta = report_meta(rep, now)
    if rep is None or meta is None or meta.stale:
        return None
    r = conn.execute("SELECT * FROM injuries WHERE report_id=? AND player_id=? ORDER BY seq LIMIT 1", (rep["report_id"], player_id)).fetchone()
    if r is None:
        return None
    espn_rows, _ = espn_state(conn, now)
    back = espn_return_lookup([e for e in espn_rows if e["player_id"] == player_id])[0].get(player_id)
    return PlayerInjury(status=r["status"], reason=r["reason"] or "", matchup=r["matchup"], game_date=r["game_date"], reported_at=rep["published_at"], espn_return_date=back)


def espn_injury_for(conn: sqlite3.Connection, player_id: int, now: Optional[datetime] = None) -> Optional[EspnInjury]:
    """The player's line on ESPN's list, but only when the official report does not already cover him."""
    rows = [r for r in espn_state(conn, now)[0] if r["player_id"] == player_id]
    if not rows:
        return None
    rep = latest_report(conn)
    meta = report_meta(rep, now)
    if rep is not None and meta is not None and not meta.stale and conn.execute("SELECT 1 FROM injuries WHERE report_id=? AND player_id=?", (rep["report_id"], player_id)).fetchone():
        return None
    return espn_out(rows[0])


KEY_PLAYERS = 5  # "key" means one of the team's five top scorers
MIN_TEAM_GP = 10  # a season this young says little about who the stars are: look at the previous one


def key_scorers(conn: sqlite3.Connection, team_id: int) -> dict[int, float]:
    """The top scorers on the team's CURRENT roster, {player_id: points per game}. Uses the newest season in which the roster has
    played enough games (else the one before); a star traded in the summer counts for his new team."""
    seasons = [r["season"] for r in conn.execute("SELECT DISTINCT season FROM league_players ORDER BY season DESC")]
    for i, season in enumerate(seasons):
        rows = conn.execute("SELECT lp.player_id, lp.pts, lp.gp FROM league_players lp JOIN players p ON p.id = lp.player_id "
                            "WHERE p.team_id=? AND lp.season=? ORDER BY lp.pts DESC", (team_id, season)).fetchall()
        if rows and (max(r["gp"] or 0 for r in rows) >= MIN_TEAM_GP or i == len(seasons) - 1):
            return {r["player_id"]: r["pts"] for r in rows[:KEY_PLAYERS]}
    return {}


def summarize_game(conn: sqlite3.Connection, g: sqlite3.Row, report_rows: list[sqlite3.Row], pending: set, names: dict[int, str]) -> GameSummary:
    def side(team_id: int, abbr: Optional[str]) -> TeamSummary:
        starters = conn.execute("SELECT status FROM lineups WHERE game_id=? AND team_id=? AND starter=1 LIMIT 1", (g["game_id"], team_id)).fetchone()
        key = key_scorers(conn, team_id)
        hurt = [r for r in report_rows if r["team_id"] == team_id and (r["game_id"] in (g["game_id"], None) or r["game_date"] == g["game_date"])
                and r["status"] in ("Out", "Doubtful", "Questionable")]
        hurt.sort(key=lambda r: (SEVERITY.get(r["status"], 9), -(key.get(r["player_id"]) or 0)))
        stars = [r for r in hurt if r["player_id"] in key]
        return TeamSummary(team_id=team_id, abbr=abbr, lineup_status=starters["status"] if starters else None,
                           key_players=[KeyAbsence(player_id=r["player_id"], name=names.get(r["player_id"]) or flip(r["player_name"]), status=r["status"],
                                                   ppg=round(key[r["player_id"]], 1)) for r in stars],
                           others_out=sum(1 for r in hurt if r["status"] == "Out" and r["player_id"] not in key), report_pending=team_id in pending)
    return GameSummary(game_id=g["game_id"], away=side(g["away_id"], g["away_abbr"]), home=side(g["home_id"], g["home_abbr"]))


def summaries_for(conn: sqlite3.Connection, ids: list[str]) -> list[GameSummary]:
    """summarize_game for each id that is in the schedule (unknown ids are skipped), with the injury report read once."""
    rep = latest_report(conn)
    report_rows = conn.execute("SELECT * FROM injuries WHERE report_id=?", (rep["report_id"],)).fetchall() if rep and not report_meta(rep).stale else []
    names = _names(conn, report_rows)
    out = []
    for gid in ids:
        g = conn.execute("SELECT * FROM schedule WHERE game_id=?", (gid,)).fetchone()
        if g is None:
            continue
        pending = {r["team_id"] for r in conn.execute("SELECT team_id FROM injury_pending WHERE report_id=? AND matchup=? AND game_date=?",
                                                       (rep["report_id"], f"{g['away_abbr']}@{g['home_abbr']}", g["game_date"]))} if rep else set()
        out.append(summarize_game(conn, g, report_rows, pending, names))
    return out


def make_router(db_path: Optional[str | Path] = None) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["availability"])

    def conn() -> Iterator[sqlite3.Connection]:
        c = db.connect(db_path)
        try:
            yield c
        finally:
            c.close()

    @router.get("/injuries", response_model=InjuryReport)
    def injuries(team_id: Optional[int] = None, status: Optional[str] = Query(None, pattern="^(Out|Doubtful|Questionable|Probable|Available)$"),
                 c: sqlite3.Connection = Depends(conn)):
        """The newest official report (who is Out / Doubtful / Questionable / Probable), teams that haven't filed yet, and, kept
        separate and labelled, ESPN's list for players the official report doesn't cover."""
        rep = latest_report(c)
        all_official = c.execute("SELECT * FROM injuries WHERE report_id=?", (rep["report_id"],)).fetchall() if rep else []
        espn_rows, espn_meta = espn_state(c)
        if rep is None and not espn_rows:
            return InjuryReport(report=None, entries=[], pending=[], espn_meta=espn_meta)
        rows = [r for r in all_official if (team_id is None or r["team_id"] == team_id) and (status is None or r["status"] == status)]
        names = _names(c, rows)
        rows.sort(key=lambda r: (r["game_date"] or "", r["game_id"] or "", r["team_abbr"] or "", SEVERITY.get(r["status"], 9), r["player_name"]))
        returns = espn_return_lookup(espn_rows)
        extra = [r for r in espn_supplement(espn_rows, all_official) if (team_id is None or r["team_id"] == team_id) and (status is None or r["status"] == status)]
        extra.sort(key=lambda r: (r["status"] != "Out", r["team_name"] or "", r["player_name"]))
        pend = c.execute("SELECT p.*, t.abbr FROM injury_pending p LEFT JOIN teams t ON t.id = p.team_id WHERE p.report_id=?"
                         + (" AND p.team_id=?" if team_id is not None else ""),
                         [rep["report_id"]] + ([team_id] if team_id is not None else [])).fetchall() if rep else []
        return InjuryReport(report=report_meta(rep), entries=[injury_out(r, names, returns) for r in rows],
                            pending=[PendingTeam(team_id=p["team_id"], team=p["abbr"] or p["team_name"], matchup=p["matchup"], game_date=p["game_date"]) for p in pend],
                            espn=[espn_out(r) for r in extra], espn_meta=espn_meta)

    @router.get("/injuries/changes", response_model=InjuryChanges)
    def injury_changes(hours: float = Query(24, gt=0, le=72), team_id: Optional[int] = None, game_id: Optional[str] = None,
                       limit: int = Query(100, ge=1, le=500), c: sqlite3.Connection = Depends(conn)):
        """Who was added, removed, or moved between statuses from one official report to the next, newest first."""
        events = [e for e in recent_changes(c, hours) if (team_id is None or e["team_id"] == team_id) and (game_id is None or e["game_id"] == game_id)]
        rows = [{"player_id": e["player_id"]} for e in events]
        names = _names(c, rows)
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")
        n = c.execute("SELECT COUNT(*) FROM injury_reports WHERE published_utc >= ?", (cutoff,)).fetchone()[0]
        return InjuryChanges(reports_compared=n, changes=[
            InjuryChange(name=names.get(e["player_id"]) or flip(e["player_name"]), **{k: v for k, v in e.items() if k != "player_name"})
            for e in events[:limit]])

    @router.get("/availability/summary", response_model=list[GameSummary])
    def summary(game_ids: str = Query(..., description="comma-separated game ids, at most 40"), c: sqlite3.Connection = Depends(conn)):
        """One compact line per game for the scoreboard: lineup status, and which of each team's top scorers are on the injury report."""
        ids = [i for i in dict.fromkeys(x.strip() for x in game_ids.split(",")) if i]
        if len(ids) > 40:
            raise HTTPException(422, "at most 40 game ids")
        return summaries_for(c, ids)

    @router.get("/games/{game_id}/availability", response_model=GameAvailability)
    def availability(game_id: str, c: sqlite3.Connection = Depends(conn)):
        """Starters (expected or confirmed) and injury report lines for both teams of a game."""
        g = c.execute("SELECT * FROM schedule WHERE game_id=?", (game_id,)).fetchone()
        if g is None:
            raise HTTPException(404, "game not in the schedule")
        rep = latest_report(c)
        report_rows = c.execute("SELECT * FROM injuries WHERE report_id=?", (rep["report_id"],)).fetchall() if rep else []
        names = _names(c, report_rows)
        # "not yet submitted" is per team AND per game: a team can have filed for tonight but not for tomorrow
        pending = {r["team_id"] for r in c.execute("SELECT team_id FROM injury_pending WHERE report_id=? AND matchup=? AND game_date=?",
                                                    (rep["report_id"], f"{g['away_abbr']}@{g['home_abbr']}", g["game_date"]))} if rep else set()
        by_player = {r["player_id"]: r for r in report_rows if r["player_id"]}
        espn_rows, _ = espn_state(c)
        espn_extra = espn_supplement(espn_rows, report_rows)
        returns = espn_return_lookup(espn_rows)

        def side(team_id: int) -> TeamAvailability:
            t = c.execute("SELECT * FROM teams WHERE id=?", (team_id,)).fetchone()
            starters = c.execute("SELECT * FROM lineups WHERE game_id=? AND team_id=? AND starter=1", (game_id, team_id)).fetchall()
            starters.sort(key=lambda r: (POSITION_ORDER.get(r["position"], 9), r["name"] or ""))
            hurt = [r for r in report_rows if r["team_id"] == team_id and (r["game_id"] in (game_id, None) or r["game_date"] == g["game_date"])]
            hurt.sort(key=lambda r: (SEVERITY.get(r["status"], 9), r["player_name"]))
            return TeamAvailability(
                team_id=team_id, abbr=t["abbr"] if t else None, name=f"{t['city']} {t['name']}" if t else str(team_id),
                lineup_status=starters[0]["status"] if starters else None, lineup_updated=starters[0]["file_timestamp"] if starters else None,
                starters=[Starter(player_id=s["player_id"], name=s["name"] or "", position=s["position"],
                                  injury_status=by_player[s["player_id"]]["status"] if s["player_id"] in by_player else None,
                                  injury_reason=(by_player[s["player_id"]]["reason"] or None) if s["player_id"] in by_player else None) for s in starters],
                injuries=[injury_out(r, names, returns) for r in hurt], report_pending=team_id in pending,
                espn_only=[espn_out(r) for r in sorted(espn_extra, key=lambda r: (r["status"] != "Out", r["player_name"])) if r["team_id"] == team_id])

        return GameAvailability(game_id=game_id, report=report_meta(rep), home=side(g["home_id"]), away=side(g["away_id"]))

    return router
