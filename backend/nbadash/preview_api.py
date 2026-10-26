"""Game preview: team comparison, recent form, season series and team leaders (SQLite-backed)."""
from __future__ import annotations

import math
import sqlite3
from datetime import date as Date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Iterator, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import db

MIN_GP = 10  # below this a team's per-game stats are too noisy; fall back to the previous season
STAT_KEYS = ("pts", "reb", "ast", "stl", "blk", "tov", "fg_pct", "fg3_pct", "ft_pct", "off_rtg", "def_rtg", "net_rtg", "pace", "ts_pct")
RANK_KEYS = ("pts", "reb", "ast", "fg_pct", "fg3_pct", "off_rtg", "def_rtg", "net_rtg", "pace")


class Leader(BaseModel):
    player_id: int
    name: str
    gp: int
    pts: float
    reb: float
    ast: float


class FormGame(BaseModel):
    date: str
    opp: str
    home: bool
    result: Optional[str]
    pts: int
    margin: int


class Record(BaseModel):
    w: int
    l: int
    margin: Optional[float]  # average points margin in those games


class Context(BaseModel):
    """Schedule context for one team going into the game (from games already played this season)."""
    last_game_date: Optional[str]
    days_rest: Optional[int]  # full days off since the last game; 0 means played yesterday
    back_to_back: bool
    games_last_7: int  # games in the 7 days before this one
    streak: Optional[str]  # "W3", "L2"
    home: Record
    away: Record
    last5: Optional[Record]


class TeamPreview(BaseModel):
    team_id: int
    abbr: Optional[str]
    name: str
    wins: int  # record in the stats season
    losses: int
    current_wins: Optional[int]  # record in the newest season with data (may differ early in a season)
    current_losses: Optional[int]
    stats: dict[str, Optional[float]]
    ranks: dict[str, Optional[int]]
    form: list[FormGame]
    leaders: list[Leader]
    context: Optional[Context] = None


class SeriesGame(BaseModel):
    date: str
    season: str
    home_abbr: str
    away_abbr: str
    home_pts: int
    away_pts: int
    winner_id: int


class Series(BaseModel):
    games: list[SeriesGame]
    home_wins: int
    away_wins: int


class Preview(BaseModel):
    season: str  # season the comparison stats come from
    is_fallback: bool  # True when the newest season is too young and last season's stats are shown
    home: TeamPreview
    away: TeamPreview
    series: Series


def build_team_preview(c: sqlite3.Connection, tid: int, season: str, newest: str) -> TeamPreview:
    r = c.execute("SELECT * FROM team_season WHERE team_id=? AND season=?", (tid, season)).fetchone()
    cur = c.execute("SELECT w, l FROM team_season WHERE team_id=? AND season=?", (tid, newest)).fetchone()
    ab = c.execute("SELECT abbr FROM team_games WHERE team_id=? ORDER BY game_date DESC LIMIT 1", (tid,)).fetchone()
    form = c.execute(
        "SELECT * FROM team_games WHERE team_id=? ORDER BY game_date DESC LIMIT 10", (tid,)).fetchall()
    min_gp = max(1, math.ceil(0.3 * (r["gp"] or 0)))
    leaders = c.execute(
        "SELECT * FROM league_players WHERE team_id=? AND season=? AND gp>=? ORDER BY pts DESC LIMIT 3",
        (tid, season, min_gp)).fetchall()
    return TeamPreview(
        team_id=tid, abbr=ab["abbr"] if ab else None, name=r["name"], wins=r["w"], losses=r["l"],
        current_wins=cur["w"] if cur else None, current_losses=cur["l"] if cur else None,
        stats={k: r[k] for k in STAT_KEYS}, ranks={k: r[f"{k}_rank"] for k in RANK_KEYS},
        form=[FormGame(date=g["game_date"], opp=g["opp_abbr"], home=bool(g["home"]), result=g["wl"],
                       pts=g["pts"], margin=g["plus_minus"]) for g in form],
        leaders=[Leader(player_id=p["player_id"], name=p["name"], gp=p["gp"], pts=p["pts"], reb=p["reb"], ast=p["ast"])
                 for p in leaders],
    )


