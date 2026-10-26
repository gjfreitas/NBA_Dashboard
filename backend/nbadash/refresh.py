"""Keep the database current without anyone remembering to run ingestion.

  python -m nbadash.ingest refresh              one pass: refresh only if there is something new (meant for a scheduler)
  python -m nbadash.ingest refresh --force      refresh now
  python -m nbadash.ingest refresh --watch      stay running and check every --interval minutes

Every pass first updates injuries and lineups (the NBA files a new injury report every 15 minutes), then the rest. A pass refreshes the rest when
  * a game has finished that the database doesn't know about yet (checked against the live scoreboard), or
  * the last successful refresh is more than a day old (catch-up if the machine was off overnight),
and never twice within --min-gap minutes. What it refreshes, for the current season only (older seasons don't change):
  game-driven data every time  -> team stats, standings, every team game, every player's game log (usage, quarters),
                                  the season schedule
  slow-moving data once a day  -> shot zones, shot types, play types, player positions/teams
Runs from a non-cloud IP like all stats.nba.com ingestion (see ingest.py).
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Callable, Optional

from . import db, espn_injuries, health, ingest, injuries, lineups, odds, props_ingest, webget
from .ingest import StatsFetcher, current_season

log = logging.getLogger("nbadash.refresh")

LAST_KIND = "refresh:last"
COUNTED_PREFIXES = ("002", "004", "005")  # regular season, playoffs, play-in; preseason / all-star never change a record


def fetch_scoreboard() -> dict:
    """Today's scoreboard from the NBA CDN (needs a browser TLS fingerprint, hence curl_cffi)."""
    from curl_cffi import requests as cffi
    r = cffi.get("https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json", impersonate="chrome", timeout=30,
                 headers={"Referer": "https://www.nba.com/", "Origin": "https://www.nba.com"})
    r.raise_for_status()
    return r.json()


def finished_game_ids(scoreboard: dict) -> list[str]:
    return [g["gameId"] for g in scoreboard["scoreboard"]["games"] if g["gameStatus"] == 3 and g["gameId"].startswith(COUNTED_PREFIXES)]


def unknown_finals(conn: sqlite3.Connection, scoreboard: dict) -> list[str]:
    """Finished games on the scoreboard that no team's game log in the database contains yet."""
    ids = finished_game_ids(scoreboard)
    if not ids:
        return []
    have = {r[0] for r in conn.execute(f"SELECT DISTINCT game_id FROM team_games WHERE game_id IN ({','.join('?' * len(ids))})", ids)}
    return [i for i in ids if i not in have]


def last_refresh(conn: sqlite3.Connection) -> Optional[datetime]:
    r = conn.execute("SELECT synced_at FROM sync WHERE player_id=0 AND kind=?", (LAST_KIND,)).fetchone()
    return datetime.fromisoformat(r["synced_at"]) if r else None


def should_refresh(conn: sqlite3.Connection, scoreboard: Optional[dict], *, now: Optional[datetime] = None, force: bool = False,
                   min_gap: timedelta = timedelta(minutes=30), daily: timedelta = timedelta(hours=24)) -> tuple[bool, str]:
    now = now or datetime.now(timezone.utc)
    if force:
        return True, "forced"
    last = last_refresh(conn)
    if last is None:
        return True, "never refreshed"
    since = now - last
    if since < min_gap:
        return False, f"refreshed {int(since.total_seconds() // 60)} min ago"
    new = unknown_finals(conn, scoreboard) if scoreboard else []
    if new:
        return True, f"{len(new)} finished game(s) not in the database yet: {', '.join(new)}"
    if since >= daily:
        return True, f"last refresh was {int(since.total_seconds() // 3600)} h ago"
    return False, "up to date"


def run_refresh(conn: sqlite3.Connection, fetcher: StatsFetcher, *, seasons: Optional[list[str]] = None,
                fetch_schedule: Optional[Callable[[], dict]] = None,
                profile_max_age: timedelta = timedelta(hours=24)) -> dict[str, Any]:
    """Refresh the current season's game-driven data (always) and slow-moving profile data (if older than profile_max_age)."""
    seasons = seasons or [current_season()]
    started = time.monotonic()
    out: dict[str, Any] = {"seasons": seasons}
    # max_age=0 -> every game-driven piece is refetched; profile pieces obey profile_max_age
    out["props"] = props_ingest.sync_props(conn, fetcher, seasons, max_age=timedelta(0), profile_max_age=profile_max_age)
    out["schedule_games"] = ingest.sync_schedule(conn, fetch_schedule or ingest.fetch_schedule_json, max_age=timedelta(0))
    ingest.mark(conn, 0, LAST_KIND)
    conn.commit()
    out["seconds"] = round(time.monotonic() - started, 1)
    return out


