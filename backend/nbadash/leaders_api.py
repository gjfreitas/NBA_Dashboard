"""League leaderboards: every player (from the league-wide game logs) and every team (from team season stats)."""
from __future__ import annotations

import math
import sqlite3
from pathlib import Path
from typing import Iterator, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from . import db

# NBA leaderboard qualification, scaled to the games a team has actually played so far (82-game season rules):
QUALIFY_GAMES = 0.70       # 58 of 82 games for per-game stats
FGM_PER_TEAM_GAME = 300 / 82   # 300 made field goals for FG%, eFG%, TS%
FG3M_PER_TEAM_GAME = 82 / 82   # 82 made threes for 3P%
FTM_PER_TEAM_GAME = 125 / 82   # 125 made free throws for FT%

# stat key -> (label, group). Counting stats can be shown per game or as totals; the rest are rates.
PLAYER_STATS: dict[str, tuple[str, str]] = {
    "pts": ("Points", "count"), "reb": ("Rebounds", "count"), "ast": ("Assists", "count"), "stl": ("Steals", "count"),
    "blk": ("Blocks", "count"), "fg3m": ("Threes made", "count"), "tov": ("Turnovers", "count"), "min": ("Minutes", "count"),
    "pra": ("Pts+Reb+Ast", "count"), "fgm": ("FG made", "count"), "fga": ("FG attempted", "count"), "ftm": ("FT made", "count"),
    "fta": ("FT attempted", "count"),
    "fg_pct": ("FG%", "fg"), "fg3_pct": ("3P%", "fg3"), "ft_pct": ("FT%", "ft"), "efg_pct": ("eFG%", "fg"), "ts_pct": ("TS%", "fg"),
    "usg": ("Usage %", "gp"), "dd": ("Double-doubles", "total"), "td": ("Triple-doubles", "total"),
}

# team stat -> (label, lower_is_better)
TEAM_STATS: dict[str, tuple[str, bool]] = {
    "pts": ("Points", False), "reb": ("Rebounds", False), "ast": ("Assists", False), "stl": ("Steals", False), "blk": ("Blocks", False),
    "tov": ("Turnovers", True), "fg_pct": ("FG%", False), "fg3_pct": ("3P%", False), "ft_pct": ("FT%", False), "ts_pct": ("TS%", False),
    "off_rtg": ("Offensive rating", False), "def_rtg": ("Defensive rating", True), "net_rtg": ("Net rating", False), "pace": ("Pace", False),
    "plus_minus": ("Point differential", False),
}


class PlayerLeader(BaseModel):
    rank: int
    player_id: int
    name: str
    team_abbr: Optional[str]
    position: Optional[str]
    gp: int
    value: float
    min: float
    pts: float
    reb: float
    ast: float
    stl: float
    blk: float
    tov: float
    fg3m: float
    fg_pct: Optional[float]
    fg3_pct: Optional[float]
    ft_pct: Optional[float]
    ts_pct: Optional[float]
    usg: Optional[float]
    dd: int
    td: int


class PlayerLeaders(BaseModel):
    season: str
    seasons: list[str]
    season_type: str
    stat: str
    label: str
    mode: str  # "pg" | "total"
    qualified: bool
    requirement: Optional[str]  # human-readable qualification rule that was applied
    team_games: int  # most games any team has played in this season/type
    total: int  # players that made the list
    rows: list[PlayerLeader]


class TeamLeader(BaseModel):
    rank: int
    team_id: int
    abbr: Optional[str]
    name: str
    conference: Optional[str]
    w: int
    l: int
    value: Optional[float]
    stats: dict[str, Optional[float]]


class TeamLeaders(BaseModel):
    season: str
    seasons: list[str]
    stat: str
    label: str
    lower_is_better: bool
    team_games: int
    rows: list[TeamLeader]


def _div(a: float, b: float) -> Optional[float]:
    return a / b if b else None


