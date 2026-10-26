"""Is the data current? Each scheduled pass records which sources it reached; `GET /api/health` turns that into a status page.

A silent failure (the NBA changed a file, the machine slept, a network block) otherwise just shows up as old data.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from . import db

LAST_REFRESH = "refresh:last"  # written by refresh.run_refresh (the heavy, game-driven update)


def record(conn: sqlite3.Connection, source: str, error: Optional[str] = None, now: Optional[datetime] = None) -> None:
    """Note that `source` was just reached (error=None) or just failed. The last success survives later failures."""
    stamp = (now or datetime.now(timezone.utc)).isoformat()  # full precision: a success right after a failure must sort after it
    with conn:
        conn.execute("INSERT OR IGNORE INTO source_checks (source) VALUES (?)", (source,))
        if error is None:
            conn.execute("UPDATE source_checks SET last_ok=? WHERE source=?", (stamp, source))
        else:
            conn.execute("UPDATE source_checks SET last_error=?, last_error_at=? WHERE source=?", (error[:300], stamp, source))


class HealthItem(BaseModel):
    key: str
    label: str
    status: str  # ok | stale | error | never
    last_ok: Optional[str]
    age_minutes: Optional[int]
    max_age_minutes: int
    detail: str
    last_error: Optional[str]
    last_error_at: Optional[str]


class Coverage(BaseModel):
    players_loaded: int
    players_active: int
    latest_game_date: Optional[str]
    newest_injury_report: Optional[str]
    injury_reports_stored: int


class Health(BaseModel):
    status: str  # ok | degraded | down
    generated_at: str
    items: list[HealthItem]
    coverage: Coverage


def _age(stamp: Optional[str], now: datetime) -> Optional[int]:
    return None if not stamp else max(0, int((now - datetime.fromisoformat(stamp)).total_seconds() // 60))


def _item(key: str, label: str, last_ok: Optional[str], max_age: int, now: datetime, detail: str = "", err: Optional[tuple] = None) -> HealthItem:
    age = _age(last_ok, now)
    err_msg, err_at = err or (None, None)
    failing = bool(err_at) and (last_ok is None or err_at >= last_ok)  # the most recent attempt failed
    status = "error" if failing else "never" if age is None else "ok" if age <= max_age else "stale"
    return HealthItem(key=key, label=label, status=status, last_ok=last_ok, age_minutes=age, max_age_minutes=max_age, detail=detail,
                      last_error=err_msg, last_error_at=err_at)


def build(conn: sqlite3.Connection, now: Optional[datetime] = None) -> Health:
    now = now or datetime.now(timezone.utc)
    checks = {r["source"]: r for r in conn.execute("SELECT * FROM source_checks")}

    def chk(source: str) -> tuple[Optional[str], Optional[tuple]]:
        r = checks.get(source)
        return (r["last_ok"], (r["last_error"], r["last_error_at"]) if r["last_error_at"] else None) if r else (None, None)

    def synced(kind: str) -> Optional[str]:
        r = conn.execute("SELECT synced_at FROM sync WHERE player_id=0 AND kind=?", (kind,)).fetchone()
        return r["synced_at"] if r else None

    rep = conn.execute("SELECT report_id, published_at, entries FROM injury_reports ORDER BY published_utc DESC LIMIT 1").fetchone()
    n_reports = conn.execute("SELECT COUNT(*) FROM injury_reports").fetchone()[0]
    latest_game = conn.execute("SELECT MAX(game_date) FROM team_games").fetchone()[0]
    items = []
    ok, err = chk("pass")
    items.append(_item("scheduler", "Scheduled refresh", ok, 45, now,
                       "The scheduled task runs every 15 minutes. If this is stale, the computer was asleep or the task is not installed.", err))
    ok, err = chk("injuries")
    items.append(_item("injuries", "NBA injury report", ok, 45, now,
                       f"Newest report: {rep['published_at'].replace('T', ' ')} ET, {rep['entries']} players. {n_reports} reports stored." if rep else "No report stored yet.", err))
    ok, err = chk("lineups")
    items.append(_item("lineups", "Starting lineups", ok, 45, now, "Today's and tomorrow's NBA lineups file.", err))
    ok, err = chk("espn")
    items.append(_item("espn", "ESPN injuries (secondary)", synced("espn_injuries") or ok, 120, now, "Fetched at most once an hour; unofficial.", err))
    ok, err = chk("refresh")
    items.append(_item("games", "Game data (stats, standings, logs)", synced(LAST_REFRESH) or ok, 26 * 60, now,
                       f"Updated after finished games, and at least daily. Latest game in the database: {latest_game}." if latest_game else "No games stored yet.", err))
    if "odds" in checks:  # only shown once an odds API key has been used
        ok, err = chk("odds")
        spent = conn.execute("SELECT COALESCE(SUM(spent), 0) FROM odds_usage WHERE period=?", (now.strftime("%Y-%m"),)).fetchone()[0]
        lines = conn.execute("SELECT COUNT(*) FROM prop_lines").fetchone()[0]
        items.append(_item("odds", "Prop lines (odds API)", ok, 30 * 60, now, f"Fetched about twice a day within a monthly budget. {spent} credits or objects used this month, {lines} line changes stored.", err))
    loaded = conn.execute("SELECT COUNT(*) FROM players p WHERE p.is_active=1 AND EXISTS(SELECT 1 FROM sync s WHERE s.player_id=p.id AND s.kind='info')").fetchone()[0]
    active = conn.execute("SELECT COUNT(*) FROM players WHERE is_active=1").fetchone()[0]
    problems = sum(i.status != "ok" for i in items)
    status = "ok" if problems == 0 else "down" if problems >= 3 else "degraded"
    return Health(status=status, generated_at=now.isoformat(timespec="seconds"), items=items,
                  coverage=Coverage(players_loaded=loaded, players_active=active, latest_game_date=latest_game,
                                    newest_injury_report=rep["report_id"] if rep else None, injury_reports_stored=n_reports))


def make_router(db_path: Optional[str | Path] = None) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["health"])

    def conn() -> Iterator[sqlite3.Connection]:
        c = db.connect(db_path)
        try:
            yield c
        finally:
            c.close()

    @router.get("/health", response_model=Health)
    def health(c: sqlite3.Connection = Depends(conn)):
        """How fresh each data source is, and what the last failure was."""
        return build(c)

    return router