def refresh_once(conn: sqlite3.Connection, fetcher: StatsFetcher, *, force: bool = False, min_gap: timedelta = timedelta(minutes=30),
                 get_scoreboard: Optional[Callable[[], dict]] = None, availability: Optional[Callable[[sqlite3.Connection], dict]] = None,
                 **kw) -> Optional[dict]:
    """One scheduler pass: always the availability feeds (cheap), then the heavy refresh only if something new happened.
    Returns the heavy refresh summary, or None when it was skipped."""
    avail = refresh_availability(conn) if availability is None else availability(conn)
    health.record(conn, "pass")  # the scheduler itself is alive, whatever the sources did
    refresh_odds(conn)
    if avail.get("injuries", {}).get("new") or avail.get("lineup_changes"):
        log.info("availability: %s", avail)
    scoreboard = None
    if not force:
        try:
            scoreboard = (get_scoreboard or fetch_scoreboard)()
        except Exception as e:  # a scoreboard hiccup must not block the daily catch-up
            log.warning("scoreboard unavailable (%s: %s); relying on the daily catch-up", type(e).__name__, e)
    go, why = should_refresh(conn, scoreboard, force=force, min_gap=min_gap)
    if not go:
        log.info("skip: %s", why)
        return None
    log.info("refreshing: %s", why)
    try:
        result = run_refresh(conn, fetcher, **kw)
    except Exception as e:
        health.record(conn, "refresh", f"{type(e).__name__}: {e}")
        raise
    health.record(conn, "refresh")
    log.info("refreshed in %.1fs: %s", result["seconds"], result["props"])
    return result


def refresh_availability(conn: sqlite3.Connection) -> dict[str, Any]:
    """Injury report + today's/tomorrow's lineups. Two or three small requests, so it runs on EVERY pass (the NBA files a new
    injury report every 15 minutes). A failure in one source is logged and doesn't stop the other, or the heavy refresh."""
    out: dict[str, Any] = {}
    try:
        out["injuries"] = injuries.sync_injuries(conn, catch_up_hours=3)
        health.record(conn, "injuries")
    except Exception as e:  # network, a PDF layout change... never fatal here
        log.warning("injury report: %s: %s", type(e).__name__, e)
        out["injuries_error"] = str(e)
        health.record(conn, "injuries", f"{type(e).__name__}: {e}")
    try:
        out["espn"] = espn_injuries.sync_espn(conn)  # unofficial secondary source; fetched at most once an hour
        health.record(conn, "espn")
    except Exception as e:
        log.warning("ESPN injuries: %s: %s", type(e).__name__, e)
        out["espn_error"] = str(e)
        health.record(conn, "espn", f"{type(e).__name__}: {e}")
    try:
        changes = lineups.poll(conn)
        out["lineup_changes"] = len(changes)
        health.record(conn, "lineups")
    except (webget.FetchError, ValueError) as e:
        log.warning("lineups: %s: %s", type(e).__name__, e)
        out["lineups_error"] = str(e)
        health.record(conn, "lineups", f"{type(e).__name__}: {e}")
    return out


def refresh_odds(conn: sqlite3.Connection) -> dict[str, Any]:
    """Prop lines from the configured odds API, at most once every ODDS_MIN_HOURS hours. Does nothing without an API key.
    A failure is logged and recorded for the status page; it never stops the rest of the pass."""
    try:
        out = odds.sync_odds(conn)
    except Exception as e:  # a refused key, a quota, a network error, a changed response
        log.warning("odds: %s: %s", type(e).__name__, e)
        health.record(conn, "odds", f"{type(e).__name__}: {e}")
        return {"odds_error": str(e)}
    if out.get("skipped") != "no odds API key set":
        health.record(conn, "odds")
    return out


def setup_logging(log_file: Optional[Path]) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()] if log_file is None else \
        [RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8")]
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=handlers, force=True)


def main(argv: Optional[list[str]] = None, fetcher: Optional[StatsFetcher] = None) -> int:
    ap = argparse.ArgumentParser(prog="nbadash.ingest refresh", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="refresh regardless of what the scoreboard says")
    ap.add_argument("--watch", action="store_true", help="keep running and check repeatedly")
    ap.add_argument("--interval", type=float, default=20, help="minutes between checks with --watch (default 20)")
    ap.add_argument("--min-gap", type=float, default=30, help="never refresh twice within this many minutes (default 30)")
    ap.add_argument("--log-file", type=Path, help="append to this file (rotated at 1 MB) instead of printing")
    ap.add_argument("--db", help="SQLite path (default $NBA_DB or backend/data/nba.db)")
    args = ap.parse_args(argv)
    setup_logging(args.log_file)
    fetcher = fetcher or ingest.NbaApiFetcher()
    gap = timedelta(minutes=args.min_gap)
    while True:
        conn = db.connect(args.db)
        try:
            refresh_once(conn, fetcher, force=args.force, min_gap=gap)
            args.force = False  # --force applies to the first pass only
        except Exception:
            log.exception("refresh failed; the next pass will retry")
            if not args.watch:
                return 1
        finally:
            conn.close()
        if not args.watch:
            return 0
        time.sleep(args.interval * 60)


if __name__ == "__main__":
    raise SystemExit(main())