def make_router(db_path: Optional[str | Path] = None) -> APIRouter:
    router = APIRouter(prefix="/api/leaders", tags=["leaders"])

    def conn() -> Iterator[sqlite3.Connection]:
        c = db.connect(db_path)
        try:
            yield c
        finally:
            c.close()

    @router.get("/players", response_model=PlayerLeaders)
    def players(stat: str = "pts", season: Optional[str] = None, season_type: str = Query("regular", pattern="^(regular|playoffs)$"),
                mode: str = Query("pg", pattern="^(pg|total)$"), qualified: bool = True, limit: int = Query(25, ge=1, le=300),
                c: sqlite3.Connection = Depends(conn)):
        if stat not in PLAYER_STATS:
            raise HTTPException(422, f"unknown stat '{stat}'")
        seasons = [r["season"] for r in c.execute("SELECT DISTINCT season FROM player_game_logs WHERE team_id IS NOT NULL ORDER BY season DESC")]
        if not seasons:
            raise HTTPException(404, "no game logs (run: python -m nbadash.ingest props)")
        if season is None:
            season = seasons[0]
        elif season not in seasons:
            raise HTTPException(404, f"no data for {season}")

        team_games = {r["team_id"]: r["g"] for r in c.execute(
            "SELECT team_id, COUNT(DISTINCT game_id) g FROM player_game_logs WHERE season=? AND season_type=? AND team_id IS NOT NULL GROUP BY team_id",
            (season, season_type))}
        league_games = max(team_games.values(), default=0)

        agg = c.execute(
            """SELECT l.player_id, COUNT(*) gp, SUM(l.min) min, SUM(l.pts) pts, SUM(l.reb) reb, SUM(l.ast) ast, SUM(l.stl) stl, SUM(l.blk) blk,
                      SUM(l.tov) tov, SUM(l.fgm) fgm, SUM(l.fga) fga, SUM(l.fg3m) fg3m, SUM(l.fg3a) fg3a, SUM(l.ftm) ftm, SUM(l.fta) fta,
                      SUM(CASE WHEN l.usg_pct IS NOT NULL THEN l.usg_pct * l.min END) usg_w,
                      SUM(CASE WHEN l.usg_pct IS NOT NULL THEN l.min END) usg_min,
                      SUM(((l.pts >= 10) + (l.reb >= 10) + (l.ast >= 10) + (l.stl >= 10) + (l.blk >= 10)) >= 2) dd,
                      SUM(((l.pts >= 10) + (l.reb >= 10) + (l.ast >= 10) + (l.stl >= 10) + (l.blk >= 10)) >= 3) td,
                      (SELECT x.team_id FROM player_game_logs x WHERE x.player_id = l.player_id AND x.season = l.season
                         AND x.season_type = l.season_type ORDER BY x.game_date DESC LIMIT 1) team_id
               FROM player_game_logs l WHERE l.season=? AND l.season_type=? GROUP BY l.player_id""", (season, season_type)).fetchall()
        who = {r["id"]: r for r in c.execute("SELECT id, full_name, position FROM players")}
        abbr = {r["id"]: r["abbr"] for r in c.execute("SELECT id, abbr FROM teams")}

        group = PLAYER_STATS[stat][1]
        rows = []
        for r in agg:
            gp = r["gp"]
            tg = team_games.get(r["team_id"], league_games)  # a player is judged against the games HIS team has played
            if qualified:
                if mode == "pg" and group not in ("total",) and gp < max(1, math.ceil(QUALIFY_GAMES * tg)):
                    continue
                if group == "fg" and (r["fgm"] or 0) < FGM_PER_TEAM_GAME * tg:
                    continue
                if group == "fg3" and (r["fg3m"] or 0) < FG3M_PER_TEAM_GAME * tg:
                    continue
                if group == "ft" and (r["ftm"] or 0) < FTM_PER_TEAM_GAME * tg:
                    continue
            per = (lambda v: (v or 0) / gp) if mode == "pg" else (lambda v: float(v or 0))
            fga, fta = r["fga"] or 0, r["fta"] or 0
            s = {
                "min": per(r["min"]), "pts": per(r["pts"]), "reb": per(r["reb"]), "ast": per(r["ast"]), "stl": per(r["stl"]), "blk": per(r["blk"]),
                "tov": per(r["tov"]), "fg3m": per(r["fg3m"]), "fgm": per(r["fgm"]), "fga": per(r["fga"]), "ftm": per(r["ftm"]), "fta": per(r["fta"]),
                "pra": per((r["pts"] or 0) + (r["reb"] or 0) + (r["ast"] or 0)),
                "fg_pct": _div(r["fgm"] or 0, fga), "fg3_pct": _div(r["fg3m"] or 0, r["fg3a"] or 0), "ft_pct": _div(r["ftm"] or 0, fta),
                "efg_pct": _div((r["fgm"] or 0) + 0.5 * (r["fg3m"] or 0), fga), "ts_pct": _div(r["pts"] or 0, 2 * (fga + 0.44 * fta)),
                "usg": (r["usg_w"] / r["usg_min"] * 100) if r["usg_min"] else None, "dd": int(r["dd"] or 0), "td": int(r["td"] or 0),
            }
            if s[stat] is None or (group != "total" and (r["min"] or 0) <= 0):
                continue
            if stat in ("fg_pct", "fg3_pct", "ft_pct", "efg_pct", "ts_pct") and not qualified and (fga if stat != "fg3_pct" else r["fg3a"] or 0) == 0:
                continue
            if group == "total" and s[stat] == 0:
                continue  # nobody wants a leaderboard of zeros
            rows.append((s[stat], r["pts"] or 0, r["player_id"], r["team_id"], gp, s))

        # best first; ties broken by total points (then id) so the order is stable
        rows.sort(key=lambda t: (-t[0], -t[1], t[2]))
        out = []
        for i, (value, _, pid, tid, gp, s) in enumerate(rows[:limit], 1):
            p = who.get(pid)
            out.append(PlayerLeader(
                rank=i, player_id=pid, name=p["full_name"] if p else f"Player {pid}", team_abbr=abbr.get(tid), position=p["position"] if p else None,
                gp=gp, value=value, min=s["min"], pts=s["pts"], reb=s["reb"], ast=s["ast"], stl=s["stl"], blk=s["blk"], tov=s["tov"], fg3m=s["fg3m"],
                fg_pct=s["fg_pct"], fg3_pct=s["fg3_pct"], ft_pct=s["ft_pct"], ts_pct=s["ts_pct"], usg=s["usg"], dd=s["dd"], td=s["td"]))

        parts = []
        if qualified and mode == "pg" and group != "total":
            # each player is judged against the games HIS team has played (matters in the playoffs, where teams differ widely)
            parts.append(f"at least 70% of their team’s games (about {max(1, math.ceil(QUALIFY_GAMES * league_games))} of {league_games} for the busiest team)")
        if qualified and group == "fg":
            parts.append(f"{math.ceil(FGM_PER_TEAM_GAME * league_games)}+ field goals made (scaled to games played)")
        if qualified and group == "fg3":
            parts.append(f"{math.ceil(FG3M_PER_TEAM_GAME * league_games)}+ threes made (scaled to games played)")
        if qualified and group == "ft":
            parts.append(f"{math.ceil(FTM_PER_TEAM_GAME * league_games)}+ free throws made (scaled to games played)")
        return PlayerLeaders(season=season, seasons=seasons, season_type=season_type, stat=stat, label=PLAYER_STATS[stat][0], mode=mode,
                             qualified=qualified, requirement=" and ".join(parts) or None, team_games=league_games, total=len(rows), rows=out)

    @router.get("/teams", response_model=TeamLeaders)
    def teams(stat: str = "net_rtg", season: Optional[str] = None, c: sqlite3.Connection = Depends(conn)):
        if stat not in TEAM_STATS:
            raise HTTPException(422, f"unknown stat '{stat}'")
        seasons = [r["season"] for r in c.execute("SELECT DISTINCT season FROM team_season ORDER BY season DESC")]
        if not seasons:
            raise HTTPException(404, "team stats not loaded (run: python -m nbadash.ingest teams)")
        if season is None:
            season = seasons[0]
        elif season not in seasons:
            raise HTTPException(404, f"no team stats for {season}")
        data = c.execute("SELECT s.*, t.abbr, t.conference FROM team_season s LEFT JOIN teams t ON t.id = s.team_id WHERE s.season=?", (season,)).fetchall()
        label, lower = TEAM_STATS[stat]
        keys = list(TEAM_STATS)
        # teams that haven't recorded the stat sort last, never first
        ordered = sorted(data, key=lambda r: (r[stat] is None, (r[stat] if lower else -r[stat]) if r[stat] is not None else 0, r["name"]))
        rows = [TeamLeader(rank=i, team_id=r["team_id"], abbr=r["abbr"], name=r["name"], conference=r["conference"], w=r["w"], l=r["l"],
                           value=r[stat], stats={k: r[k] for k in keys}) for i, r in enumerate(ordered, 1)]
        return TeamLeaders(season=season, seasons=seasons, stat=stat, label=label, lower_is_better=lower,
                           team_games=max((r["gp"] or 0 for r in data), default=0), rows=rows)

    return router
