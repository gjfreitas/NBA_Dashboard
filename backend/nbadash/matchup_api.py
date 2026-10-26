"""Team-vs-team depth for the Preview tab: tempo, how each defence treats guards, forwards and centers, and shot-zone matchups."""
from __future__ import annotations

import math
import sqlite3
from pathlib import Path
from typing import Iterator, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import db

MIN_GP = 10  # same rule as the main preview: a younger season falls back to the previous one
MIN_OPP_MINUTES = 15  # opposing players who played less than this are bench filler
POSITIONS = ("G", "F", "C")
ZONE_ORDER = ["Restricted Area", "In The Paint (Non-RA)", "Mid-Range", "Left Corner 3", "Right Corner 3", "Above the Break 3"]


class Pace(BaseModel):
    home: Optional[float]
    away: Optional[float]
    league: Optional[float]
    expected: Optional[float]  # the average of the two teams' pace
    home_rank: Optional[int]  # 1 = fastest
    away_rank: Optional[int]


class PositionRow(BaseModel):
    position: str  # G, F or C: the position of the opposing players
    pts: float  # per opposing player-game (minimum 15 minutes) this team's defence allows
    reb: float
    ast: float
    league_pts: float
    pts_rank: int  # 1 = allows the fewest points to that position
    games: int  # opposing player-games behind the average


class ZoneRow(BaseModel):
    zone: str
    shot_share: float  # share of the attacking team's shots taken there (current roster)
    league_share: float
    fg_pct_allowed: Optional[float]  # the defending team's opponent FG% there
    league_fg_pct: Optional[float]
    def_rank: Optional[int]  # 1 = allows the lowest FG% in the league


class TeamDepth(BaseModel):
    team_id: int
    abbr: Optional[str]
    defence_by_position: list[PositionRow]
    offence_vs_opponent_zones: list[ZoneRow]  # this team's shots against the OTHER team's defence


class Matchup(BaseModel):
    season: str
    is_fallback: bool
    pace: Pace
    home: TeamDepth
    away: TeamDepth


def pos_letter(position: Optional[str]) -> Optional[str]:
    """'Guard-Forward' -> 'G' (the first listed position)."""
    return {"G": "G", "F": "F", "C": "C"}.get((position or "")[:1].upper())


def _season(conn: sqlite3.Connection, home: int, away: int) -> tuple[str, bool]:
    seasons = [r["season"] for r in conn.execute("SELECT DISTINCT season FROM team_season ORDER BY season DESC")]
    usable = []
    for s in seasons:
        rows = conn.execute("SELECT team_id, gp FROM team_season WHERE season=? AND team_id IN (?,?)", (s, home, away)).fetchall()
        if len(rows) == 2:
            usable.append((s, all((r["gp"] or 0) >= MIN_GP for r in rows)))
    if not usable:
        raise HTTPException(404, "team data not loaded")
    pick = next((s for s, ok in usable if ok), usable[0][0])
    return pick, pick != seasons[0]


def defence_by_position(conn: sqlite3.Connection, season: str) -> dict[int, dict[str, dict]]:
    """{team_id: {position: {pts, reb, ast, n}}}: what each defence allowed to opposing players of each position, per player-game."""
    rows = conn.execute(
        "SELECT tg.team_id AS team, p.position AS position, l.pts AS pts, l.reb AS reb, l.ast AS ast "
        "FROM team_games tg JOIN player_game_logs l ON l.game_id = tg.game_id AND l.team_id <> tg.team_id "
        "JOIN players p ON p.id = l.player_id "
        "WHERE tg.season=? AND l.season_type='regular' AND l.min >= ?", (season, MIN_OPP_MINUTES))
    acc: dict[int, dict[str, list[float]]] = {}
    for r in rows:
        pl = pos_letter(r["position"])
        if pl is None:
            continue
        a = acc.setdefault(r["team"], {}).setdefault(pl, [0, 0, 0, 0])
        a[0] += r["pts"] or 0; a[1] += r["reb"] or 0; a[2] += r["ast"] or 0; a[3] += 1
    return {t: {pos: {"pts": v[0] / v[3], "reb": v[1] / v[3], "ast": v[2] / v[3], "n": v[3]} for pos, v in d.items() if v[3]} for t, d in acc.items()}


