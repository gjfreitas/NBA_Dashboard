"""Player ingestion from stats.nba.com via nba_api.

Must run from a non-cloud IP (stats.nba.com drops cloud ranges). Resumable: every fetched
piece is recorded in `sync`, so re-running skips fresh data.

  python -m nbadash.ingest roster                 # all ~5k players (no network), marks active ones
  python -m nbadash.ingest player 2544 203999     # full sync of specific players
  python -m nbadash.ingest active --limit 30      # active players, stalest first
  python -m nbadash.ingest teams                  # team stats, game log, leaders for previews
  python -m nbadash.ingest props                  # every player's logs + matchup data, 3 seasons (Stats tab)
  python -m nbadash.ingest refresh                # refresh only if games finished / daily (for the scheduler)
  python -m nbadash.ingest status
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Optional, Protocol

from . import db

log = logging.getLogger("nbadash.ingest")

REGULAR, PLAYOFFS = "regular", "playoffs"
NBA_SEASON_TYPE = {REGULAR: "Regular Season", PLAYOFFS: "Playoffs"}


# ---------------------------------------------------------------- fetching ----

class StatsFetcher(Protocol):
    def info(self, pid: int) -> dict: ...
    def career(self, pid: int) -> dict: ...
    def gamelog(self, pid: int, season: str, season_type: str) -> dict: ...
    def shots(self, pid: int, season: str, season_type: str) -> dict: ...
    def team_stats(self, season: str, measure: str) -> dict: ...
    def team_games(self, season: str) -> dict: ...
    def league_players(self, season: str) -> dict: ...
    def standings(self, season: str) -> dict: ...
    def league_game_logs(self, season: str, measure: str = "Base", period: int = 0) -> dict: ...
    def player_zones(self, season: str) -> dict: ...
    def team_zones_def(self, season: str) -> dict: ...
    def player_shot_types(self, season: str, general_range: str) -> dict: ...
    def team_shot_types_def(self, season: str, general_range: str) -> dict: ...
    def synergy(self, season: str, play_type: str, who: str) -> dict: ...
    def player_index(self, season: str) -> dict: ...


class NbaApiFetcher:
    """Throttled, retrying nba_api wrapper. Imports nba_api lazily (heavy: pandas/numpy)."""

    def __init__(self, delay: float = 0.8, timeout: int = 30, retries: int = 3):
        self.delay, self.timeout, self.retries = delay, timeout, retries
        self._install_session()

    @staticmethod
    def _install_session() -> None:
        """urllib3 2.x enables OpenSSL's strict X.509 mode, which rejects some of the certificate chains
        Akamai serves for stats.nba.com ("Basic Constraints of CA cert not marked critical"), intermittently.
        Only that one flag is relaxed; chain and hostname verification stay on."""
        import ssl

        import requests
        from nba_api.library.http import NBAHTTP
        from requests.adapters import HTTPAdapter
        from urllib3.util.ssl_ import create_urllib3_context

        class _Adapter(HTTPAdapter):
            def init_poolmanager(self, *args, **kwargs):
                ctx = create_urllib3_context()
                ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
                super().init_poolmanager(*args, ssl_context=ctx, **kwargs)

        session = requests.Session()
        session.mount("https://", _Adapter())
        NBAHTTP.set_session(session)

    def _call(self, make: Callable[[], Any]) -> dict:
        for attempt in range(1, self.retries + 1):
            try:
                result = make().get_dict()
                time.sleep(self.delay)
                return result
            except Exception as e:  # nba_api surfaces requests/JSON errors directly
                if attempt == self.retries:
                    raise
                wait = self.delay * 2 ** attempt
                log.warning("attempt %d failed (%s: %s); retrying in %.1fs", attempt, type(e).__name__, e, wait)
                time.sleep(wait)
        raise AssertionError("unreachable")

    def info(self, pid: int) -> dict:
        from nba_api.stats.endpoints import commonplayerinfo
        return self._call(lambda: commonplayerinfo.CommonPlayerInfo(player_id=pid, timeout=self.timeout))

    def career(self, pid: int) -> dict:
        from nba_api.stats.endpoints import playercareerstats
        return self._call(lambda: playercareerstats.PlayerCareerStats(player_id=pid, timeout=self.timeout))

    def gamelog(self, pid: int, season: str, season_type: str) -> dict:
        from nba_api.stats.endpoints import playergamelog
        return self._call(lambda: playergamelog.PlayerGameLog(
            player_id=pid, season=season, season_type_all_star=NBA_SEASON_TYPE[season_type], timeout=self.timeout))

    def shots(self, pid: int, season: str, season_type: str) -> dict:
        from nba_api.stats.endpoints import shotchartdetail
        return self._call(lambda: shotchartdetail.ShotChartDetail(
            team_id=0, player_id=pid, season_nullable=season, context_measure_simple="FGA",
            season_type_all_star=NBA_SEASON_TYPE[season_type], timeout=self.timeout * 2))


    def team_stats(self, season: str, measure: str) -> dict:
        from nba_api.stats.endpoints import leaguedashteamstats
        return self._call(lambda: leaguedashteamstats.LeagueDashTeamStats(
            season=season, per_mode_detailed="PerGame", measure_type_detailed_defense=measure, timeout=self.timeout))

    def team_games(self, season: str) -> dict:
        from nba_api.stats.endpoints import leaguegamelog
        return self._call(lambda: leaguegamelog.LeagueGameLog(
            season=season, player_or_team_abbreviation="T", timeout=self.timeout))

    def league_players(self, season: str) -> dict:
        from nba_api.stats.endpoints import leaguedashplayerstats
        return self._call(lambda: leaguedashplayerstats.LeagueDashPlayerStats(
            season=season, per_mode_detailed="PerGame", timeout=self.timeout))

    def standings(self, season: str) -> dict:
        from nba_api.stats.endpoints import leaguestandingsv3
        return self._call(lambda: leaguestandingsv3.LeagueStandingsV3(season=season, timeout=self.timeout))

    # ---- league-wide calls for the props / matchup analysis (one request covers every player or team)
    def league_game_logs(self, season: str, measure: str = "Base", period: int = 0) -> dict:
        from nba_api.stats.endpoints import playergamelogs
        kw = {"period_nullable": period} if period else {}
        return self._call(lambda: playergamelogs.PlayerGameLogs(
            season_nullable=season, measure_type_player_game_logs_nullable=measure, timeout=self.timeout * 4, **kw))

    def player_zones(self, season: str) -> dict:
        from nba_api.stats.endpoints import leaguedashplayershotlocations
        return self._call(lambda: leaguedashplayershotlocations.LeagueDashPlayerShotLocations(
            season=season, distance_range="By Zone", per_mode_detailed="Totals", timeout=self.timeout))

    def team_zones_def(self, season: str) -> dict:
        from nba_api.stats.endpoints import leaguedashteamshotlocations
        return self._call(lambda: leaguedashteamshotlocations.LeagueDashTeamShotLocations(
            season=season, measure_type_simple="Opponent", distance_range="By Zone", per_mode_detailed="Totals",
            timeout=self.timeout))

    def player_shot_types(self, season: str, general_range: str) -> dict:
        from nba_api.stats.endpoints import leaguedashplayerptshot
        return self._call(lambda: leaguedashplayerptshot.LeagueDashPlayerPtShot(
            season=season, general_range_nullable=general_range, per_mode_simple="Totals", timeout=self.timeout))

    def team_shot_types_def(self, season: str, general_range: str) -> dict:
        from nba_api.stats.endpoints import leaguedashoppptshot
        return self._call(lambda: leaguedashoppptshot.LeagueDashOppPtShot(
            season=season, general_range_nullable=general_range, per_mode_simple="Totals", timeout=self.timeout))

    def synergy(self, season: str, play_type: str, who: str) -> dict:
        """who = 'P' (every player, offence) or 'T' (every team, defence)."""
        from nba_api.stats.endpoints import synergyplaytypes
        return self._call(lambda: synergyplaytypes.SynergyPlayTypes(
            league_id="00", per_mode_simple="Totals", player_or_team_abbreviation=who, season=season,
            season_type_all_star="Regular Season", play_type_nullable=play_type,
            type_grouping_nullable="offensive" if who == "P" else "defensive", timeout=self.timeout))

    def player_index(self, season: str) -> dict:
        """Every player who has appeared recently (position, height, team...) in one request."""
        from nba_api.stats.endpoints import playerindex
        return self._call(lambda: playerindex.PlayerIndex(season=season, historical_nullable=1, timeout=self.timeout * 2))


# ----------------------------------------------------------------- storing ----

def rows(d: dict, name: str) -> list[dict]:
    """nba_api resultSets -> list of {HEADER: value}."""
    for rs in d["resultSets"]:
        if rs["name"] == name:
            return [dict(zip(rs["headers"], r)) for r in rs["rowSet"]]
    return []


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def mark(conn: sqlite3.Connection, pid: int, kind: str) -> None:
    conn.execute("INSERT OR REPLACE INTO sync VALUES (?,?,?)", (pid, kind, _now()))


def is_fresh(conn: sqlite3.Connection, pid: int, kind: str, max_age: timedelta) -> bool:
    r = conn.execute("SELECT synced_at FROM sync WHERE player_id=? AND kind=?", (pid, kind)).fetchone()
    return bool(r) and datetime.fromisoformat(r["synced_at"]) > datetime.now(timezone.utc) - max_age


def load_roster(conn: sqlite3.Connection, static_players: list[dict]) -> int:
    """Insert/refresh the static player list (id, name, is_active) without touching bio fields."""
    with conn:
        for p in static_players:
            conn.execute(
                """INSERT INTO players (id, full_name, first_name, last_name, is_active)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET full_name=excluded.full_name,
                     first_name=excluded.first_name, last_name=excluded.last_name,
                     is_active=excluded.is_active""",
                (p["id"], p["full_name"], p["first_name"], p["last_name"], int(p["is_active"])))
    return len(static_players)


def _int(v: Any) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def store_info(conn: sqlite3.Connection, d: dict) -> int:
    r = rows(d, "CommonPlayerInfo")[0]
    pid = r["PERSON_ID"]
    with conn:
        conn.execute(
            """INSERT INTO players (id, full_name, first_name, last_name, slug, is_active, birthdate, country,
                 school, height, weight, jersey, position, roster_status, team_id, team_abbr, team_name,
                 team_city, from_year, to_year, draft_year, draft_round, draft_number, greatest_75)
               VALUES (:id,:full,:first,:last,:slug,:active,:birth,:country,:school,:height,:weight,:jersey,
                 :pos,:status,:team_id,:abbr,:team,:city,:from_year,:to_year,:dy,:dr,:dn,:g75)
               ON CONFLICT(id) DO UPDATE SET full_name=:full, first_name=:first, last_name=:last, slug=:slug,
                 is_active=:active, birthdate=:birth, country=:country, school=:school, height=:height,
                 weight=:weight, jersey=:jersey, position=:pos, roster_status=:status, team_id=:team_id,
                 team_abbr=:abbr, team_name=:team, team_city=:city, from_year=:from_year, to_year=:to_year,
                 draft_year=:dy, draft_round=:dr, draft_number=:dn, greatest_75=:g75""",
            dict(id=pid, full=r["DISPLAY_FIRST_LAST"], first=r["FIRST_NAME"], last=r["LAST_NAME"],
                 slug=r["PLAYER_SLUG"], active=int(r["ROSTERSTATUS"] == "Active"),
                 birth=(r["BIRTHDATE"] or "")[:10] or None, country=r["COUNTRY"], school=r["SCHOOL"],
                 height=r["HEIGHT"], weight=r["WEIGHT"], jersey=r["JERSEY"], pos=r["POSITION"],
                 status=r["ROSTERSTATUS"], team_id=_int(r["TEAM_ID"]) or None, abbr=r["TEAM_ABBREVIATION"] or None,
                 team=r["TEAM_NAME"] or None, city=r["TEAM_CITY"] or None, from_year=_int(r["FROM_YEAR"]),
                 to_year=_int(r["TO_YEAR"]), dy=r["DRAFT_YEAR"], dr=r["DRAFT_ROUND"], dn=r["DRAFT_NUMBER"],
                 g75=int(r["GREATEST_75_FLAG"] == "Y")))
        mark(conn, pid, "info")
    return pid


_SEASON_COLS = ("GP", "GS", "MIN", "FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA", "OREB", "DREB", "REB",
                "AST", "STL", "BLK", "TOV", "PF", "PTS")


def store_career(conn: sqlite3.Connection, pid: int, d: dict) -> None:
    sets = ((REGULAR, "SeasonTotalsRegularSeason", "CareerTotalsRegularSeason"),
            (PLAYOFFS, "SeasonTotalsPostSeason", "CareerTotalsPostSeason"))
    ins = ("INSERT OR REPLACE INTO player_seasons (player_id, season, season_type, team_id, team_abbr, age, gp, gs, "
           "min, fgm, fga, fg3m, fg3a, ftm, fta, oreb, dreb, reb, ast, stl, blk, tov, pf, pts) "
           "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)")
    with conn:
        conn.execute("DELETE FROM player_seasons WHERE player_id=?", (pid,))
        for stype, season_set, career_set in sets:
            for r in rows(d, season_set):
                conn.execute(ins, (pid, r["SEASON_ID"], stype, _int(r["TEAM_ID"]), r["TEAM_ABBREVIATION"] or "",
                                   r["PLAYER_AGE"], *[r[c] for c in _SEASON_COLS]))
            for r in rows(d, career_set):
                conn.execute(ins, (pid, "Career", stype, None, "", None, *[r[c] for c in _SEASON_COLS]))
        mark(conn, pid, "career")


def _iso_date(s: str) -> str:
    return datetime.strptime(s, "%b %d, %Y").date().isoformat()


_LOG_COLS = ("player_id", "game_id", "season", "season_type", "game_date", "matchup", "wl", "min", "fgm", "fga",
             "fg3m", "fg3a", "ftm", "fta", "oreb", "dreb", "reb", "ast", "stl", "blk", "tov", "pf", "pts",
             "plus_minus", "team_id")


def upsert_log(conn: sqlite3.Connection, row: dict) -> None:
    """Insert or refresh the base box-score columns of a game log, keeping usage / quarter extras."""
    cols = [c for c in _LOG_COLS if c in row]
    updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c not in ("player_id", "game_id"))
    conn.execute(f"INSERT INTO player_game_logs ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))}) "
                 f"ON CONFLICT(player_id, game_id) DO UPDATE SET {updates}", [row[c] for c in cols])


def store_gamelog(conn: sqlite3.Connection, pid: int, d: dict, season: str, season_type: str) -> int:
    data = rows(d, "PlayerGameLog")
    with conn:
        conn.execute("DELETE FROM player_game_logs WHERE player_id=? AND season=? AND season_type=?",
                     (pid, season, season_type))
        for r in data:
            upsert_log(conn, dict(
                player_id=pid, game_id=r["Game_ID"], season=season, season_type=season_type,
                game_date=_iso_date(r["GAME_DATE"]), matchup=r["MATCHUP"], wl=r["WL"], min=r["MIN"], fgm=r["FGM"],
                fga=r["FGA"], fg3m=r["FG3M"], fg3a=r["FG3A"], ftm=r["FTM"], fta=r["FTA"], oreb=r["OREB"],
                dreb=r["DREB"], reb=r["REB"], ast=r["AST"], stl=r["STL"], blk=r["BLK"], tov=r["TOV"], pf=r["PF"],
                pts=r["PTS"], plus_minus=r["PLUS_MINUS"]))
        mark(conn, pid, f"gamelog:{season}:{season_type}")
    return len(data)


def store_shots(conn: sqlite3.Connection, pid: int, d: dict, season: str, season_type: str) -> int:
    data = rows(d, "Shot_Chart_Detail")
    with conn:
        conn.execute("DELETE FROM player_shots WHERE player_id=? AND season=? AND season_type=?",
                     (pid, season, season_type))
        for r in data:
            gd = r["GAME_DATE"]
            conn.execute(
                "INSERT OR REPLACE INTO player_shots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (pid, r["GAME_ID"], r["GAME_EVENT_ID"], season, season_type, f"{gd[:4]}-{gd[4:6]}-{gd[6:]}",
                 r["PERIOD"], r["MINUTES_REMAINING"], r["SECONDS_REMAINING"], r["ACTION_TYPE"], r["SHOT_TYPE"],
                 r["SHOT_ZONE_BASIC"], r["SHOT_ZONE_AREA"], r["SHOT_ZONE_RANGE"], r["SHOT_DISTANCE"],
                 r["LOC_X"], r["LOC_Y"], int(r["SHOT_MADE_FLAG"])))
        mark(conn, pid, f"shots:{season}:{season_type}")
    return len(data)


def current_season(today: Optional[date] = None) -> str:
    t = today or date.today()
    y = t.year if t.month >= 10 else t.year - 1
    return f"{y}-{str(y + 1)[2:]}"


def previous_season(season: str) -> str:
    y = int(season[:4]) - 1
    return f"{y}-{str(y + 1)[2:]}"


def store_team_stats(conn: sqlite3.Connection, season: str, base: dict, advanced: dict) -> int:
    adv = {r["TEAM_ID"]: r for r in rows(advanced, "LeagueDashTeamStats")}
    data = rows(base, "LeagueDashTeamStats")
    with conn:
        conn.execute("DELETE FROM team_season WHERE season=?", (season,))
        for r in data:
            a = adv.get(r["TEAM_ID"], {})
            conn.execute(
                "INSERT INTO team_season VALUES (" + ",".join("?" * 30) + ")",
                (r["TEAM_ID"], season, r["TEAM_NAME"], r["GP"], r["W"], r["L"], r["PTS"], r["REB"], r["AST"],
                 r["STL"], r["BLK"], r["TOV"], r["FG_PCT"], r["FG3_PCT"], r["FT_PCT"], r["PLUS_MINUS"],
                 a.get("OFF_RATING"), a.get("DEF_RATING"), a.get("NET_RATING"), a.get("PACE"), a.get("TS_PCT"),
                 r["PTS_RANK"], r["REB_RANK"], r["AST_RANK"], r["FG_PCT_RANK"], r["FG3_PCT_RANK"],
                 a.get("OFF_RATING_RANK"), a.get("DEF_RATING_RANK"), a.get("NET_RATING_RANK"), a.get("PACE_RANK")))
        mark(conn, 0, f"teamstats:{season}")
    return len(data)


def store_team_games(conn: sqlite3.Connection, season: str, d: dict) -> int:
    data = rows(d, "LeagueGameLog")
    with conn:
        conn.execute("DELETE FROM team_games WHERE season=?", (season,))
        for r in data:
            m = r["MATCHUP"]  # "GSW @ LAL" (away) or "LAL vs. GSW" (home)
            conn.execute("INSERT OR REPLACE INTO team_games VALUES (?,?,?,?,?,?,?,?,?,?)",
                         (r["TEAM_ID"], r["GAME_ID"], season, r["TEAM_ABBREVIATION"], m.split()[-1],
                          r["GAME_DATE"], int(" vs. " in m), r["WL"], r["PTS"], r["PLUS_MINUS"]))
        mark(conn, 0, f"teamgames:{season}")
    return len(data)


def store_league_players(conn: sqlite3.Connection, season: str, d: dict) -> int:
    data = rows(d, "LeagueDashPlayerStats")
    with conn:
        conn.execute("DELETE FROM league_players WHERE season=?", (season,))
        for r in data:
            conn.execute("INSERT OR REPLACE INTO league_players VALUES (?,?,?,?,?,?,?,?,?)",
                         (r["PLAYER_ID"], season, r["TEAM_ID"], r["PLAYER_NAME"], r["GP"], r["MIN"], r["PTS"], r["REB"], r["AST"]))
        mark(conn, 0, f"leagueplayers:{season}")
    return len(data)


def clinch_code(r: dict) -> str:
    """Standard notation from the NBA's explicit flags (its own ClinchIndicator codes are opaque):
    z top seed, y division title, x playoff berth, pi play-in secured, e eliminated, '' undecided."""
    if r.get("ClinchedConferenceTitle") == 1:
        return "z"
    if r.get("ClinchedDivisionTitle") == 1:
        return "y"
    if r.get("ClinchedPlayoffBirth") == 1:
        return "x"
    if r.get("ClinchedPlayIn") == 1:
        return "pi"
    return "e" if r.get("EliminatedConference") == 1 else ""


def store_standings(conn: sqlite3.Connection, season: str, d: dict) -> int:
    data = rows(d, "Standings")
    with conn:
        conn.execute("DELETE FROM standings WHERE season=?", (season,))
        for r in data:
            conn.execute(
                """INSERT INTO teams (id, city, name, slug, conference, division) VALUES (?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET city=excluded.city, name=excluded.name, slug=excluded.slug,
                     conference=excluded.conference, division=excluded.division""",
                (r["TeamID"], r["TeamCity"], r["TeamName"], r["TeamSlug"], r["Conference"], r["Division"]))
            conn.execute(
                "INSERT INTO standings VALUES (" + ",".join("?" * 19) + ")",
                (r["TeamID"], season, r["PlayoffRank"], r["DivisionRank"], r["LeagueRank"], r["WINS"], r["LOSSES"],
                 r["WinPCT"], r["ConferenceGamesBack"], r["HOME"], r["ROAD"], r["L10"], (r["strCurrentStreak"] or "").strip(),
                 r["ConferenceRecord"], r["DivisionRecord"], r["PointsPG"], r["OppPointsPG"], r["DiffPointsPG"],
                 clinch_code(r)))
        mark(conn, 0, f"standings:{season}")
    return len(data)


def store_schedule(conn: sqlite3.Connection, d: dict) -> int:
    ls = d["leagueSchedule"]
    season = ls["seasonYear"]
    n = 0
    with conn:
        conn.execute("DELETE FROM schedule WHERE season=?", (season,))
        for day in ls["gameDates"]:
            for g in day["games"]:
                if g["gameId"].startswith("001"):  # preseason: not part of any record
                    continue
                h, a = g["homeTeam"], g["awayTeam"]
                conn.execute("INSERT OR REPLACE INTO schedule VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                             (g["gameId"], season, g["gameDateEst"][:10], g["gameDateTimeUTC"], g["gameStatus"],
                              (g["gameStatusText"] or "").strip(), h["teamId"], a["teamId"], h["teamTricode"], a["teamTricode"],
                              h["score"], a["score"], g["gameLabel"] or None, g["gameSubLabel"] or None, g["arenaName"] or None))
                # the schedule carries every team's tricode: keep the team directory's abbreviations in sync
                for t in (h, a):
                    conn.execute("UPDATE teams SET abbr=? WHERE id=?", (t["teamTricode"], t["teamId"]))
                n += 1
        mark(conn, 0, f"schedule:{season}")
    return n


SCHEDULE_URL = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json"


def fetch_schedule_json() -> dict:
    """The CDN needs a browser TLS fingerprint (plain requests get 403), hence curl_cffi."""
    from curl_cffi import requests as cffi
    r = cffi.get(SCHEDULE_URL, impersonate="chrome", timeout=60,
                 headers={"Referer": "https://www.nba.com/", "Origin": "https://www.nba.com"})
    r.raise_for_status()
    return r.json()


def sync_schedule(conn: sqlite3.Connection, fetch: Callable[[], dict] = fetch_schedule_json,
                  max_age: timedelta = timedelta(hours=1)) -> int:
    """Season schedule (~1.2k games, one 7 MB request). Returns games stored, 0 if still fresh."""
    latest = conn.execute("SELECT MAX(synced_at) m FROM sync WHERE player_id=0 AND kind LIKE 'schedule:%'").fetchone()["m"]
    if latest and datetime.fromisoformat(latest) > datetime.now(timezone.utc) - max_age:
        return 0
    return store_schedule(conn, fetch())


def sync_league(conn: sqlite3.Connection, fetcher: StatsFetcher, seasons: Optional[list[str]] = None,
                max_age: timedelta = timedelta(hours=6)) -> dict:
    """League-wide data for team previews: a handful of API calls per season cover all 30 teams."""
    cur = current_season()
    out = {}
    for season in seasons or [cur, previous_season(cur)]:
        n = {}
        if not is_fresh(conn, 0, f"teamstats:{season}", max_age):
            n["teams"] = store_team_stats(conn, season, fetcher.team_stats(season, "Base"), fetcher.team_stats(season, "Advanced"))
        if not is_fresh(conn, 0, f"teamgames:{season}", max_age):
            n["games"] = store_team_games(conn, season, fetcher.team_games(season))
        if not is_fresh(conn, 0, f"leagueplayers:{season}", max_age):
            n["players"] = store_league_players(conn, season, fetcher.league_players(season))
        if not is_fresh(conn, 0, f"standings:{season}", max_age):
            n["standings"] = store_standings(conn, season, fetcher.standings(season))
        out[season] = n
    return out


# ------------------------------------------------------------ orchestration ----

class Throttle:
    """Back off when stats.nba.com starts timing out. It rate-limits bursts and recovers after a pause, so hammering
    it with retries only prolongs the block: after `trip_after` players in a row fail, sleep `cooldown` seconds and
    slow the pacing; pacing eases back toward normal as players succeed again."""

    def __init__(self, fetcher: "NbaApiFetcher", trip_after: int = 2, cooldown: float = 300.0, sleep: Callable[[float], None] = time.sleep):
        self.fetcher, self.trip_after, self.cooldown, self.sleep = fetcher, trip_after, cooldown, sleep
        self.base_delay, self.failures = fetcher.delay, 0

    def ok(self) -> None:
        self.failures = 0
        self.fetcher.delay = max(self.base_delay, self.fetcher.delay * 0.9)

    def failed(self) -> bool:
        """Record a failed player; returns True when it paused."""
        self.failures += 1
        if self.failures < self.trip_after:
            return False
        log.warning("%d players in a row failed: stats.nba.com is throttling. Pausing %.0f s and slowing down.", self.failures, self.cooldown)
        self.sleep(self.cooldown)
        self.fetcher.delay = min(max(self.fetcher.delay, self.base_delay) * 1.5, 3.0)
        self.failures = 0
        return True


def sync_player(conn: sqlite3.Connection, fetcher: StatsFetcher, pid: int, *, recent_seasons: int = 2,
                seasons: Optional[list[str]] = None, max_age: timedelta = timedelta(hours=12), gamelogs: bool = True) -> dict:
    """Sync bio, career splits, and game logs + shot charts for the player's most recent seasons.

    gamelogs=False skips the per-player game-log calls: `ingest props` already stores every player's logs league-wide."""
    done = {"info": False, "career": False, "gamelogs": 0, "shots": 0}
    if not is_fresh(conn, pid, "info", max_age):
        store_info(conn, fetcher.info(pid))
        done["info"] = True
    if not is_fresh(conn, pid, "career", max_age):
        store_career(conn, pid, fetcher.career(pid))
        done["career"] = True

    have = conn.execute(
        "SELECT DISTINCT season, season_type FROM player_seasons WHERE player_id=? AND season!='Career' AND gp>0 "
        "ORDER BY season DESC", (pid,)).fetchall()
    played = {(r["season"], r["season_type"]) for r in have}
    wanted = seasons or sorted({s for s, _ in played}, reverse=True)[:recent_seasons]
    for season in wanted:
        for stype in (REGULAR, PLAYOFFS):
            if (season, stype) not in played:
                continue  # don't ask the API for playoff data a player doesn't have
            if gamelogs and not is_fresh(conn, pid, f"gamelog:{season}:{stype}", max_age):
                done["gamelogs"] += store_gamelog(conn, pid, fetcher.gamelog(pid, season, stype), season, stype)
            if not is_fresh(conn, pid, f"shots:{season}:{stype}", max_age):
                done["shots"] += store_shots(conn, pid, fetcher.shots(pid, season, stype), season, stype)
    return done


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="nbadash.ingest", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", help="SQLite path (default $NBA_DB or backend/data/nba.db)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("roster")
    sub.add_parser("status")
    sub.add_parser("refresh", help="refresh when new games have finished (for a scheduler); see `refresh --help`", add_help=False)
    pr = sub.add_parser("props", help="league-wide logs, usage, quarters, zones, shot and play types (Stats tab)")
    pr.add_argument("--seasons", nargs="*", help="default: the current and two previous seasons")
    t = sub.add_parser("teams", help="team stats, team games, player averages, standings and schedule (previews, standings, team pages)")
    t.add_argument("--seasons", nargs="*")
    p = sub.add_parser("player"); p.add_argument("ids", nargs="+", type=int)
    p.add_argument("--seasons", nargs="*", help="e.g. 2024-25 2025-26 (default: most recent N)")
    p.add_argument("--recent", type=int, default=2)
    p.add_argument("--with-gamelogs", action="store_true", help="also fetch per-player game logs (normally covered by `props`)")
    a = sub.add_parser("active"); a.add_argument("--limit", type=int, default=0)
    a.add_argument("--recent", type=int, default=2); a.add_argument("--stale-hours", type=float, default=12)
    a.add_argument("--with-gamelogs", action="store_true")
    argv = list(sys.argv[1:] if argv is None else argv)
    if "refresh" in argv:
        from . import refresh
        rest = argv[argv.index("refresh") + 1:]
        db_args = argv[:argv.index("refresh")]  # e.g. a leading --db path
        return refresh.main(db_args + rest if "--db" in db_args else rest)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    conn = db.connect(args.db)

    if args.cmd == "roster":
        from nba_api.stats.static import players
        print(f"loaded {load_roster(conn, players.get_players())} players")
    elif args.cmd == "status":
        for t in ("players", "player_seasons", "player_game_logs", "player_shots"):
            print(f"{t:18} {conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]}")
        print("synced players:", conn.execute("SELECT COUNT(DISTINCT player_id) FROM sync WHERE kind='info'").fetchone()[0])
    elif args.cmd == "props":
        from . import props_ingest
        print(props_ingest.sync_props(conn, NbaApiFetcher(), args.seasons or None))
    elif args.cmd == "teams":
        print(sync_league(conn, NbaApiFetcher(), args.seasons or None))
        print("schedule games:", sync_schedule(conn))
    else:
        fetcher = NbaApiFetcher()
        if args.cmd == "player":
            ids, kw = args.ids, dict(recent_seasons=args.recent, seasons=args.seasons or None, gamelogs=args.with_gamelogs)
        else:
            q = ("SELECT p.id FROM players p LEFT JOIN sync s ON s.player_id=p.id AND s.kind='info' "
                 "WHERE p.is_active=1 ORDER BY s.synced_at IS NOT NULL, s.synced_at")
            ids = [r["id"] for r in conn.execute(q)]
            ids = ids[: args.limit] if args.limit else ids
            kw = dict(recent_seasons=args.recent, max_age=timedelta(hours=args.stale_hours), gamelogs=args.with_gamelogs)
        throttle = Throttle(fetcher)
        for i, pid in enumerate(ids, 1):
            try:
                print(f"[{i}/{len(ids)}] {pid}: {sync_player(conn, fetcher, pid, **kw)}")
                throttle.ok()
            except Exception as e:
                log.error("player %s failed: %s: %s", pid, type(e).__name__, e)
                throttle.failed()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
