"""Data behind the player Stats tab: per-game rows with every filterable attribute, and the opponent matchup profile.

The Stats tab filters and recomputes client-side, so /games returns *everything* about each game once.
"""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Iterator, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from . import db
from .props_ingest import SHOT_TYPES, ZONES

ZONE_LABELS = {
    "Restricted Area": "Restricted area", "In The Paint (Non-RA)": "Paint (non-RA)", "Mid-Range": "Mid-range",
    "Left Corner 3": "Left corner 3", "Right Corner 3": "Right corner 3", "Above the Break 3": "Above the break 3",
}
SHOT_TYPE_LABELS = {"catch_shoot": "Catch & shoot", "under_10": "Under 10 ft", "pullup": "Pull-up"}
PLAY_TYPE_LABELS = {
    "Isolation": "Isolation", "Transition": "Transition", "PRBallHandler": "PnR ball handler", "PRRollMan": "PnR roll man",
    "Postup": "Post up", "Spotup": "Spot up", "Handoff": "Handoff", "Cut": "Cut", "OffScreen": "Off screen",
    "OffRebound": "Putbacks", "Misc": "Misc",
}
COUNTED = ("regular", "playoffs")  # play-in games are stored but are neither regular season nor playoffs


class Window(BaseModel):
    season: str
    team_id: int
    first: str
    last: str


class Teammate(BaseModel):
    player_id: int
    name: str
    games: int  # games played together in the returned sample
    windows: list[Window]  # when they were on the same team, so "without X" excludes games before a trade


class PropGame(BaseModel):
    game_id: str
    date: str
    season: str
    season_type: str
    team_id: Optional[int]
    opp_id: Optional[int]
    opp_abbr: str
    home: bool
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
    plus_minus: Optional[int]
    q1_pts: Optional[int]
    q1_reb: Optional[int]
    q1_ast: Optional[int]
    h1_pts: Optional[int]
    usg: Optional[float]  # percent
    rest_days: Optional[int]  # days since the team's previous game in the same season (0 = back-to-back)
    opp_def_rank: Optional[int]  # opponent defensive-rating rank that season (1 = best defence)
    opp_pace_rank: Optional[int]
    mates: list[int]  # teammates who played in this game


class NextGame(BaseModel):
    game_id: str
    date: str
    start_utc: Optional[str]
    opp_id: int
    opp_abbr: str
    opp_name: str
    home: bool


class PropsData(BaseModel):
    player_id: int
    name: str
    seasons: list[str]  # ascending
    games: list[PropGame]  # ascending by date
    teammates: list[Teammate]
    next_game: Optional[NextGame]


class ZoneRow(BaseModel):
    zone: str
    label: str
    fgm: int
    fga: int
    fg_pct: Optional[float]
    share: Optional[float]  # share of the player's field-goal attempts
    league_fg_pct: Optional[float]  # league-wide FG% in this zone, to judge the player against
    opp_fg_pct: Optional[float]  # FG% the opponent allows in this zone
    opp_rank: Optional[int]  # 1 = allows the lowest FG% (toughest), 30 = allows the highest (best matchup)


class ShotTypeRow(BaseModel):
    key: str
    label: str
    fgm: int
    fga: int
    fg_pct: Optional[float]
    share: Optional[float]
    opp_efg_pct: Optional[float]
    opp_rank: Optional[int]


class PlayTypeRow(BaseModel):
    key: str
    label: str
    pts_pg: float
    share: float  # of the player's points
    ppp: Optional[float]
    opp_ppp: Optional[float]
    opp_rank: Optional[int]


class TeamRef(BaseModel):
    id: int
    abbr: Optional[str]
    name: str


class Matchup(BaseModel):
    season: str
    seasons: list[str]
    opponent: Optional[TeamRef]
    zones: list[ZoneRow]
    shot_types: list[ShotTypeRow]
    play_types: list[PlayTypeRow]
    free_throws_pg: Optional[float]
    points_pg: Optional[float]


class AvgLine(BaseModel):
    """Per-game averages with the same stat names as PropGame, so any market can be evaluated on it."""
    min: float
    pts: float
    reb: float
    ast: float
    stl: float
    blk: float
    tov: float
    pf: float
    fgm: float
    fga: float
    fg3m: float
    fg3a: float
    ftm: float
    fta: float
    q1_pts: Optional[float]
    q1_reb: Optional[float]
    q1_ast: Optional[float]
    h1_pts: Optional[float]


