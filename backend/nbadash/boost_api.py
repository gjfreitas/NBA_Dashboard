"""Matchup boosts: how today's defence should help or hurt each scorer, from how that defence guards his style of play,
his shot types and his position.

For every player in today's games three effects are worked out, each a percentage change in expected scoring against a league-average defence:
  style     his play types (isolation, transition, spot up...) weighted by his share of points, against the opponent's points per possession
            allowed on each, relative to the league's
  shot      catch-and-shoot / pull-up / under-10-feet, weighted by his attempts, against the opponent's effective FG% allowed
  position  the points the opponent allows to players of his position, relative to the league average (halved: a noisier signal)
The boost is the average of the effects that could be computed. It is a pointer to where a matchup is soft or tough, not a projection:
small samples, injuries and minutes all matter more than any of it.

How much of a defence is this season's: a team's defensive numbers are noisy early, so each one blends last season's with this season's by the
number of games THAT TEAM has played: all last season's at 10 games or fewer, all this season's at 30 (a straight ramp in between).
Numbers that stay noisy even after 30 games (rare play types, shooting percentages that include threes) never go above CAP_NOISY of this season.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from . import db
from .matchup_api import defence_by_position, pos_letter

ET = ZoneInfo("America/New_York")
MIN_GP = 15  # games a player needs in a season for his profile to mean anything
MIN_PPG = 8.0  # only rotation scorers: a bench player's profile is noise
RAMP_FROM, RAMP_TO = 10, 30  # a team's games: 0% this season at 10, 100% at 30
CAP_NOISY = 0.7  # the most of this season ever used for the noisiest numbers
NOISY_PLAYS = {"Postup", "Handoff", "Cut", "OffScreen", "Isolation", "OffRebound", "Misc", "PRRollMan"}  # a handful of possessions a game per team
POSITION_WEIGHT = 0.5  # points allowed by position is a noisier signal than play and shot types (pace, minutes, who plays), so its effect is halved
PLAY_LABEL = {"Isolation": "Isolation", "Transition": "Transition", "PRBallHandler": "PnR ball handler", "PRRollMan": "PnR roll man", "Postup": "Post up",
              "Spotup": "Spot up", "Handoff": "Handoff", "Cut": "Cuts", "OffScreen": "Off screen", "OffRebound": "Putbacks", "Misc": "Other plays"}
SHOT_LABEL = {"catch_shoot": "Catch & shoot", "pullup": "Pull-ups", "under_10": "Shots under 10 ft"}
POS_LABEL = {"G": "guards", "F": "forwards", "C": "centers"}


class Driver(BaseModel):
    kind: str  # style | shot | position
    label: str
    share: Optional[float]  # his share of points (style), of attempts (shot); None for position
    effect_pct: float  # this item's contribution to the boost, in percentage points
    detail: str  # "UTA allow the 1st most"


class Boost(BaseModel):
    player_id: int
    name: str
    team_abbr: Optional[str]
    opp_abbr: Optional[str]
    game_id: str
    start_utc: Optional[str]
    home: bool
    boost_pct: float
    style_pct: Optional[float]
    shot_pct: Optional[float]
    position_pct: Optional[float]
    headline: str
    drivers: list[Driver]  # strongest first
    ppg: float
    profile_season: str  # the season his own numbers come from
    opp_games: int  # games the opponent has played this season
    season_weight: float  # how much of the opponent's defence numbers is this season's (0 to 1); the rest is last season's


class Boosts(BaseModel):
    date: str
    season: Optional[str]  # the current season
    previous_season: Optional[str]
    best: list[Boost]
    toughest: list[Boost]
    all: list[Boost]  # everyone, best first


def ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def rank_text(abbr: str, rank_most: int, teams: int, positive: bool, what: str = "") -> str:
    """'UTA allow the 1st most' (soft) or 'DET allow the 1st fewest' (tough). rank_most counts from the team that allows the most."""
    n = rank_most if positive else teams + 1 - rank_most
    return f"{abbr} allow the {ordinal(n)} {'most' if positive else 'fewest'}{what}"


def weighted_effect(items: list[tuple[float, float]]) -> Optional[float]:
    """items = [(weight, deviation)], deviation as a fraction (0.08 = 8% above league). Weighted mean, in percent; None with no weight."""
    total = sum(w for w, _ in items if w > 0)
    if total <= 0:
        return None
    return 100 * sum(w * d for w, d in items if w > 0) / total


def combine(*parts: Optional[float]) -> Optional[float]:
    have = [p for p in parts if p is not None]
    return sum(have) / len(have) if have else None


def ramp(games: Optional[int], cap: float = 1.0) -> float:
    """How much of this season to use for a team that has played `games`: 0 at RAMP_FROM, 1 at RAMP_TO, capped at `cap`."""
    if not games:
        return 0.0
    return min(cap, max(0.0, (games - RAMP_FROM) / (RAMP_TO - RAMP_FROM)))


def blend(cur: Optional[float], prev: Optional[float], w: float) -> Optional[float]:
    """w of the current value and 1 - w of the previous one; whichever exists if only one does."""
    if cur is None:
        return prev
    if prev is None:
        return cur
    return w * cur + (1 - w) * prev


def seasons(conn: sqlite3.Connection) -> tuple[Optional[str], Optional[str]]:
    """(current, previous) season among those with team data."""
    s = [r["season"] for r in conn.execute("SELECT DISTINCT season FROM team_season ORDER BY season DESC LIMIT 2")]
    return (s[0] if s else None, s[1] if len(s) > 1 else None)


class Defence:
    """One season's defence deviations from the league: how far above (+) or below (-) average each team allows, as a fraction."""

    def __init__(self, conn: sqlite3.Connection, season: str):
        self.play: dict[int, dict[str, float]] = {}
        self.shot: dict[int, dict[str, float]] = {}
        self.pos: dict[int, dict[str, float]] = {}
        league_play: dict[str, list[float]] = {}
        rows = list(conn.execute("SELECT team_id, play_type, poss, pts FROM team_play_types_def WHERE season=?", (season,)))
        for r in rows:
            if r["poss"]:
                a = league_play.setdefault(r["play_type"], [0.0, 0.0]); a[0] += r["poss"]; a[1] += r["pts"]
        for r in rows:
            if r["poss"] and r["play_type"] in league_play and league_play[r["play_type"]][1]:
                self.play.setdefault(r["team_id"], {})[r["play_type"]] = (r["pts"] / r["poss"]) / (league_play[r["play_type"]][1] / league_play[r["play_type"]][0]) - 1
        league_shot: dict[str, list[float]] = {}
        rows = list(conn.execute("SELECT team_id, shot_type, fgm, fg3m, fga FROM team_shot_types_def WHERE season=?", (season,)))
        for r in rows:
            if r["fga"]:
                a = league_shot.setdefault(r["shot_type"], [0.0, 0.0]); a[0] += r["fgm"] + 0.5 * r["fg3m"]; a[1] += r["fga"]
        for r in rows:
            if r["fga"] and league_shot.get(r["shot_type"], [0, 0])[0]:
                efg = (r["fgm"] + 0.5 * r["fg3m"]) / r["fga"]
                self.shot.setdefault(r["team_id"], {})[r["shot_type"]] = efg / (league_shot[r["shot_type"]][0] / league_shot[r["shot_type"]][1]) - 1
        by_pos = defence_by_position(conn, season)
        for pos in ("G", "F", "C"):
            vals = [d[pos]["pts"] for d in by_pos.values() if pos in d]
            if vals:
                avg = sum(vals) / len(vals)
                for team, d in by_pos.items():
                    if pos in d:
                        self.pos.setdefault(team, {})[pos] = d[pos]["pts"] / avg - 1


