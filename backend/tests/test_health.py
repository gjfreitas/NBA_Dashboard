from datetime import datetime, timedelta, timezone

import httpx
import pytest

from nbadash import db, health, refresh
from nbadash.app import create_app
from nbadash.sources import ReplaySource

NOW = datetime(2026, 10, 23, 18, 0, tzinfo=timezone.utc)


@pytest.fixture
def conn(tmp_path):
    return db.connect(tmp_path / "h.db")


def item(report, key):
    return next(i for i in report.items if i.key == key)


def test_nothing_recorded_is_never_not_ok(conn):
    r = health.build(conn, NOW)
    assert {i.status for i in r.items} == {"never"} and r.status == "down"


def test_fresh_stale_and_error_states(conn):
    health.record(conn, "pass", now=NOW - timedelta(minutes=10))
    health.record(conn, "lineups", now=NOW - timedelta(minutes=10))
    health.record(conn, "injuries", now=NOW - timedelta(minutes=50))
    r = health.build(conn, NOW)
    assert item(r, "lineups").status == "ok" and item(r, "lineups").age_minutes == 10
    assert item(r, "injuries").status == "stale" and item(r, "injuries").age_minutes == 50  # 50 > 45 minutes allowed
    health.record(conn, "lineups", "FetchError: 500", now=NOW - timedelta(minutes=2))
    lu = item(health.build(conn, NOW), "lineups")
    assert lu.status == "error" and lu.last_error == "FetchError: 500" and lu.age_minutes == 10  # the last success is still known
    health.record(conn, "lineups", now=NOW - timedelta(minutes=1))  # recovered
    lu = item(health.build(conn, NOW), "lineups")
    assert lu.status == "ok" and lu.last_error == "FetchError: 500"  # history kept, but not the current state


def test_overall_status(conn):
    for src in ("pass", "injuries", "lineups"):
        health.record(conn, src, now=NOW)
    with conn:
        conn.execute("INSERT INTO sync VALUES (0, 'espn_injuries', ?)", (NOW.isoformat(),))
        conn.execute("INSERT INTO sync VALUES (0, 'refresh:last', ?)", (NOW.isoformat(),))
    assert health.build(conn, NOW).status == "ok"
    health.record(conn, "injuries", "boom", now=NOW)
    assert health.build(conn, NOW).status == "degraded"


@pytest.mark.real_availability
def test_refresh_pass_records_failures_per_source(conn, monkeypatch):
    monkeypatch.setattr(refresh.injuries, "sync_injuries", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("nba is down")))
    monkeypatch.setattr(refresh.espn_injuries, "sync_espn", lambda c: {"skipped": "fresh"})
    monkeypatch.setattr(refresh.lineups, "poll", lambda c: [])
    out = refresh.refresh_availability(conn)
    assert "injuries_error" in out
    r = health.build(conn)
    assert item(r, "injuries").status == "error" and "nba is down" in item(r, "injuries").last_error
    assert item(r, "lineups").status == "ok" and item(r, "espn").status == "ok"


async def test_health_endpoint(tmp_path, fixtures_dir):
    c = db.connect(tmp_path / "e.db")
    health.record(c, "pass")
    app = create_app(ReplaySource(fixtures_dir), db_path=str(tmp_path / "e.db"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        d = (await client.get("/api/health")).json()
    assert d["status"] in ("degraded", "down") and [i["key"] for i in d["items"]] == ["scheduler", "injuries", "lineups", "espn", "games"]
    assert next(i for i in d["items"] if i["key"] == "scheduler")["status"] == "ok"
    assert set(d["coverage"]) == {"players_loaded", "players_active", "latest_game_date", "newest_injury_report", "injury_reports_stored"}
