"""Read-only player endpoints backed by SQLite."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from . import db
from .availability_api import EspnInjury, PlayerInjury, current_injury, espn_injury_for


class PlayerSummary(BaseModel):
    id: int
    name: str
    is_active: bool
    team: Optional[str] = None  # tricode
    position: Optional[str] = None
    jersey: Optional[str] = None


class SeasonLine(BaseModel):
    season: str  # "2025-26" or "Career"
    season_type: str
    team: str  # tricode; "TOT" = traded-player total row
    age: Optional[float] = None
    gp: int
    gs: int
    # per game
    mpg: float
    ppg: float
    rpg: float
    apg: float
    spg: float
    bpg: float
    tpg: float
    # shooting
    fg_pct: Optional[float]
    fg3_pct: Optional[float]
    ft_pct: Optional[float]
    efg_pct: Optional[float]
    ts_pct: Optional[float]
    # totals
    pts: int
    reb: int
    ast: int


class DataAvailability(BaseModel):
    season: str
    season_type: str
    games: int
    shots: int


class PlayerProfile(PlayerSummary):
    full_bio_loaded: bool
    birthdate: Optional[str] = None
    age: Optional[int] = None
    country: Optional[str] = None
    school: Optional[str] = None
    height: Optional[str] = None
    weight: Optional[str] = None
    team_name: Optional[str] = None
    draft: Optional[str] = None
    from_year: Optional[int] = None
    to_year: Optional[int] = None
    greatest_75: bool = False
    regular: list[SeasonLine] = []
    playoffs: list[SeasonLine] = []
    career_regular: Optional[SeasonLine] = None
    career_playoffs: Optional[SeasonLine] = None
    available: list[DataAvailability] = []
    injury: Optional[PlayerInjury] = None  # from the newest official injury report, if recent
    espn_injury: Optional[EspnInjury] = None  # ESPN's list, only when the official report doesn't cover the player


class GameLogRow(BaseModel):
    game_id: str
    date: str
    matchup: str
    result: Optional[str]
    min: float
    pts: int
    reb: int
    ast: int
    stl: int
    blk: int
    tov: int
    pf: int
    fgm: int
    fga: int
    fg3m: int
    fg3a: int
    ftm: int
    fta: int
    plus_minus: int


class Shot(BaseModel):
    game_id: str
    period: int
    clock: str
    action: str
    shot_type: str
    zone: str
    distance: int
    x: int  # tenths of a foot from the rim; +x = shooter's right of centre line
    y: int  # tenths of a foot from the rim toward half court
    made: bool


class ZoneSummary(BaseModel):
    zone: str
    attempts: int
    made: int
    fg_pct: float


class ShotChart(BaseModel):
    season: str
    season_type: str
    attempts: int
    made: int
    fg_pct: Optional[float]
    zones: list[ZoneSummary]
    shots: list[Shot]


def _div(a: float, b: float) -> Optional[float]:
    return round(a / b, 3) if b else None


def season_line(r: sqlite3.Row) -> SeasonLine:
    gp = r["gp"] or 0
    pg = lambda k: round((r[k] or 0) / gp, 1) if gp else 0.0  # noqa: E731
    fga, fta, fgm, fg3m = (r[k] or 0 for k in ("fga", "fta", "fgm", "fg3m"))
    mpg = round((r["min"] or 0) / gp, 1) if gp else 0.0
    return SeasonLine(
        season=r["season"], season_type=r["season_type"], team=r["team_abbr"] or "", age=r["age"],
        gp=gp, gs=r["gs"] or 0, mpg=mpg, ppg=pg("pts"), rpg=pg("reb"), apg=pg("ast"), spg=pg("stl"),
        bpg=pg("blk"), tpg=pg("tov"),
        fg_pct=_div(fgm, fga), fg3_pct=_div(fg3m, r["fg3a"] or 0), ft_pct=_div(r["ftm"] or 0, fta),
        efg_pct=_div(fgm + 0.5 * fg3m, fga), ts_pct=_div(r["pts"] or 0, 2 * (fga + 0.44 * fta)),
        pts=r["pts"] or 0, reb=r["reb"] or 0, ast=r["ast"] or 0,
    )


def _age(birthdate: Optional[str]) -> Optional[int]:
    if not birthdate:
        return None
    from datetime import date
    b = date.fromisoformat(birthdate)
    t = date.today()
    return t.year - b.year - ((t.month, t.day) < (b.month, b.day))


def make_router(db_path: Optional[str | Path] = None) -> APIRouter:
    router = APIRouter(prefix="/api/players", tags=["players"])

    def conn() -> Iterator[sqlite3.Connection]:
        c = db.connect(db_path)
        try:
            yield c
        finally:
            c.close()

    def summary(r: sqlite3.Row) -> PlayerSummary:
        return PlayerSummary(id=r["id"], name=r["full_name"], is_active=bool(r["is_active"]),
                             team=r["team_abbr"], position=r["position"], jersey=r["jersey"])

    @router.get("", response_model=list[PlayerSummary])
    def search(q: str = Query("", max_length=60), active: bool = True, limit: int = Query(30, ge=1, le=100),
               c: sqlite3.Connection = Depends(conn)):
        """Name search (case- and accent-insensitive substring). Players with loaded data sort first."""
        esc = db.fold_text(q.strip()).replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
        sql = ("SELECT p.*, EXISTS(SELECT 1 FROM sync s WHERE s.player_id=p.id AND s.kind='info') AS loaded "
               r"FROM players p WHERE fold(p.full_name) LIKE ? ESCAPE '\'" + (" AND p.is_active=1" if active else "") +
               " ORDER BY loaded DESC, p.full_name LIMIT ?")
        like = f"%{esc}%"
        return [summary(r) for r in c.execute(sql, (like, limit))]

    def _player(c: sqlite3.Connection, pid: int) -> sqlite3.Row:
        r = c.execute("SELECT * FROM players WHERE id=?", (pid,)).fetchone()
        if not r:
            raise HTTPException(404, "player not found")
        return r

    @router.get("/{pid}", response_model=PlayerProfile)
    def profile(pid: int, c: sqlite3.Connection = Depends(conn)):
        p = _player(c, pid)
        loaded = bool(c.execute("SELECT 1 FROM sync WHERE player_id=? AND kind='info'", (pid,)).fetchone())
        seasons = c.execute(
            "SELECT * FROM player_seasons WHERE player_id=? ORDER BY season, team_abbr='TOT' DESC, team_abbr", (pid,)).fetchall()
        lines = [season_line(r) for r in seasons]
        avail = c.execute(
            """SELECT l.season, l.season_type, COUNT(*) AS games,
                      (SELECT COUNT(*) FROM player_shots s WHERE s.player_id=l.player_id AND s.season=l.season
                         AND s.season_type=l.season_type) AS shots
               FROM player_game_logs l WHERE l.player_id=? GROUP BY l.season, l.season_type
               ORDER BY l.season DESC, l.season_type DESC""", (pid,)).fetchall()
        draft = None
        if p["draft_year"] and p["draft_year"] != "Undrafted":
            draft = f"{p['draft_year']} · Round {p['draft_round']} · Pick {p['draft_number']}"
        elif loaded:
            draft = "Undrafted"
        return PlayerProfile(
            **summary(p).model_dump(), full_bio_loaded=loaded, birthdate=p["birthdate"], age=_age(p["birthdate"]),
            country=p["country"], school=p["school"], height=p["height"], weight=p["weight"],
            team_name=(f"{p['team_city']} {p['team_name']}" if p["team_name"] else None), draft=draft,
            from_year=p["from_year"], to_year=p["to_year"], greatest_75=bool(p["greatest_75"]),
            regular=[x for x in lines if x.season_type == "regular" and x.season != "Career"],
            playoffs=[x for x in lines if x.season_type == "playoffs" and x.season != "Career"],
            career_regular=next((x for x in lines if x.season_type == "regular" and x.season == "Career"), None),
            career_playoffs=next((x for x in lines if x.season_type == "playoffs" and x.season == "Career"), None),
            available=[DataAvailability(**dict(r)) for r in avail],
            injury=current_injury(c, pid), espn_injury=espn_injury_for(c, pid),
        )

    @router.get("/{pid}/gamelog", response_model=list[GameLogRow])
    def gamelog(pid: int, season: str, season_type: str = "regular", c: sqlite3.Connection = Depends(conn)):
        _player(c, pid)
        q = ("SELECT * FROM player_game_logs WHERE player_id=? AND season=? AND season_type=? "
             "ORDER BY game_date DESC")
        return [GameLogRow(game_id=r["game_id"], date=r["game_date"], matchup=r["matchup"], result=r["wl"],
                           min=r["min"] or 0, pts=r["pts"], reb=r["reb"], ast=r["ast"], stl=r["stl"], blk=r["blk"],
                           tov=r["tov"], pf=r["pf"], fgm=r["fgm"], fga=r["fga"], fg3m=r["fg3m"], fg3a=r["fg3a"],
                           ftm=r["ftm"], fta=r["fta"], plus_minus=r["plus_minus"] or 0)
                for r in c.execute(q, (pid, season, season_type))]

    @router.get("/{pid}/shots", response_model=ShotChart)
    def shots(pid: int, season: str, season_type: str = "regular", c: sqlite3.Connection = Depends(conn)):
        _player(c, pid)
        data = c.execute("SELECT * FROM player_shots WHERE player_id=? AND season=? AND season_type=? "
                         "ORDER BY game_date, game_id, period, min_rem DESC, sec_rem DESC",
                         (pid, season, season_type)).fetchall()
        zones: dict[str, list[int]] = {}
        for r in data:
            z = zones.setdefault(r["zone_basic"], [0, 0])
            z[0] += 1
            z[1] += r["made"]
        made = sum(r["made"] for r in data)
        return ShotChart(
            season=season, season_type=season_type, attempts=len(data), made=made, fg_pct=_div(made, len(data)),
            zones=sorted((ZoneSummary(zone=k, attempts=a, made=m, fg_pct=round(m / a, 3)) for k, (a, m) in zones.items()),
                         key=lambda z: -z.attempts),
            shots=[Shot(game_id=r["game_id"], period=r["period"], clock=f"{r['min_rem']}:{r['sec_rem']:02d}",
                        action=r["action_type"], shot_type=r["shot_type"], zone=r["zone_basic"],
                        distance=r["distance"], x=r["x"], y=r["y"], made=bool(r["made"])) for r in data],
        )

    return router