class SimilarPlayer(BaseModel):
    player_id: int
    name: str
    position: Optional[str]
    team_abbr: Optional[str]
    match: float  # 0-100: how closely their shot zones and shot types match the player's
    games_vs_opp: int
    averages: AvgLine  # their per-game averages this season (market values are read from it)


class SimilarGame(PropGame):
    player_id: int
    player_name: str
    team_abbr: Optional[str]


class Similar(BaseModel):
    season: str
    seasons: list[str]
    mode: str  # "shots" | "position"
    opponent: Optional[TeamRef]
    players: list[SimilarPlayer]
    games: list[SimilarGame]  # the similar players' games against the opponent this season, newest first


def opp_abbr_of(r: sqlite3.Row) -> str:
    return (r["matchup"] or "").split()[-1] if r["matchup"] else ""


def prop_game(r: sqlite3.Row, opp_id: Optional[int], has_q1: set[str], has_q2: set[str], *, rest: Optional[int] = None,
              ranks: tuple[Optional[int], Optional[int]] = (None, None), mates: Optional[list[int]] = None) -> PropGame:
    """One player_game_logs row as a PropGame. A missing period row means 0 once that season's period data exists."""
    q1 = {k: (r[k] or 0) if r["season"] in has_q1 else None for k in ("q1_pts", "q1_reb", "q1_ast")}
    q2 = (r["q2_pts"] or 0) if r["season"] in has_q2 else None
    h1 = q1["q1_pts"] + q2 if q1["q1_pts"] is not None and q2 is not None else None
    return PropGame(
        game_id=r["game_id"], date=r["game_date"], season=r["season"], season_type=r["season_type"], team_id=r["team_id"],
        opp_id=opp_id, opp_abbr=opp_abbr_of(r), home=" vs. " in (r["matchup"] or ""), result=r["wl"], min=r["min"] or 0,
        pts=r["pts"], reb=r["reb"], ast=r["ast"], stl=r["stl"], blk=r["blk"], tov=r["tov"], pf=r["pf"], fgm=r["fgm"],
        fga=r["fga"], fg3m=r["fg3m"], fg3a=r["fg3a"], ftm=r["ftm"], fta=r["fta"], plus_minus=r["plus_minus"],
        q1_pts=q1["q1_pts"], q1_reb=q1["q1_reb"], q1_ast=q1["q1_ast"], h1_pts=h1,
        usg=round(r["usg_pct"] * 100, 1) if r["usg_pct"] is not None else None, rest_days=rest,
        opp_def_rank=ranks[0], opp_pace_rank=ranks[1], mates=mates or [])


def period_flags(logs: list[sqlite3.Row]) -> tuple[set[str], set[str]]:
    """Seasons for which first / second quarter data was ingested (so a missing row means 'no stats', not 'unknown')."""
    return ({r["season"] for r in logs if r["q1_pts"] is not None}, {r["season"] for r in logs if r["q2_pts"] is not None})


def _div(a: float, b: float, nd: int = 3) -> Optional[float]:
    return round(a / b, nd) if b else None


def _ranks(values: dict[int, Optional[float]]) -> dict[int, int]:
    """1 = lowest value. Teams without a value are left out."""
    ordered = sorted((v, k) for k, v in values.items() if v is not None)
    return {tid: i + 1 for i, (_, tid) in enumerate(ordered)}


