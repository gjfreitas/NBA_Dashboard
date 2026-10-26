import json

import httpx
import pytest

from nbadash import db, ingest
from nbadash.app import create_app
from nbadash.sources import ReplaySource
from test_preview import LeagueFetcher

SEASON, NEXT = "2025-26", "2026-27"
OKC, LAL = 1610612760, 1610612747


@pytest.fixture
def conn(tmp_path, fixtures_dir):
    c = db.connect(tmp_path / "t.db")
    ingest.sync_league(c, LeagueFetcher(fixtures_dir / "teams"), [SEASON])
    fx = json.loads((fixtures_dir / "scheduleLeagueV2_1.json").read_text(encoding="utf-8"))
    assert ingest.sync_schedule(c, lambda: fx) > 1200
    return c


@pytest.fixture
async def client(conn, tmp_path, fixtures_dir):
    app = create_app(ReplaySource(fixtures_dir), db_path=str(tmp_path / "t.db"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


def test_ingest_teams_and_schedule(conn, fixtures_dir):
    assert conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0] == 30
    assert conn.execute("SELECT COUNT(*) FROM teams WHERE abbr IS NULL").fetchone()[0] == 0  # filled from the schedule
    assert conn.execute("SELECT COUNT(*) FROM schedule WHERE game_id LIKE '001%'").fetchone()[0] == 0  # no preseason
    fx = json.loads((fixtures_dir / "scheduleLeagueV2_1.json").read_text(encoding="utf-8"))
    assert ingest.sync_schedule(conn, lambda: fx) == 0  # fresh -> no refetch


async def test_standings(client):
    s = (await client.get("/api/standings")).json()
    assert s["season"] == SEASON and s["seasons"] == [SEASON] and len(s["teams"]) == 30 and s["min_games"] == 82
    for conf in ("East", "West"):
        ranks = [t["conf_rank"] for t in s["teams"] if t["team"]["conference"] == conf]
        assert sorted(ranks) == list(range(1, 16))
    top = next(t for t in s["teams"] if t["team"]["conference"] == "West" and t["conf_rank"] == 1)
    assert top["team"]["id"] == OKC and (top["w"], top["l"]) == (64, 18) and top["streak"].startswith(("W", "L"))
    assert abs(top["pct"] - 64 / 82) < 0.01 and top["diff"] > 5
    codes = [t["clinch"] for t in s["teams"]]
    assert set(codes) <= {"", "z", "y", "x", "pi", "e"} and codes.count("z") == 2  # one top seed per conference
    assert next(t for t in s["teams"] if t["team"]["id"] == OKC)["clinch"] == "z"
    assert (await client.get("/api/standings", params={"season": "1999-00"})).status_code == 404


async def test_team_profile(client):
    t = (await client.get(f"/api/teams/{OKC}")).json()
    assert t["team"]["abbr"] == "OKC" and t["team"]["division"] == "Northwest"
    assert t["standing"]["conf_rank"] == 1 and t["stats_season"] == SEASON and t["is_fallback"] is False
    assert t["detail"]["abbr"] == "OKC" and len(t["detail"]["form"]) == 10 and 1 <= t["detail"]["ranks"]["net_rtg"] <= 30
    assert (await client.get("/api/teams/1")).status_code == 404


async def test_roster(client):
    r = (await client.get(f"/api/teams/{LAL}/roster")).json()
    assert r["season"] == SEASON and len(r["players"]) >= 8
    assert all(p["gp"] > 0 for p in r["players"])
    minutes = [p["min"] * p["gp"] for p in r["players"]]
    assert minutes == sorted(minutes, reverse=True)  # rotation order: most minutes played first


async def test_schedule(client):
    s = (await client.get(f"/api/teams/{OKC}/schedule")).json()
    assert s["season"] == NEXT and 80 <= len(s["games"]) <= 90
    dates = [g["start_utc"] for g in s["games"]]
    assert dates == sorted(dates)
    assert all(g["opp_id"] != OKC and g["opp_abbr"] and g["opp_name"] for g in s["games"])
    assert {g["status"] for g in s["games"]} <= {"pre", "live", "final"}
    pre = next(g for g in s["games"] if g["status"] == "pre")
    assert pre["team_score"] is None and pre["result"] is None
    final = [g for g in s["games"] if g["status"] == "final"]
    assert final and all(g["result"] in ("W", "L") for g in final)
    assert sum(g["home"] for g in s["games"]) in range(38, 46)  # ~41 home games


async def test_game_info_comes_from_the_schedule(client, conn):
    row = conn.execute("SELECT * FROM schedule WHERE status=1 ORDER BY start_utc LIMIT 1").fetchone()
    d = (await client.get(f"/api/games/{row['game_id']}/info")).json()
    assert d["id"] == row["game_id"] and d["state"] == "pre" and d["start_utc"] == row["start_utc"]
    assert d["home"]["id"] == row["home_id"] and d["home"]["tricode"] == row["home_abbr"] and d["away"]["tricode"] == row["away_abbr"]
    assert d["home"]["city"] and d["home"]["name"]  # names come from the team directory
    assert d["home"]["score"] == 0 and d["home"]["wins"] is not None  # record from the standings
    assert (await client.get("/api/games/0029999999/info")).status_code == 404


async def test_game_info_prefers_the_game_log_over_a_stale_schedule(client, conn):
    row = conn.execute("SELECT * FROM schedule WHERE status=1 ORDER BY start_utc LIMIT 1").fetchone()
    with conn:  # the schedule file still says "not started", but both teams' game logs have the result
        conn.execute("INSERT INTO team_games VALUES (?, ?, '2026-27', 'H', 'A', ?, 1, 'W', 110, 5)", (row["home_id"], row["game_id"], row["game_date"]))
        conn.execute("INSERT INTO team_games VALUES (?, ?, '2026-27', 'A', 'H', ?, 0, 'L', 100, -5)", (row["away_id"], row["game_id"], row["game_date"]))
    d = (await client.get(f"/api/games/{row['game_id']}/info")).json()
    assert d["state"] == "final" and d["status_text"] == "Final" and (d["home"]["score"], d["away"]["score"]) == (110, 100)
