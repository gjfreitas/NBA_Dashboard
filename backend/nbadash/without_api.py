"""If a star is out: how his teammates have played in the games he missed, compared with the games he played."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import db

MIN_GAMES_WITH_TEAM = 10  # a season counts only if he played this many games for the team in it
MIN_GAMES_WITHOUT = 2  # fewer missed games than this say nothing
SMALL_SAMPLE = 5
MIN_MINUTES = 12  # teammates who barely play are noise
MAX_SEASONS = 2
LIMIT = 8


class Avg(BaseModel):
    games: int
    min: Optional[float]
    pts: Optional[float]
    reb: Optional[float]
    ast: Optional[float]
    usg: Optional[float]


class Teammate(BaseModel):
    player_id: int
    name: str
    with_player: Avg
    without: Avg
    pts_diff: Optional[float]
    min_diff: Optional[float]
    small_sample: bool  # fewer than SMALL_SAMPLE games without him


class Without(BaseModel):
    player_id: int
    name: str
    team_id: Optional[int]
    seasons: list[str]
    games_with: int
    games_without: int
    teammates: list[Teammate]


def _avg(rows: list[sqlite3.Row]) -> Avg:
    def m(key: str) -> Optional[float]:
        xs = [r[key] for r in rows if r[key] is not None]
        return round(sum(xs) / len(xs), 1) if xs else None
    return Avg(games=len(rows), min=m("min"), pts=m("pts"), reb=m("reb"), ast=m("ast"), usg=m("usg_pct"))


def build(conn: sqlite3.Connection, pid: int) -> Optional[Without]:
    me = conn.execute("SELECT id, full_name, team_id FROM players WHERE id=?", (pid,)).fetchone()
    if me is None:
        return None
    team = me["team_id"]
    out = Without(player_id=pid, name=me["full_name"], team_id=team, seasons=[], games_with=0, games_without=0, teammates=[])
    if team is None:
        return out
    # seasons in which he played enough games for his current team, newest first
    seasons = [r["season"] for r in conn.execute(
        "SELECT season FROM player_game_logs WHERE player_id=? AND team_id=? AND season_type='regular' AND min>=1 GROUP BY season HAVING COUNT(*)>=? ORDER BY season DESC LIMIT ?",
        (pid, team, MIN_GAMES_WITH_TEAM, MAX_SEASONS))]
    if not seasons:
        return out
    games_with: set[str] = set()
    games_without: set[str] = set()
    for season in seasons:
        mine = {r["game_id"]: r for r in conn.execute("SELECT game_id, game_date, team_id FROM player_game_logs WHERE player_id=? AND season=? AND season_type='regular' AND min>=1", (pid, season))}
        elsewhere = [r["game_date"] for r in mine.values() if r["team_id"] != team and r["game_date"]]
        first_here = min(r["game_date"] for r in mine.values() if r["team_id"] == team)
        # traded in mid-season: the team's earlier games were played before he arrived, so they say nothing
        anchor = first_here if elsewhere and min(elsewhere) < first_here else ""
        for g in conn.execute("SELECT game_id, game_date FROM team_games WHERE team_id=? AND season=? AND game_date>=?", (team, season, anchor)):
            (games_with if g["game_id"] in mine and mine[g["game_id"]]["team_id"] == team else games_without).add(g["game_id"])
    out.seasons, out.games_with, out.games_without = seasons, len(games_with), len(games_without)
    if len(games_without) < MIN_GAMES_WITHOUT:
        return out
    ids = list(games_with | games_without)
    ph = ",".join("?" * len(ids))
    logs = conn.execute(f"SELECT player_id, game_id, min, pts, reb, ast, usg_pct FROM player_game_logs WHERE team_id=? AND game_id IN ({ph}) AND min>=1 AND player_id<>?", [team, *ids, pid]).fetchall()
    by_player: dict[int, list[sqlite3.Row]] = {}
    for r in logs:
        by_player.setdefault(r["player_id"], []).append(r)
    roster = {r["id"]: r["full_name"] for r in conn.execute("SELECT id, full_name FROM players WHERE team_id=?", (team,))}  # only current teammates
    result = []
    for tid, rows in by_player.items():
        if tid not in roster:
            continue
        w = [r for r in rows if r["game_id"] in games_with]
        wo = [r for r in rows if r["game_id"] in games_without]
        if len(wo) < MIN_GAMES_WITHOUT or not w:
            continue
        a, b = _avg(w), _avg(wo)
        if (b.min or 0) < MIN_MINUTES and (a.min or 0) < MIN_MINUTES:
            continue
        result.append(Teammate(player_id=tid, name=roster[tid], with_player=a, without=b,
                               pts_diff=round(b.pts - a.pts, 1) if a.pts is not None and b.pts is not None else None,
                               min_diff=round(b.min - a.min, 1) if a.min is not None and b.min is not None else None, small_sample=len(wo) < SMALL_SAMPLE))
    result.sort(key=lambda t: (-(t.pts_diff if t.pts_diff is not None else -99), t.name))
    out.teammates = result[:LIMIT]
    return out


def make_router(db_path: Optional[str | Path] = None) -> APIRouter:
    router = APIRouter(prefix="/api/players", tags=["without"])

    def conn() -> Iterator[sqlite3.Connection]:
        c = db.connect(db_path)
        try:
            yield c
        finally:
            c.close()

    @router.get("/{pid}/without", response_model=Without)
    def without(pid: int, c: sqlite3.Connection = Depends(conn)):
        """Teammates' averages in games this player played vs the games his team played without him (his current team, last two seasons)."""
        w = build(c, pid)
        if w is None:
            raise HTTPException(404, "player not found")
        return w

    return router
