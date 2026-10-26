"""Standings, team directory, team roster and team schedule (SQLite-backed)."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import db
from .models import Game, TeamSummary
from .preview_api import MIN_GP, TeamPreview, build_team_preview


class TeamInfo(BaseModel):
    id: int
    abbr: Optional[str]
    city: str
    name: str
    conference: Optional[str]
    division: Optional[str]


class StandingRow(BaseModel):
    team: TeamInfo
    conf_rank: int
    div_rank: int
    league_rank: Optional[int] = None  # only populated by the NBA for some teams; sort by pct instead
    w: int
    l: int
    pct: float
    gb: float  # games back in the conference
    home: str
    road: str
    l10: str
    streak: str
    conf_record: str
    div_record: str
    ppg: float
    opp_ppg: float
    diff: float
    clinch: str  # "" | "z" top seed | "y" division | "x" playoffs | "pi" play-in | "e" eliminated


class Standings(BaseModel):
    season: str
    seasons: list[str]
    min_games: int  # fewest games played by any team (small early in a season)
    teams: list[StandingRow]


class TeamProfile(BaseModel):
    team: TeamInfo
    standing: Optional[StandingRow]
    standings_season: Optional[str]
    stats_season: Optional[str]  # season the per-game stats come from
    is_fallback: bool  # True when last season's stats are shown because the current one is too young
    detail: Optional[TeamPreview]  # stats, league ranks, last-10 form, leaders


class RosterPlayer(BaseModel):
    player_id: int
    name: str
    gp: int
    min: float
    pts: float
    reb: float
    ast: float
    position: Optional[str] = None
    jersey: Optional[str] = None


class Roster(BaseModel):
    season: str
    players: list[RosterPlayer]


class ScheduleGame(BaseModel):
    game_id: str
    date: str
    start_utc: Optional[str]
    status: str  # pre | live | final
    status_text: str
    home: bool  # True when this team is the home team
    opp_id: int
    opp_abbr: str
    opp_name: str
    team_score: Optional[int]
    opp_score: Optional[int]
    result: Optional[str]  # "W" | "L" for finished games
    label: Optional[str]


class Schedule(BaseModel):
    season: str
    seasons: list[str]
    games: list[ScheduleGame]


def make_router(db_path: Optional[str | Path] = None) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["teams"])

    def conn() -> Iterator[sqlite3.Connection]:
        c = db.connect(db_path)
        try:
            yield c
        finally:
            c.close()

    def info(r: sqlite3.Row) -> TeamInfo:
        return TeamInfo(id=r["id"], abbr=r["abbr"], city=r["city"], name=r["name"], conference=r["conference"], division=r["division"])

    def standing(r: sqlite3.Row) -> StandingRow:
        return StandingRow(
            team=info(r), conf_rank=r["conf_rank"], div_rank=r["div_rank"], league_rank=r["league_rank"], w=r["w"], l=r["l"],
            pct=r["pct"], gb=r["gb"], home=r["home"], road=r["road"], l10=r["l10"], streak=r["streak"],
            conf_record=r["conf_record"], div_record=r["div_record"], ppg=r["ppg"], opp_ppg=r["opp_ppg"], diff=r["diff"],
            clinch=r["clinch"] or "")

    def team_row(c: sqlite3.Connection, tid: int) -> sqlite3.Row:
        r = c.execute("SELECT * FROM teams WHERE id=?", (tid,)).fetchone()
        if not r:
            raise HTTPException(404, "team not found (run: python -m nbadash.ingest teams)")
        return r

    def standing_for(c: sqlite3.Connection, tid: int, season: str) -> Optional[StandingRow]:
        r = c.execute("SELECT t.*, s.* FROM standings s JOIN teams t ON t.id = s.team_id "
                      "WHERE s.team_id=? AND s.season=?", (tid, season)).fetchone()
        return standing(r) if r else None

    @router.get("/standings", response_model=Standings)
    def standings(season: Optional[str] = None, c: sqlite3.Connection = Depends(conn)):
        seasons = [r["season"] for r in c.execute("SELECT DISTINCT season FROM standings ORDER BY season DESC")]
        if not seasons:
            raise HTTPException(404, "standings not loaded (run: python -m nbadash.ingest teams)")
        if season is None:
            season = seasons[0]
        elif season not in seasons:
            raise HTTPException(404, f"no standings for {season}")
        rows = c.execute("SELECT t.*, s.* FROM standings s JOIN teams t ON t.id = s.team_id WHERE s.season=? "
                         "ORDER BY t.conference, s.conf_rank", (season,)).fetchall()
        return Standings(season=season, seasons=seasons, min_games=min(r["w"] + r["l"] for r in rows),
                         teams=[standing(r) for r in rows])

    @router.get("/teams", response_model=list[TeamInfo])
    def teams(c: sqlite3.Connection = Depends(conn)):
        return [info(r) for r in c.execute("SELECT * FROM teams ORDER BY city, name")]

    @router.get("/teams/{tid}", response_model=TeamProfile)
    def team(tid: int, c: sqlite3.Connection = Depends(conn)):
        t = team_row(c, tid)
        sseasons = [r["season"] for r in c.execute("SELECT season FROM standings WHERE team_id=? ORDER BY season DESC", (tid,))]
        stat_rows = c.execute("SELECT season, gp FROM team_season WHERE team_id=? ORDER BY season DESC", (tid,)).fetchall()
        stats_season = next((r["season"] for r in stat_rows if r["gp"] >= MIN_GP), stat_rows[0]["season"] if stat_rows else None)
        detail = build_team_preview(c, tid, stats_season, stat_rows[0]["season"]) if stats_season else None
        return TeamProfile(
            team=info(t), standing=standing_for(c, tid, sseasons[0]) if sseasons else None,
            standings_season=sseasons[0] if sseasons else None, stats_season=stats_season,
            is_fallback=bool(stat_rows) and stats_season != stat_rows[0]["season"], detail=detail)

    @router.get("/teams/{tid}/roster", response_model=Roster)
    def roster(tid: int, season: Optional[str] = None, c: sqlite3.Connection = Depends(conn)):
        team_row(c, tid)
        if season is None:
            counts = c.execute("SELECT season, COUNT(*) n FROM league_players WHERE team_id=? GROUP BY season ORDER BY season DESC",
                               (tid,)).fetchall()
            if not counts:
                raise HTTPException(404, "roster not loaded (run: python -m nbadash.ingest teams)")
            # a brand-new season only lists players who have appeared so far; prefer a fuller earlier one
            season = next((r["season"] for r in counts if r["n"] >= 8), counts[0]["season"])
        rows = c.execute(
            """SELECT lp.*, p.position, p.jersey FROM league_players lp LEFT JOIN players p ON p.id = lp.player_id
               WHERE lp.team_id=? AND lp.season=? ORDER BY lp.min * lp.gp DESC""", (tid, season)).fetchall()
        return Roster(season=season, players=[
            RosterPlayer(player_id=r["player_id"], name=r["name"], gp=r["gp"], min=r["min"], pts=r["pts"], reb=r["reb"],
                         ast=r["ast"], position=r["position"] or None, jersey=r["jersey"] or None) for r in rows])

    @router.get("/teams/{tid}/schedule", response_model=Schedule)
    def schedule(tid: int, season: Optional[str] = None, c: sqlite3.Connection = Depends(conn)):
        team_row(c, tid)
        seasons = [r["season"] for r in c.execute("SELECT DISTINCT season FROM schedule ORDER BY season DESC")]
        if not seasons:
            raise HTTPException(404, "schedule not loaded (run: python -m nbadash.ingest teams)")
        season = season or seasons[0]
        # team_games (LeagueGameLog) is fresher than the schedule file for games already played
        rows = c.execute(
            """SELECT s.*, mine.wl AS wl, mine.pts AS my_pts, theirs.pts AS their_pts
               FROM schedule s
               LEFT JOIN team_games mine ON mine.game_id = s.game_id AND mine.team_id = ?
               LEFT JOIN team_games theirs ON theirs.game_id = s.game_id AND theirs.team_id != ?
               WHERE s.season = ? AND (s.home_id = ? OR s.away_id = ?) ORDER BY s.start_utc""",
            (tid, tid, season, tid, tid)).fetchall()
        names = {r["id"]: f"{r['city']} {r['name']}" for r in c.execute("SELECT * FROM teams")}
        out = []
        for r in rows:
            home = r["home_id"] == tid
            final = r["status"] == 3 or r["wl"] is not None
            mine = r["my_pts"] if r["wl"] is not None else (r["home_score"] if home else r["away_score"])
            theirs = r["their_pts"] if r["wl"] is not None else (r["away_score"] if home else r["home_score"])
            status = "final" if final else "live" if r["status"] == 2 else "pre"
            opp = r["away_id"] if home else r["home_id"]
            out.append(ScheduleGame(
                game_id=r["game_id"], date=r["game_date"], start_utc=r["start_utc"], status=status,
                status_text="Final" if final else (r["status_text"] or ""), home=home, opp_id=opp,
                opp_abbr=(r["away_abbr"] if home else r["home_abbr"]), opp_name=names.get(opp, ""),
                team_score=mine if status != "pre" else None, opp_score=theirs if status != "pre" else None,
                result=(r["wl"] if r["wl"] else ("W" if mine > theirs else "L") if final and mine is not None and theirs is not None else None),
                label=r["label"]))
        return Schedule(season=season, seasons=seasons, games=out)

    @router.get("/games/{game_id}/info", response_model=Game)
    def game_info(game_id: str, c: sqlite3.Connection = Depends(conn)):
        """A game from the schedule. Lets the game page (and its Preview tab) open before the game reaches the live scoreboard."""
        g = c.execute("SELECT * FROM schedule WHERE game_id=?", (game_id,)).fetchone()
        if g is None:
            raise HTTPException(404, "game not in the schedule")
        played = {r["team_id"]: r for r in c.execute("SELECT team_id, pts, wl FROM team_games WHERE game_id=?", (game_id,))}
        final = g["status"] == 3 or len(played) == 2  # the game log is fresher than the schedule file

        def team(tid: int, abbr: Optional[str], score: Optional[int]) -> TeamSummary:
            t = c.execute("SELECT * FROM teams WHERE id=?", (tid,)).fetchone()
            rec = c.execute("SELECT w, l FROM standings WHERE team_id=? ORDER BY season DESC LIMIT 1", (tid,)).fetchone()
            pts = played[tid]["pts"] if tid in played else score
            return TeamSummary(id=tid, tricode=(t["abbr"] if t and t["abbr"] else abbr) or "", city=t["city"] if t else "", name=t["name"] if t else "",
                               score=pts or 0, wins=rec["w"] if rec else None, losses=rec["l"] if rec else None)

        return Game(id=game_id, state="final" if final else "live" if g["status"] == 2 else "pre",
                    status_text="Final" if final else (g["status_text"] or ""), period=0, clock="", start_utc=g["start_utc"],
                    home=team(g["home_id"], g["home_abbr"], g["home_score"]), away=team(g["away_id"], g["away_abbr"], g["away_score"]))

    return router
