"""Raw NBA CDN JSON -> our models."""
from __future__ import annotations

import re
from typing import Any, Optional

from .models import (BoxScore, Game, PeriodScore, Play, PlayerLine, TeamBox,
                     TeamSummary)

_ISO = re.compile(r"^PT(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?$")


def parse_clock(value: Optional[str]) -> str:
    """'PT10M36.00S' -> '10:36'; '' / None -> ''."""
    if not value:
        return ""
    m = _ISO.match(value)
    if not m:
        return value
    minutes = int(m.group(1) or 0)
    seconds = float(m.group(2) or 0)
    return f"{minutes}:{int(seconds):02d}"


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _state(status: int) -> str:
    return {1: "pre", 2: "live", 3: "final"}.get(status, "pre")


def normalize_team(t: dict) -> TeamSummary:
    return TeamSummary(
        id=t["teamId"], tricode=t["teamTricode"], city=t.get("teamCity", ""),
        name=t.get("teamName", ""), score=_int(t.get("score")),
        wins=t.get("wins"), losses=t.get("losses"),
        periods=[PeriodScore(period=p["period"], score=_int(p["score"]))
                 for p in t.get("periods", [])],
    )


def normalize_game(g: dict) -> Game:
    return Game(
        id=g["gameId"], state=_state(g["gameStatus"]),
        status_text=(g.get("gameStatusText") or "").strip(),
        period=_int(g.get("period")), clock=parse_clock(g.get("gameClock")),
        start_utc=g.get("gameTimeUTC"),
        home=normalize_team(g["homeTeam"]), away=normalize_team(g["awayTeam"]),
    )


def normalize_scoreboard(raw: dict) -> list[Game]:
    return [normalize_game(g) for g in raw["scoreboard"]["games"]]


def _player(p: dict) -> PlayerLine:
    s = p.get("statistics", {})
    return PlayerLine(
        id=p["personId"], name=p["name"], short_name=p.get("nameI", p["name"]),
        jersey=p.get("jerseyNum", ""), position=p.get("position", ""),
        starter=p.get("starter") == "1", on_court=p.get("oncourt") == "1",
        played=p.get("played") == "1",
        minutes=parse_clock(s.get("minutes")) or "0:00",
        points=_int(s.get("points")), rebounds=_int(s.get("reboundsTotal")),
        assists=_int(s.get("assists")), steals=_int(s.get("steals")),
        blocks=_int(s.get("blocks")), turnovers=_int(s.get("turnovers")),
        fouls=_int(s.get("foulsPersonal")),
        fgm=_int(s.get("fieldGoalsMade")), fga=_int(s.get("fieldGoalsAttempted")),
        tpm=_int(s.get("threePointersMade")), tpa=_int(s.get("threePointersAttempted")),
        ftm=_int(s.get("freeThrowsMade")), fta=_int(s.get("freeThrowsAttempted")),
        plus_minus=float(s.get("plusMinusPoints") or 0),
    )


_TOTAL_KEYS = ("points", "reboundsTotal", "assists", "steals", "blocks", "turnovers",
               "foulsPersonal", "fieldGoalsMade", "fieldGoalsAttempted",
               "threePointersMade", "threePointersAttempted", "freeThrowsMade",
               "freeThrowsAttempted", "pointsInThePaint", "pointsFastBreak",
               "pointsSecondChance", "pointsFromTurnovers", "benchPoints",
               "biggestLead")


def _team_box(t: dict) -> TeamBox:
    stats = t.get("statistics", {})
    return TeamBox(
        team=normalize_team(t),
        players=[_player(p) for p in t.get("players", [])],
        totals={k: float(stats[k]) for k in _TOTAL_KEYS if isinstance(stats.get(k), (int, float))},
    )


def normalize_boxscore(raw: dict) -> BoxScore:
    g = raw["game"]
    return BoxScore(
        game=normalize_game(g),
        arena=(g.get("arena") or {}).get("arenaName"),
        attendance=g.get("attendance"),
        officials=[o.get("name", "") for o in g.get("officials", [])],
        home=_team_box(g["homeTeam"]), away=_team_box(g["awayTeam"]),
    )


_POINT_VALUE = {"2pt": 2, "3pt": 3, "freethrow": 1}


def normalize_play(a: dict) -> Play:
    shot = bool(a.get("isFieldGoal"))
    result = a.get("shotResult")
    # `pointsTotal` is the shooter's running total, not this shot's value.
    made = result == "Made"
    points = _POINT_VALUE.get(a["actionType"], 0) if made else 0
    return Play(
        id=a["actionNumber"], order=a.get("orderNumber", a["actionNumber"]),
        period=a["period"], clock=parse_clock(a.get("clock")),
        team=a.get("teamTricode") or None, player_id=a.get("personId") or None,
        type=a["actionType"], subtype=a.get("subType") or "",
        text=a.get("description", ""),
        home_score=_int(a.get("scoreHome")), away_score=_int(a.get("scoreAway")),
        is_shot=shot, made=(result == "Made") if shot and result else None,
        points=points,
        x=a.get("x") if shot else None, y=a.get("y") if shot else None,
        sx=a.get("xLegacy") if shot else None, sy=a.get("yLegacy") if shot else None, distance=a.get("shotDistance") if shot else None,
        time_utc=a.get("timeActual"), edited_utc=a.get("edited"),
    )


def normalize_playbyplay(raw: dict) -> list[Play]:
    plays = [normalize_play(a) for a in raw["game"]["actions"]]
    # orderNumber is the chronological key; actionNumber is not (late-entered plays such as assists get a
    # high actionNumber but belong earlier). actionNumber stays the stable identity for diffing.
    plays.sort(key=lambda p: (p.order, p.id))
    return plays