def build_context(c: sqlite3.Connection, tid: int, season: str, on: Date) -> Optional[Context]:
    """Rest, streak and home/away splits from the team's games in `season` played before `on`."""
    games = c.execute("SELECT game_date, home, wl, plus_minus FROM team_games WHERE team_id=? AND season=? AND game_date<? ORDER BY game_date DESC",
                      (tid, season, on.isoformat())).fetchall()
    if not games:
        return None

    def rec(rows) -> Record:
        w = sum(1 for g in rows if g["wl"] == "W")
        margins = [g["plus_minus"] for g in rows if g["plus_minus"] is not None]
        return Record(w=w, l=len(rows) - w, margin=round(sum(margins) / len(margins), 1) if margins else None)

    last = Date.fromisoformat(games[0]["game_date"])
    run = 0
    for g in games:
        if g["wl"] != games[0]["wl"]:
            break
        run += 1
    week_ago = (on - timedelta(days=7)).isoformat()
    days_rest = (on - last).days - 1
    return Context(last_game_date=games[0]["game_date"], days_rest=days_rest, back_to_back=days_rest == 0,
                   games_last_7=sum(1 for g in games if g["game_date"] >= week_ago),
                   streak=f"{games[0]['wl']}{run}" if games[0]["wl"] else None,
                   home=rec([g for g in games if g["home"]]), away=rec([g for g in games if not g["home"]]), last5=rec(games[:5]))


def make_router(db_path: Optional[str | Path] = None) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["preview"])

    def conn() -> Iterator[sqlite3.Connection]:
        c = db.connect(db_path)
        try:
            yield c
        finally:
            c.close()

    @router.get("/preview", response_model=Preview)
    def preview(home: int, away: int, game_id: Optional[str] = None, c: sqlite3.Connection = Depends(conn)):
        seasons = [r["season"] for r in c.execute("SELECT DISTINCT season FROM team_season ORDER BY season DESC")]
        both = {s: c.execute("SELECT team_id, gp FROM team_season WHERE season=? AND team_id IN (?,?)", (s, home, away)).fetchall()
                for s in seasons}
        usable = [s for s in seasons if len(both[s]) == 2]
        if not usable:
            raise HTTPException(404, "team data not loaded (run: python -m nbadash.ingest teams)")
        season = next((s for s in usable if all(t["gp"] >= MIN_GP for t in both[s])), usable[0])
        newest = seasons[0]
        h, a = build_team_preview(c, home, season, newest), build_team_preview(c, away, season, newest)
        # rest and splits describe the games of the newest season that were played before this game (today, if the game isn't in the schedule)
        g = c.execute("SELECT game_date FROM schedule WHERE game_id=?", (game_id,)).fetchone() if game_id else None
        on = Date.fromisoformat(g["game_date"]) if g else datetime.now(ZoneInfo("America/New_York")).date()
        h.context, a.context = build_context(c, home, newest, on), build_context(c, away, newest, on)

        games = []
        if h.abbr and a.abbr:
            rows = c.execute(
                """SELECT x.game_date, x.season, x.home, x.pts AS hp, y.pts AS ap, x.wl
                   FROM team_games x JOIN team_games y ON y.game_id = x.game_id AND y.team_id = ?
                   WHERE x.team_id = ? AND x.season IN (?, ?) ORDER BY x.game_date DESC""",
                (away, home, newest, season)).fetchall()
            for g in rows:
                home_court = bool(g["home"])
                games.append(SeriesGame(
                    date=g["game_date"], season=g["season"],
                    home_abbr=h.abbr if home_court else a.abbr, away_abbr=a.abbr if home_court else h.abbr,
                    home_pts=g["hp"] if home_court else g["ap"], away_pts=g["ap"] if home_court else g["hp"],
                    winner_id=home if g["hp"] > g["ap"] else away))
        return Preview(season=season, is_fallback=season != newest, home=h, away=a,
                       series=Series(games=games, home_wins=sum(g.winner_id == home for g in games),
                                     away_wins=sum(g.winner_id == away for g in games)))

    return router
