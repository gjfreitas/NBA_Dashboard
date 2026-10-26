"""League-wide ingestion behind the player Stats tab.

Each stats.nba.com request below covers EVERY player (or team) for a season, so a season costs ~45 calls
instead of hundreds of per-player ones:
  * PlayerGameLogs   base / usage / 1st quarter / 2nd quarter  -> player_game_logs (all players, all games)
  * shot zones       player + opponent (team) side
  * shot types       catch & shoot, pull-ups, < 10 ft; player + opponent side
  * Synergy play types, player offence + team defence
Run from a non-cloud IP. Resumable: every piece is skipped while fresh (see ingest.is_fresh).
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import timedelta
from typing import Any, Optional

from . import ingest
from .ingest import StatsFetcher, _int, current_season, is_fresh, mark, previous_season, rows, upsert_log

log = logging.getLogger("nbadash.props")

SEASONS_BACK = 3

# NBA game-id prefixes -> season_type. Preseason (001), all-star (003) and the NBA Cup final (006) are not
# part of anyone's regular-season line, so they are not stored.
GAME_TYPE = {"002": "regular", "004": "playoffs", "005": "playin"}

ZONES = ["Restricted Area", "In The Paint (Non-RA)", "Mid-Range", "Left Corner 3", "Right Corner 3", "Above the Break 3"]

SHOT_TYPES = {"Catch and Shoot": "catch_shoot", "Pullups": "pullup", "Less Than 10 ft": "under_10"}

# the API's query value -> (stored key); stored value is whatever PLAY_TYPE the API returns for the rows
PLAY_TYPES = ["Isolation", "Transition", "PRBallHandler", "PRRollman", "Postup", "Spotup", "Handoff", "Cut",
              "OffScreen", "OffRebound", "Misc"]


def default_seasons() -> list[str]:
    out = [current_season()]
    while len(out) < SEASONS_BACK:
        out.append(previous_season(out[-1]))
    return out


# ------------------------------------------------------------ player index ----

_POSITION_WORDS = {"G": "Guard", "F": "Forward", "C": "Center"}


def position_words(code: Optional[str]) -> Optional[str]:
    """'G-F' -> 'Guard-Forward' (the wording CommonPlayerInfo uses, so pages read the same either way)."""
    if not code:
        return None
    return "-".join(_POSITION_WORDS.get(part, part) for part in code.split("-"))


def store_player_index(conn: sqlite3.Connection, d: dict) -> int:
    """Fill position / jersey / height / weight / team for every player. Existing values are kept when the index has none."""
    data = rows(d, "PlayerIndex")
    with conn:
        for r in data:
            first, last = r["PLAYER_FIRST_NAME"] or "", r["PLAYER_LAST_NAME"] or ""
            conn.execute(
                """INSERT INTO players (id, full_name, first_name, last_name, slug, position, jersey, height, weight,
                                        team_id, team_abbr, team_name, team_city, country)
                   VALUES (:id, :full, :first, :last, :slug, :pos, :jersey, :height, :weight, :tid, :abbr, :tname, :city, :country)
                   ON CONFLICT(id) DO UPDATE SET
                     position = COALESCE(:pos, position), jersey = COALESCE(:jersey, jersey), height = COALESCE(:height, height),
                     weight = COALESCE(:weight, weight), country = COALESCE(:country, country), slug = COALESCE(:slug, slug),
                     team_id = COALESCE(:tid, team_id), team_abbr = COALESCE(:abbr, team_abbr),
                     team_name = COALESCE(:tname, team_name), team_city = COALESCE(:city, team_city)""",
                dict(id=r["PERSON_ID"], full=f"{first} {last}".strip(), first=first, last=last, slug=r["PLAYER_SLUG"],
                     pos=position_words(r["POSITION"]), jersey=r["JERSEY_NUMBER"] or None, height=r["HEIGHT"] or None,
                     weight=r["WEIGHT"] or None, tid=r["TEAM_ID"] or None, abbr=r["TEAM_ABBREVIATION"] or None,
                     tname=r["TEAM_NAME"] or None, city=r["TEAM_CITY"] or None, country=r["COUNTRY"] or None))
        mark(conn, 0, "playerindex")
    return len(data)


# --------------------------------------------------------------- game logs ----

def _log_row(r: dict, season: str) -> Optional[dict]:
    stype = GAME_TYPE.get(r["GAME_ID"][:3])
    if stype is None:
        return None
    return dict(
        player_id=r["PLAYER_ID"], game_id=r["GAME_ID"], season=season, season_type=stype, game_date=r["GAME_DATE"][:10],
        matchup=r["MATCHUP"], wl=r["WL"], min=r["MIN"], fgm=r["FGM"], fga=r["FGA"], fg3m=r["FG3M"], fg3a=r["FG3A"],
        ftm=r["FTM"], fta=r["FTA"], oreb=r["OREB"], dreb=r["DREB"], reb=r["REB"], ast=r["AST"], stl=r["STL"],
        blk=r["BLK"], tov=r["TOV"], pf=r["PF"], pts=r["PTS"], plus_minus=r["PLUS_MINUS"], team_id=r["TEAM_ID"])


def store_league_logs(conn: sqlite3.Connection, season: str, d: dict) -> int:
    n = 0
    with conn:
        for r in rows(d, "PlayerGameLogs"):
            row = _log_row(r, season)
            if row:
                upsert_log(conn, row)
                n += 1
        mark(conn, 0, f"pgl:{season}:base")
    return n


def store_log_extras(conn: sqlite3.Connection, season: str, kind: str, d: dict) -> int:
    """kind: 'usage' | 'q1' | 'q2'. Only updates games already stored by store_league_logs."""
    n = 0
    with conn:
        for r in rows(d, "PlayerGameLogs"):
            if kind == "usage":
                cur = conn.execute("UPDATE player_game_logs SET usg_pct=? WHERE player_id=? AND game_id=?",
                                   (r["USG_PCT"], r["PLAYER_ID"], r["GAME_ID"]))
            elif kind == "q1":
                cur = conn.execute("UPDATE player_game_logs SET q1_pts=?, q1_reb=?, q1_ast=? WHERE player_id=? AND game_id=?",
                                   (r["PTS"], r["REB"], r["AST"], r["PLAYER_ID"], r["GAME_ID"]))
            else:
                cur = conn.execute("UPDATE player_game_logs SET q2_pts=? WHERE player_id=? AND game_id=?",
                                   (r["PTS"], r["PLAYER_ID"], r["GAME_ID"]))
            n += cur.rowcount
        mark(conn, 0, f"pgl:{season}:{kind}")
    return n


# ------------------------------------------------------------------- zones ----

def _zone_triples(d: dict, skip: int, fgm_first: bool = True) -> list[tuple[list, dict[str, tuple[int, int]]]]:
    """Zone result sets are 'wide': `skip` id columns then (FGM, FGA, FG_PCT) per zone, in header order."""
    rs = d["resultSets"]
    zone_names = rs["headers"][0]["columnNames"]
    out = []
    for row in rs["rowSet"]:
        z = {}
        for i, name in enumerate(zone_names):
            if name in ZONES:
                z[name] = (_int(row[skip + 3 * i]) or 0, _int(row[skip + 3 * i + 1]) or 0)
        out.append((row, z))
    return out


def store_player_zones(conn: sqlite3.Connection, season: str, d: dict) -> int:
    n = 0
    with conn:
        conn.execute("DELETE FROM player_zones WHERE season=?", (season,))
        for row, z in _zone_triples(d, skip=6):
            for zone, (fgm, fga) in z.items():
                conn.execute("INSERT INTO player_zones VALUES (?,?,?,?,?)", (row[0], season, zone, fgm, fga))
                n += 1
        mark(conn, 0, f"zones:{season}:player")
    return n


def store_team_zones(conn: sqlite3.Connection, season: str, d: dict) -> int:
    n = 0
    with conn:
        conn.execute("DELETE FROM team_zones_def WHERE season=?", (season,))
        for row, z in _zone_triples(d, skip=2):
            for zone, (fgm, fga) in z.items():
                conn.execute("INSERT INTO team_zones_def VALUES (?,?,?,?,?)", (row[0], season, zone, fgm, fga))
                n += 1
        mark(conn, 0, f"zones:{season}:team")
    return n


# --------------------------------------------------------------- shot types ----

def store_shot_types(conn: sqlite3.Connection, season: str, key: str, player: dict, team: dict) -> int:
    n = 0
    with conn:
        conn.execute("DELETE FROM player_shot_types WHERE season=? AND shot_type=?", (season, key))
        conn.execute("DELETE FROM team_shot_types_def WHERE season=? AND shot_type=?", (season, key))
        for r in rows(player, "LeagueDashPTShots"):
            conn.execute("INSERT INTO player_shot_types VALUES (?,?,?,?,?,?,?,?)",
                         (r["PLAYER_ID"], season, key, r["FGM"], r["FGA"], r["FG3M"], r["FG3A"], r["GP"]))
            n += 1
        for r in rows(team, "LeagueDashPTShots"):
            conn.execute("INSERT INTO team_shot_types_def VALUES (?,?,?,?,?,?,?)",
                         (r["TEAM_ID"], season, key, r["FGM"], r["FGA"], r["FG3M"], r["FG3A"]))
        mark(conn, 0, f"shottype:{season}:{key}")
    return n


# --------------------------------------------------------------- play types ----

def store_play_type(conn: sqlite3.Connection, season: str, play_type: str, player: dict, team: dict) -> int:
    n = 0
    with conn:
        for r in rows(player, "SynergyPlayType"):
            conn.execute("INSERT OR REPLACE INTO player_play_types VALUES (?,?,?,?,?,?,?,?)",
                         (r["PLAYER_ID"], season, r["PLAY_TYPE"], r["GP"], r["POSS"], r["PTS"], r["FGM"], r["FGA"]))
            n += 1
        for r in rows(team, "SynergyPlayType"):
            conn.execute("INSERT OR REPLACE INTO team_play_types_def VALUES (?,?,?,?,?)",
                         (r["TEAM_ID"], season, r["PLAY_TYPE"], r["POSS"], r["PTS"]))
        mark(conn, 0, f"playtype:{season}:{play_type}")
    return n


# ------------------------------------------------------------ orchestration ----

def sync_props(conn: sqlite3.Connection, fetcher: StatsFetcher, seasons: Optional[list[str]] = None,
               max_age: timedelta = timedelta(hours=12), profile_max_age: Optional[timedelta] = None) -> dict[str, Any]:
    """max_age governs the game-driven tables (logs, team stats, standings); profile_max_age the slow-moving ones
    (player index, shot zones, shot types, play types), defaulting to max_age."""
    seasons = seasons or default_seasons()
    slow = max_age if profile_max_age is None else profile_max_age
    out: dict[str, Any] = {}
    # team directory, team ratings/ranks, standings (opponent defence ranks use team_season)
    ingest.sync_league(conn, fetcher, seasons, max_age)
    if not is_fresh(conn, 0, "playerindex", slow):
        out["player_index"] = store_player_index(conn, fetcher.player_index(seasons[0]))
    for season in seasons:
        n: dict[str, int] = {}

        if not is_fresh(conn, 0, f"pgl:{season}:base", max_age):
            n["logs"] = store_league_logs(conn, season, fetcher.league_game_logs(season, "Base"))
        for kind, measure, period in (("usage", "Usage", 0), ("q1", "Base", 1), ("q2", "Base", 2)):
            if not is_fresh(conn, 0, f"pgl:{season}:{kind}", max_age):
                n[kind] = store_log_extras(conn, season, kind, fetcher.league_game_logs(season, measure, period))

        if not is_fresh(conn, 0, f"zones:{season}:player", slow):
            n["player_zones"] = store_player_zones(conn, season, fetcher.player_zones(season))
        if not is_fresh(conn, 0, f"zones:{season}:team", slow):
            n["team_zones"] = store_team_zones(conn, season, fetcher.team_zones_def(season))

        for api_name, key in SHOT_TYPES.items():
            if not is_fresh(conn, 0, f"shottype:{season}:{key}", slow):
                n[f"shot_{key}"] = store_shot_types(conn, season, key, fetcher.player_shot_types(season, api_name),
                                                    fetcher.team_shot_types_def(season, api_name))

        for pt in PLAY_TYPES:
            if not is_fresh(conn, 0, f"playtype:{season}:{pt}", slow):
                n[f"play_{pt}"] = store_play_type(conn, season, pt, fetcher.synergy(season, pt, "P"), fetcher.synergy(season, pt, "T"))
        out[season] = n
        log.info("props %s: %s", season, n)
    return out