def _position_rows(allteams: dict[int, dict[str, dict]], team: int) -> list[PositionRow]:
    out = []
    for pos in POSITIONS:
        mine = allteams.get(team, {}).get(pos)
        if not mine:
            continue
        league = [d[pos]["pts"] for d in allteams.values() if pos in d]
        rank = 1 + sum(1 for x in league if x < mine["pts"])
        out.append(PositionRow(position=pos, pts=round(mine["pts"], 1), reb=round(mine["reb"], 1), ast=round(mine["ast"], 1),
                               league_pts=round(sum(league) / len(league), 1), pts_rank=rank, games=int(mine["n"])))
    return out


def zone_rows(conn: sqlite3.Connection, season: str, attack: int, defend: int) -> list[ZoneRow]:
    """Where `attack` shoots (current roster) against how well `defend` guards each zone."""
    shots = {r["zone"]: r["fga"] for r in conn.execute(
        "SELECT z.zone, SUM(z.fga) AS fga FROM player_zones z JOIN players p ON p.id = z.player_id WHERE p.team_id=? AND z.season=? GROUP BY z.zone", (attack, season))}
    league = {r["zone"]: (r["fga"], r["fgm"]) for r in conn.execute("SELECT zone, SUM(fga) AS fga, SUM(fgm) AS fgm FROM team_zones_def WHERE season=? GROUP BY zone", (season,))}
    pct = {}
    for r in conn.execute("SELECT team_id, zone, fgm, fga FROM team_zones_def WHERE season=?", (season,)):
        if r["fga"]:
            pct.setdefault(r["zone"], {})[r["team_id"]] = r["fgm"] / r["fga"]
    total = sum(shots.values()) or 0
    ltotal = sum(v[0] for v in league.values()) or 0
    out = []
    for zone in ZONE_ORDER:
        if zone not in league:
            continue
        mine = pct.get(zone, {}).get(defend)
        out.append(ZoneRow(zone=zone, shot_share=round(shots.get(zone, 0) / total, 3) if total else 0.0, league_share=round(league[zone][0] / ltotal, 3) if ltotal else 0.0,
                           fg_pct_allowed=round(mine, 3) if mine is not None else None,
                           league_fg_pct=round(league[zone][1] / league[zone][0], 3) if league[zone][0] else None,
                           def_rank=(1 + sum(1 for x in pct[zone].values() if x < mine)) if mine is not None else None))
    return out


def build(conn: sqlite3.Connection, home: int, away: int) -> Matchup:
    season, fallback = _season(conn, home, away)
    ts = {r["team_id"]: r for r in conn.execute("SELECT team_id, pace FROM team_season WHERE season=?", (season,))}
    paces = sorted((r["pace"] for r in ts.values() if r["pace"] is not None), reverse=True)
    pace = lambda t: ts[t]["pace"] if t in ts else None  # noqa: E731
    ph, pa = pace(home), pace(away)
    league = round(sum(paces) / len(paces), 1) if paces else None
    rank = lambda v: (1 + sum(1 for x in paces if x > v)) if v is not None else None  # noqa: E731
    by_pos = defence_by_position(conn, season)
    abbr = lambda t: (conn.execute("SELECT abbr FROM teams WHERE id=?", (t,)).fetchone() or {"abbr": None})["abbr"]  # noqa: E731
    return Matchup(season=season, is_fallback=fallback,
                   pace=Pace(home=ph, away=pa, league=league, expected=round((ph + pa) / 2, 1) if ph is not None and pa is not None else None, home_rank=rank(ph), away_rank=rank(pa)),
                   home=TeamDepth(team_id=home, abbr=abbr(home), defence_by_position=_position_rows(by_pos, home), offence_vs_opponent_zones=zone_rows(conn, season, home, away)),
                   away=TeamDepth(team_id=away, abbr=abbr(away), defence_by_position=_position_rows(by_pos, away), offence_vs_opponent_zones=zone_rows(conn, season, away, home)))


def make_router(db_path: Optional[str | Path] = None) -> APIRouter:
    router = APIRouter(prefix="/api/preview", tags=["preview"])

    def conn() -> Iterator[sqlite3.Connection]:
        c = db.connect(db_path)
        try:
            yield c
        finally:
            c.close()

    @router.get("/matchup", response_model=Matchup)
    def matchup(home: int, away: int, c: sqlite3.Connection = Depends(conn)):
        """Tempo, defence by opposing position, and shot-zone matchups for a game's two teams."""
        return build(c, home, away)

    return router