def make_router(db_path: Optional[str | Path] = None) -> APIRouter:
    router = APIRouter(prefix="/api/players", tags=["props"])

    def conn() -> Iterator[sqlite3.Connection]:
        c = db.connect(db_path)
        try:
            yield c
        finally:
            c.close()

    def need_player(c: sqlite3.Connection, pid: int) -> sqlite3.Row:
        r = c.execute("SELECT * FROM players WHERE id=?", (pid,)).fetchone()
        if not r:
            raise HTTPException(404, "player not found")
        return r

    def next_game_for(c: sqlite3.Connection, team_id: Optional[int]) -> Optional[NextGame]:
        if team_id is None:
            return None
        r = c.execute(
            """SELECT s.* FROM schedule s WHERE s.status = 1 AND (s.home_id = ? OR s.away_id = ?)
                 AND s.game_id NOT IN (SELECT game_id FROM team_games WHERE team_id = ?)
               ORDER BY s.start_utc LIMIT 1""", (team_id, team_id, team_id)).fetchone()
        if not r:
            return None
        home = r["home_id"] == team_id
        opp = c.execute("SELECT * FROM teams WHERE id=?", (r["away_id"] if home else r["home_id"],)).fetchone()
        return NextGame(game_id=r["game_id"], date=r["game_date"], start_utc=r["start_utc"], opp_id=opp["id"],
                        opp_abbr=opp["abbr"] or "", opp_name=f"{opp['city']} {opp['name']}", home=home)

    @router.get("/{pid}/games", response_model=PropsData)
    def games(pid: int, seasons: int = Query(3, ge=1, le=6), c: sqlite3.Connection = Depends(conn)):
        p = need_player(c, pid)
        all_seasons = [r["season"] for r in c.execute(
            "SELECT DISTINCT season FROM player_game_logs WHERE player_id=? AND season_type IN ('regular','playoffs') "
            "ORDER BY season DESC", (pid,))][:seasons]
        if not all_seasons:
            raise HTTPException(404, "no game logs (run: python -m nbadash.ingest props)")
        marks = ",".join("?" * len(all_seasons))
        logs = c.execute(
            f"SELECT * FROM player_game_logs WHERE player_id=? AND season IN ({marks}) AND season_type IN ('regular','playoffs') "
            "ORDER BY game_date, game_id", (pid, *all_seasons)).fetchall()

        abbr_to_id = {r["abbr"]: r["id"] for r in c.execute("SELECT id, abbr FROM teams WHERE abbr IS NOT NULL")}
        def_rank = {(r["team_id"], r["season"]): (r["def_rtg_rank"], r["pace_rank"]) for r in c.execute(
            f"SELECT team_id, season, def_rtg_rank, pace_rank FROM team_season WHERE season IN ({marks})", all_seasons)}

        team_seasons = sorted({(r["team_id"], r["season"]) for r in logs if r["team_id"] is not None})
        # every date each of the player's teams played, to derive rest days (any player's row marks a team game)
        prev_date: dict[tuple[int, str, str], Optional[str]] = {}
        mates_by_game: dict[str, list[int]] = {}
        for tid, season in team_seasons:
            dates = [r["game_date"] for r in c.execute(
                "SELECT DISTINCT game_date FROM player_game_logs WHERE team_id=? AND season=? ORDER BY game_date", (tid, season))]
            for prev, cur in zip([None] + dates, dates):
                prev_date[(tid, season, cur)] = prev
            for r in c.execute("SELECT game_id, player_id FROM player_game_logs WHERE team_id=? AND season=? AND min > 0",
                               (tid, season)):
                if r["player_id"] != pid:
                    mates_by_game.setdefault(r["game_id"], []).append(r["player_id"])

        has_q1, has_q2 = period_flags(logs)

        out: list[PropGame] = []
        for r in logs:
            opp_id = abbr_to_id.get(opp_abbr_of(r))
            prev = prev_date.get((r["team_id"], r["season"], r["game_date"]))
            rest = (date.fromisoformat(r["game_date"]) - date.fromisoformat(prev)).days - 1 if prev else None
            out.append(prop_game(r, opp_id, has_q1, has_q2, rest=rest, ranks=def_rank.get((opp_id, r["season"]), (None, None)),
                                 mates=mates_by_game.get(r["game_id"], [])))

        together: dict[int, int] = {}
        for g in out:
            for m in g.mates:
                together[m] = together.get(m, 0) + 1
        top = [t for t, n in sorted(together.items(), key=lambda kv: -kv[1]) if n >= 8][:14]
        names = {r["id"]: r["full_name"] for r in c.execute(f"SELECT id, full_name FROM players WHERE id IN ({','.join('?' * len(top)) or 'NULL'})", top)}
        my_teams = sorted({tid for tid, _ in team_seasons})
        teammates = []
        for m in top:
            wins = c.execute(
                f"SELECT season, team_id, MIN(game_date) f, MAX(game_date) l FROM player_game_logs WHERE player_id=? "
                f"AND team_id IN ({','.join('?' * len(my_teams))}) AND season IN ({marks}) GROUP BY season, team_id",
                (m, *my_teams, *all_seasons)).fetchall()
            teammates.append(Teammate(player_id=m, name=names.get(m, f"Player {m}"), games=together[m],
                                      windows=[Window(season=w["season"], team_id=w["team_id"], first=w["f"], last=w["l"]) for w in wins]))

        latest_team = out[-1].team_id if out else p["team_id"]
        return PropsData(player_id=pid, name=p["full_name"], seasons=sorted(all_seasons), games=out, teammates=teammates,
                         next_game=next_game_for(c, latest_team))

    @router.get("/{pid}/matchup", response_model=Matchup)
    def matchup(pid: int, season: Optional[str] = None, opp: Optional[int] = None, c: sqlite3.Connection = Depends(conn)):
        p = need_player(c, pid)
        seasons = [r["season"] for r in c.execute(
            "SELECT DISTINCT season FROM player_zones WHERE player_id=? ORDER BY season DESC", (pid,))]
        if not seasons:
            raise HTTPException(404, "no matchup data (run: python -m nbadash.ingest props)")
        if season not in seasons:
            played = {r["season"]: r["n"] for r in c.execute(
                "SELECT season, COUNT(*) n FROM player_game_logs WHERE player_id=? AND season_type='regular' GROUP BY season", (pid,))}
            season = next((x for x in seasons if played.get(x, 0) >= 15), seasons[0])

        opponent: Optional[TeamRef] = None
        if opp is None:
            last = c.execute("SELECT team_id FROM player_game_logs WHERE player_id=? ORDER BY game_date DESC LIMIT 1", (pid,)).fetchone()
            ng = next_game_for(c, last["team_id"] if last else p["team_id"])
            opp = ng.opp_id if ng else None
        if opp is not None:
            t = c.execute("SELECT * FROM teams WHERE id=?", (opp,)).fetchone()
            if not t:
                raise HTTPException(404, "opponent not found")
            opponent = TeamRef(id=t["id"], abbr=t["abbr"], name=f"{t['city']} {t['name']}")

        # ---- zones
        pz = {r["zone"]: r for r in c.execute("SELECT * FROM player_zones WHERE player_id=? AND season=?", (pid, season))}
        total_fga = sum(r["fga"] or 0 for r in pz.values())
        tz: dict[str, dict[int, Optional[float]]] = {z: {} for z in ZONES}
        for r in c.execute("SELECT * FROM team_zones_def WHERE season=?", (season,)):
            tz[r["zone"]][r["team_id"]] = _div(r["fgm"], r["fga"])
        league = {r["zone"]: _div(r["m"], r["a"]) for r in c.execute(
            "SELECT zone, SUM(fgm) m, SUM(fga) a FROM player_zones WHERE season=? GROUP BY zone", (season,))}
        zones = []
        for z in ZONES:
            r = pz.get(z)
            ranks = _ranks(tz[z])
            zones.append(ZoneRow(
                zone=z, label=ZONE_LABELS[z], fgm=r["fgm"] if r else 0, fga=r["fga"] if r else 0,
                fg_pct=_div(r["fgm"], r["fga"]) if r else None, share=_div(r["fga"], total_fga) if r else None,
                league_fg_pct=league.get(z), opp_fg_pct=tz[z].get(opp) if opp else None, opp_rank=ranks.get(opp) if opp else None))

        # ---- shot types (opponent metric: eFG% allowed)
        shot_types = []
        for key in SHOT_TYPES.values():
            r = c.execute("SELECT * FROM player_shot_types WHERE player_id=? AND season=? AND shot_type=?", (pid, season, key)).fetchone()
            allowed = {t["team_id"]: _div(t["fgm"] + 0.5 * t["fg3m"], t["fga"]) for t in c.execute(
                "SELECT * FROM team_shot_types_def WHERE season=? AND shot_type=?", (season, key))}
            ranks = _ranks(allowed)
            shot_types.append(ShotTypeRow(
                key=key, label=SHOT_TYPE_LABELS[key], fgm=r["fgm"] if r else 0, fga=r["fga"] if r else 0,
                fg_pct=_div(r["fgm"], r["fga"]) if r else None, share=_div(r["fga"], total_fga) if r and total_fga else None,
                opp_efg_pct=allowed.get(opp) if opp else None, opp_rank=ranks.get(opp) if opp else None))

        # ---- play types (Synergy): points per game by play type, and the opponent's PPP allowed
        tot = c.execute(
            "SELECT COUNT(*) gp, SUM(pts) pts, SUM(ftm) ftm FROM player_game_logs WHERE player_id=? AND season=? AND season_type='regular'",
            (pid, season)).fetchone()
        gp = tot["gp"] or 0
        points_pg = round(tot["pts"] / gp, 1) if gp else None
        play_types = []
        for r in c.execute("SELECT * FROM player_play_types WHERE player_id=? AND season=? ORDER BY pts DESC", (pid, season)):
            allowed = {t["team_id"]: _div(t["pts"], t["poss"]) for t in c.execute(
                "SELECT * FROM team_play_types_def WHERE season=? AND play_type=?", (season, r["play_type"]))}
            ranks = _ranks(allowed)
            play_types.append(PlayTypeRow(
                key=r["play_type"], label=PLAY_TYPE_LABELS.get(r["play_type"], r["play_type"]),
                pts_pg=round(r["pts"] / r["gp"], 1) if r["gp"] else 0.0,
                share=round(r["pts"] / r["gp"] / points_pg, 3) if r["gp"] and points_pg else 0.0,
                ppp=_div(r["pts"], r["poss"]), opp_ppp=allowed.get(opp) if opp else None, opp_rank=ranks.get(opp) if opp else None))

        return Matchup(season=season, seasons=seasons, opponent=opponent, zones=zones, shot_types=shot_types,
                       play_types=play_types, points_pg=points_pg,
                       free_throws_pg=round(tot["ftm"] / gp, 1) if gp and tot["ftm"] is not None else None)

    def profile_vectors(c: sqlite3.Connection, season: str) -> dict[int, tuple[list[float], list[float]]]:
        """player -> (share of attempts by zone, share by shot type). Both use the zone attempt total as denominator."""
        zones: dict[int, dict[str, int]] = {}
        for r in c.execute("SELECT player_id, zone, fga FROM player_zones WHERE season=?", (season,)):
            zones.setdefault(r["player_id"], {})[r["zone"]] = r["fga"] or 0
        types: dict[int, dict[str, int]] = {}
        for r in c.execute("SELECT player_id, shot_type, fga FROM player_shot_types WHERE season=?", (season,)):
            types.setdefault(r["player_id"], {})[r["shot_type"]] = r["fga"] or 0
        out = {}
        for pid, z in zones.items():
            total = sum(z.values())
            if total <= 0:
                continue
            t = types.get(pid, {})
            out[pid] = ([z.get(name, 0) / total for name in ZONES], [t.get(key, 0) / total for key in SHOT_TYPES.values()])
        return out

    @router.get("/{pid}/similar", response_model=Similar)
    def similar(pid: int, season: Optional[str] = None, opp: Optional[int] = None, mode: str = Query("shots", pattern="^(shots|position)$"),
                limit: int = Query(10, ge=1, le=25), c: sqlite3.Connection = Depends(conn)):
        """Players who shoot like this one (shot zones + shot types), and how they fared against the opponent this season."""
        p = need_player(c, pid)
        seasons = [r["season"] for r in c.execute("SELECT DISTINCT season FROM player_zones WHERE player_id=? ORDER BY season DESC", (pid,))]
        if not seasons:
            raise HTTPException(404, "no shot profile for this player (run: python -m nbadash.ingest props)")
        if season not in seasons:
            played = {r["season"]: r["n"] for r in c.execute(
                "SELECT season, COUNT(*) n FROM player_game_logs WHERE player_id=? AND season_type='regular' GROUP BY season", (pid,))}
            season = next((x for x in seasons if played.get(x, 0) >= 15), seasons[0])

        opponent: Optional[TeamRef] = None
        if opp is None:
            last = c.execute("SELECT team_id FROM player_game_logs WHERE player_id=? ORDER BY game_date DESC LIMIT 1", (pid,)).fetchone()
            ng = next_game_for(c, last["team_id"] if last else p["team_id"])
            opp = ng.opp_id if ng else None
        if opp is not None:
            t = c.execute("SELECT * FROM teams WHERE id=?", (opp,)).fetchone()
            if not t:
                raise HTTPException(404, "opponent not found")
            opponent = TeamRef(id=t["id"], abbr=t["abbr"], name=f"{t['city']} {t['name']}")

        vectors = profile_vectors(c, season)
        if pid not in vectors:
            raise HTTPException(404, "no shot profile for this player in that season")
        # Candidates must have a comparable role: a real sample, rotation minutes and at least half the player's shot volume.
        # (The ranking itself uses only shot zones and shot types; volume just keeps bench players out of the pool.)
        usage = {r["player_id"]: (r["mpg"], r["fpg"]) for r in c.execute(
            "SELECT player_id, AVG(min) mpg, AVG(fga) fpg FROM player_game_logs WHERE season=? AND season_type='regular' "
            "GROUP BY player_id HAVING COUNT(*) >= 15", (season,))}
        my_fga = usage.get(pid, (0, 0))[1]
        eligible = {q for q, (mpg, fpg) in usage.items() if mpg >= 20 and fpg >= 0.5 * my_fga}
        positions = {r["id"]: r["position"] for r in c.execute("SELECT id, position FROM players")}
        group = lambda pos: pos[0].upper() if pos else None  # noqa: E731  Guard / Forward / Center (also "G-F")
        mine = vectors[pid]

        def match(other: tuple[list[float], list[float]]) -> float:
            tv_zone = 0.5 * sum(abs(a - b) for a, b in zip(mine[0], other[0]))
            tv_type = 0.5 * sum(abs(a - b) for a, b in zip(mine[1], other[1]))
            return round(max(0.0, 1 - (tv_zone + tv_type) / 2) * 100, 1)

        pool = [q for q in vectors if q != pid and q in eligible
                and (mode == "shots" or (group(positions.get(q)) is not None and group(positions.get(q)) == group(positions.get(pid))))]
        ranked = sorted(((match(vectors[q]), q) for q in pool), reverse=True)[:limit]
        if not ranked:
            return Similar(season=season, seasons=seasons, mode=mode, opponent=opponent, players=[], games=[])

        ids = [q for _, q in ranked]
        marks = ",".join("?" * len(ids))
        rows = c.execute(f"SELECT * FROM player_game_logs WHERE season=? AND season_type IN ('regular','playoffs') AND player_id IN ({marks}) "
                         "ORDER BY game_date DESC", (season, *ids)).fetchall()
        has_q1, has_q2 = period_flags(rows)
        abbr_to_id = {r["abbr"]: r["id"] for r in c.execute("SELECT id, abbr FROM teams WHERE abbr IS NOT NULL")}
        team_abbr = {v: k for k, v in abbr_to_id.items()}
        info = {r["id"]: r for r in c.execute(f"SELECT id, full_name, position, team_abbr FROM players WHERE id IN ({marks})", ids)}
        by_player: dict[int, list[sqlite3.Row]] = {}
        for r in rows:
            by_player.setdefault(r["player_id"], []).append(r)

        def averages(q: int) -> Optional[AvgLine]:
            reg = [r for r in by_player.get(q, []) if r["season_type"] == "regular"]
            if not reg:
                return None
            n = len(reg)
            mean = lambda k: sum((r[k] or 0) for r in reg) / n  # noqa: E731
            has1, has2 = season in has_q1, season in has_q2
            return AvgLine(
                min=mean("min"), pts=mean("pts"), reb=mean("reb"), ast=mean("ast"), stl=mean("stl"), blk=mean("blk"), tov=mean("tov"),
                pf=mean("pf"), fgm=mean("fgm"), fga=mean("fga"), fg3m=mean("fg3m"), fg3a=mean("fg3a"), ftm=mean("ftm"), fta=mean("fta"),
                q1_pts=mean("q1_pts") if has1 else None, q1_reb=mean("q1_reb") if has1 else None, q1_ast=mean("q1_ast") if has1 else None,
                h1_pts=mean("q1_pts") + mean("q2_pts") if has1 and has2 else None)

        players, games = [], []
        for score, q in ranked:
            avg = averages(q)
            if avg is None:
                continue
            mine_games = [r for r in by_player.get(q, []) if opponent and opp_abbr_of(r) == opponent.abbr]
            i = info.get(q)
            for r in mine_games:
                g = prop_game(r, opp, has_q1, has_q2)
                games.append(SimilarGame(**g.model_dump(), player_id=q, player_name=i["full_name"] if i else f"Player {q}", team_abbr=team_abbr.get(r["team_id"])))
            players.append(SimilarPlayer(player_id=q, name=i["full_name"] if i else f"Player {q}", position=i["position"] if i else None,
                                         team_abbr=i["team_abbr"] if i else None, match=score, games_vs_opp=len(mine_games), averages=avg))
        games.sort(key=lambda g: g.date, reverse=True)
        return Similar(season=season, seasons=seasons, mode=mode, opponent=opponent, players=players, games=games)

    return router