def blended(cur: Defence, prev: Optional[Defence], table: str, team: int, key: str, w: float) -> Optional[float]:
    return blend(getattr(cur, table).get(team, {}).get(key), getattr(prev, table).get(team, {}).get(key) if prev else None, w)


def build(conn: sqlite3.Connection, day: str) -> Boosts:
    season, previous = seasons(conn)
    games = conn.execute("SELECT * FROM schedule WHERE game_date=? ORDER BY start_utc, game_id", (day,)).fetchall()
    empty = Boosts(date=day, season=season, previous_season=previous, best=[], toughest=[], all=[])
    if season is None or not games:
        return empty
    cur = Defence(conn, season)
    prev = Defence(conn, previous) if previous else None
    team_gp = {r["team_id"]: r["gp"] for r in conn.execute("SELECT team_id, gp FROM team_season WHERE season=?", (season,))}

    def weight(team: int, cap: float = 1.0) -> float:
        return ramp(team_gp.get(team), cap)

    def rank_most(table: str, key: str, team: int, cap: float) -> tuple[int, int]:
        """Where the team stands among all teams on the blended number (1 = allows the most)."""
        vals = {t: blended(cur, prev, table, t, key, weight(t, cap)) for t in set(getattr(cur, table)) | set(getattr(prev, table) if prev else {})}
        vals = {t: v for t, v in vals.items() if v is not None}
        return 1 + sum(1 for v in vals.values() if v > vals[team]), len(vals)

    teams = {r["id"]: r for r in conn.execute("SELECT id, abbr FROM teams")}
    team_game = {}  # team id -> (game row, opponent id, is home)
    for g in games:
        team_game[g["home_id"]] = (g, g["away_id"], True)
        team_game[g["away_id"]] = (g, g["home_id"], False)
    pool = conn.execute(f"SELECT id, full_name, team_id, position FROM players WHERE is_active=1 AND team_id IN ({','.join('?' * len(team_game))})", list(team_game)).fetchall()
    ids = [p["id"] for p in pool]
    if not ids:
        return empty
    ph = ",".join("?" * len(ids))
    wanted = [s for s in (season, previous) if s]
    sph = ",".join("?" * len(wanted))
    form: dict[tuple[int, str], sqlite3.Row] = {(r["player_id"], r["season"]): r for r in conn.execute(
        f"SELECT player_id, season, COUNT(*) AS gp, AVG(pts) AS ppg FROM player_game_logs WHERE season IN ({sph}) AND season_type='regular' AND min>=1 AND player_id IN ({ph}) "
        f"GROUP BY player_id, season", [*wanted, *ids])}
    mine_play: dict[tuple[int, str], dict[str, float]] = {}
    for r in conn.execute(f"SELECT player_id, season, play_type, pts FROM player_play_types WHERE season IN ({sph}) AND player_id IN ({ph})", [*wanted, *ids]):
        mine_play.setdefault((r["player_id"], r["season"]), {})[r["play_type"]] = r["pts"]
    mine_shot: dict[tuple[int, str], dict[str, float]] = {}
    for r in conn.execute(f"SELECT player_id, season, shot_type, fga FROM player_shot_types WHERE season IN ({sph}) AND player_id IN ({ph})", [*wanted, *ids]):
        mine_shot.setdefault((r["player_id"], r["season"]), {})[r["shot_type"]] = r["fga"] or 0
    out_today = {r["player_id"] for r in conn.execute(
        "SELECT player_id FROM injuries WHERE report_id=(SELECT report_id FROM injury_reports ORDER BY published_utc DESC LIMIT 1) AND status IN ('Out','Doubtful') AND player_id IS NOT NULL")}

    boosts: list[Boost] = []
    for p in pool:
        # his own profile: this season once he has played enough, otherwise last season's
        profile = next((s for s in wanted if (p["id"], s) in form and form[(p["id"], s)]["gp"] >= MIN_GP), None)
        if profile is None or (form[(p["id"], profile)]["ppg"] or 0) < MIN_PPG or p["id"] in out_today:
            continue
        f = form[(p["id"], profile)]
        game, opp, home = team_game[p["team_id"]]
        opp_abbr = teams[opp]["abbr"] if opp in teams else None
        drivers: list[Driver] = []

        items = []
        plays = mine_play.get((p["id"], profile), {})
        total_pts = sum(plays.values())
        for key, pts in plays.items():
            cap = CAP_NOISY if key in NOISY_PLAYS else 1.0
            dev = blended(cur, prev, "play", opp, key, weight(opp, cap))
            if dev is None or total_pts <= 0:
                continue
            items.append((pts / total_pts, dev))
            rk, n = rank_most("play", key, opp, cap)
            drivers.append(Driver(kind="style", label=PLAY_LABEL.get(key, key), share=round(pts / total_pts, 3), effect_pct=round(100 * pts / total_pts * dev, 2),
                                  detail=rank_text(opp_abbr or "Opp", rk, n, dev >= 0)))
        style = weighted_effect(items)

        sitems = []
        shots = mine_shot.get((p["id"], profile), {})
        total_fga = sum(v for k, v in shots.items() if k in SHOT_LABEL)
        for key, fga in shots.items():
            dev = blended(cur, prev, "shot", opp, key, weight(opp, CAP_NOISY))
            if dev is None or total_fga <= 0 or key not in SHOT_LABEL:
                continue
            sitems.append((fga / total_fga, dev))
            rk, n = rank_most("shot", key, opp, CAP_NOISY)
            drivers.append(Driver(kind="shot", label=SHOT_LABEL[key], share=round(fga / total_fga, 3), effect_pct=round(100 * fga / total_fga * dev, 2),
                                  detail=rank_text(opp_abbr or "Opp", rk, n, dev >= 0, " (effective FG%)")))
        shot = weighted_effect(sitems)

        pos = pos_letter(p["position"])
        position = None
        if pos:
            dev = blended(cur, prev, "pos", opp, pos, weight(opp))
            if dev is not None:
                position = 100 * dev * POSITION_WEIGHT
                rk, n = rank_most("pos", pos, opp, 1.0)
                drivers.append(Driver(kind="position", label=f"Position: {POS_LABEL[pos]}", share=None, effect_pct=round(position, 2),
                                      detail=rank_text(opp_abbr or "Opp", rk, n, dev >= 0, f" to {POS_LABEL[pos]}")))

        total = combine(style, shot, position)
        if total is None or not drivers:
            continue
        drivers.sort(key=lambda d: -abs(d.effect_pct))
        top = drivers[0]
        headline = (f"{top.label} {round(top.share * 100)}% of {'his points' if top.kind == 'style' else 'his shots'} · {top.detail}" if top.share is not None else f"{top.label} · {top.detail}")
        boosts.append(Boost(player_id=p["id"], name=p["full_name"], team_abbr=teams[p["team_id"]]["abbr"] if p["team_id"] in teams else None, opp_abbr=opp_abbr,
                            game_id=game["game_id"], start_utc=game["start_utc"], home=home, boost_pct=round(total, 1),
                            style_pct=round(style, 1) if style is not None else None, shot_pct=round(shot, 1) if shot is not None else None,
                            position_pct=round(position, 1) if position is not None else None, headline=headline, drivers=drivers[:4], ppg=round(f["ppg"], 1),
                            profile_season=profile, opp_games=team_gp.get(opp) or 0, season_weight=round(weight(opp), 2)))
    boosts.sort(key=lambda b: (-b.boost_pct, b.name))
    return Boosts(date=day, season=season, previous_season=previous, best=[b for b in boosts[:5] if b.boost_pct > 0],
                  toughest=[b for b in sorted(boosts, key=lambda b: (b.boost_pct, b.name))[:5] if b.boost_pct < 0], all=boosts)


def make_router(db_path: Optional[str | Path] = None) -> APIRouter:
    router = APIRouter(prefix="/api/today", tags=["today"])

    def conn() -> Iterator[sqlite3.Connection]:
        c = db.connect(db_path)
        try:
            yield c
        finally:
            c.close()

    @router.get("/boosts", response_model=Boosts)
    def boosts(date: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"), c: sqlite3.Connection = Depends(conn)):
        """Which of today's scorers face a soft or a tough defence for his style, shot types and position."""
        return build(c, date or datetime.now(ET).date().isoformat())

    return router
