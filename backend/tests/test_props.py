import json

import httpx
import pytest

from nbadash import db, ingest, props_ingest
from nbadash.app import create_app
from nbadash.sources import ReplaySource

PID, SEASON = 2544, "2025-26"
LAL, OKC = 1610612747, 1610612760


def load(fixtures_dir, name):
    return json.loads((fixtures_dir / "stats" / name).read_text(encoding="utf-8"))


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "p.db")
    ingest.load_roster(c, [{"id": PID, "full_name": "LeBron James", "first_name": "LeBron", "last_name": "James", "is_active": True},
                           {"id": 7, "full_name": "Sidekick One", "first_name": "Sidekick", "last_name": "One", "is_active": True}])
    return c


@pytest.fixture
def loaded(conn, fixtures_dir):
    """A player's games (period-1 fixture doubles as a base league log: same shape) plus extras and matchup data."""
    q1 = load(fixtures_dir, "pgl_q1.json")
    props_ingest.store_league_logs(conn, SEASON, q1)
    props_ingest.store_log_extras(conn, SEASON, "usage", load(fixtures_dir, "pgl_usage.json"))
    props_ingest.store_log_extras(conn, SEASON, "q1", q1)
    props_ingest.store_log_extras(conn, SEASON, "q2", load(fixtures_dir, "pgl_q2.json"))
    props_ingest.store_player_zones(conn, SEASON, load(fixtures_dir, "player_shotloc.json"))
    props_ingest.store_team_zones(conn, SEASON, load(fixtures_dir, "team_shotloc_opp.json"))
    props_ingest.store_shot_types(conn, SEASON, "catch_shoot", load(fixtures_dir, "player_ptshot_Catch_and_Shoot.json"),
                                  load(fixtures_dir, "opp_pt_shot_cs.json"))
    props_ingest.store_play_type(conn, SEASON, "Isolation", load(fixtures_dir, "synergy_iso_player.json"),
                                 load(fixtures_dir, "synergy_iso_team_def.json"))
    return conn


def test_league_logs_classify_game_types_and_keep_extras(loaded):
    types = dict(loaded.execute("SELECT season_type, COUNT(*) FROM player_game_logs GROUP BY season_type").fetchall())
    # fixture: 60 regular + 10 playoff games + 3 All-Star rows (003), which are not stored
    assert types == {"regular": 60, "playoffs": 10}
    assert loaded.execute("SELECT COUNT(*) FROM player_game_logs WHERE usg_pct IS NULL OR q1_pts IS NULL OR q2_pts IS NULL").fetchone()[0] == 0
    assert 0 < loaded.execute("SELECT MAX(usg_pct) FROM player_game_logs").fetchone()[0] < 1  # stored as a fraction
    assert loaded.execute("SELECT COUNT(*) FROM player_game_logs WHERE team_id=?", (LAL,)).fetchone()[0] > 60
    # re-running the base refresh must not wipe usage/quarter extras
    props_ingest.store_league_logs(loaded, SEASON, load_q1(loaded))
    assert loaded.execute("SELECT COUNT(*) FROM player_game_logs WHERE usg_pct IS NOT NULL").fetchone()[0] == 70


def load_q1(conn):  # the same fixture again
    from pathlib import Path
    return json.loads((Path(__file__).resolve().parents[2] / "fixtures" / "stats" / "pgl_q1.json").read_text(encoding="utf-8"))


def test_non_counted_game_types_are_skipped(conn, fixtures_dir):
    d = load(fixtures_dir, "pgl_q1.json")
    for r in d["resultSets"][0]["rowSet"][:5]:
        r[7] = "0012500001"  # preseason id
    assert props_ingest.store_league_logs(conn, SEASON, d) == 65  # 70 countable - 5 turned into preseason


def test_zone_and_matchup_tables(loaded):
    assert loaded.execute("SELECT COUNT(*) FROM player_zones WHERE season=?", (SEASON,)).fetchone()[0] == 582 * 6
    assert loaded.execute("SELECT COUNT(*) FROM team_zones_def WHERE season=?", (SEASON,)).fetchone()[0] == 30 * 6
    assert loaded.execute("SELECT COUNT(DISTINCT zone) FROM player_zones").fetchone()[0] == 6  # backcourt/aggregate corner dropped
    assert loaded.execute("SELECT COUNT(*) FROM team_play_types_def").fetchone()[0] == 30
    assert loaded.execute("SELECT COUNT(*) FROM player_shot_types WHERE shot_type='catch_shoot'").fetchone()[0] > 400


@pytest.fixture
async def client(loaded, tmp_path, fixtures_dir):
    # teammate "7" played alongside the player in his first 30 games; the team's schedule has one future game
    games = loaded.execute("SELECT game_id FROM player_game_logs WHERE player_id=? ORDER BY game_date", (PID,)).fetchall()
    with loaded:
        for g in games[:30]:
            loaded.execute("INSERT INTO player_game_logs (player_id, game_id, season, season_type, game_date, matchup, wl, min, "
                           "fgm, fga, fg3m, fg3a, ftm, fta, oreb, dreb, reb, ast, stl, blk, tov, pf, pts, plus_minus, team_id) "
                           "SELECT 7, game_id, season, season_type, game_date, matchup, wl, 20, 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0, team_id "
                           "FROM player_game_logs WHERE player_id=? AND game_id=?", (PID, g["game_id"]))
        loaded.execute("INSERT INTO teams (id, abbr, city, name, conference, division) VALUES (?,?,?,?,?,?)", (OKC, "OKC", "Oklahoma City", "Thunder", "West", "Northwest"))
        loaded.execute("INSERT INTO teams (id, abbr, city, name, conference, division) VALUES (?,?,?,?,?,?)", (LAL, "LAL", "Los Angeles", "Lakers", "West", "Pacific"))
        loaded.execute("INSERT INTO schedule VALUES ('0029900001', ?, '2099-01-01', '2099-01-02T00:00:00Z', 1, '7:00 pm ET', ?, ?, 'LAL', 'OKC', NULL, NULL, NULL, NULL, NULL)",
                       (SEASON, LAL, OKC))
    app = create_app(ReplaySource(fixtures_dir), db_path=str(tmp_path / "p.db"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def test_games_payload(client):
    r = await client.get(f"/api/players/{PID}/games")
    assert r.status_code == 200
    d = r.json()
    g = d["games"]
    assert d["seasons"] == [SEASON] and len(g) == 70 and [x["date"] for x in g] == sorted(x["date"] for x in g)
    assert all(x["opp_abbr"] and x["season_type"] in ("regular", "playoffs") for x in g)
    assert all(x["h1_pts"] >= x["q1_pts"] >= 0 for x in g)  # first half = Q1 + Q2; a missing period row counts as 0
    assert {x["home"] for x in g} == {True, False}
    assert all(0 < x["usg"] <= 100 for x in g if x["usg"] is not None)
    # back-to-backs: rest_days 0 only when the previous team game was the day before
    from datetime import date
    for prev, cur in zip(g, g[1:]):
        if cur["season"] == prev["season"] and cur["rest_days"] is not None:
            assert cur["rest_days"] == (date.fromisoformat(cur["date"]) - date.fromisoformat(prev["date"])).days - 1
    assert g[0]["rest_days"] is None
    # teammate 7 appears in the first 30 games only, and is listed with a window
    assert all(7 in x["mates"] for x in g[:30]) and all(7 not in x["mates"] for x in g[30:])
    assert [t["player_id"] for t in d["teammates"]] == [7] and d["teammates"][0]["name"] == "Sidekick One"
    w = d["teammates"][0]["windows"][0]
    assert w["first"] == g[0]["date"] and w["last"] == g[29]["date"]
    assert d["next_game"]["opp_abbr"] == "OKC" and d["next_game"]["home"] is True


async def test_games_404(client):
    assert (await client.get("/api/players/7/games")).status_code == 200  # the teammate has logs too
    assert (await client.get("/api/players/99999/games")).status_code == 404


async def test_matchup_payload(client):
    d = (await client.get(f"/api/players/{PID}/matchup")).json()  # opponent defaults to the next game's
    assert d["season"] == SEASON and d["opponent"]["abbr"] == "OKC"
    assert [z["zone"] for z in d["zones"]] == props_ingest.ZONES
    assert abs(sum(z["share"] for z in d["zones"]) - 1) < 0.01
    assert all(1 <= z["opp_rank"] <= 30 for z in d["zones"] if z["opp_rank"])
    assert all(0.2 < z["league_fg_pct"] < 0.8 for z in d["zones"])  # league average per zone
    cs = next(s for s in d["shot_types"] if s["key"] == "catch_shoot")
    assert cs["fga"] > 0 and 1 <= cs["opp_rank"] <= 30 and 0 < cs["opp_efg_pct"] < 1
    iso = next(p for p in d["play_types"] if p["key"] == "Isolation")
    assert iso["label"] == "Isolation" and 1 <= iso["opp_rank"] <= 30 and iso["opp_ppp"] > 0 and iso["ppp"] > 0
    # explicit opponent without a next game still ranks; unknown opponent 404s
    assert (await client.get(f"/api/players/{PID}/matchup", params={"opp": LAL})).json()["opponent"]["abbr"] == "LAL"
    assert (await client.get(f"/api/players/{PID}/matchup", params={"opp": 5})).status_code == 404
    assert (await client.get("/api/players/7/matchup")).status_code == 404  # no zone data for this player


# ------------------------------------------------------------- similar players ----

@pytest.fixture
async def similar_client(loaded, tmp_path, fixtures_dir):
    """LeBron (the target) + a clone with an identical shot profile + other real zone-fixture players, all with rotation logs."""
    others = [r[0] for r in loaded.execute("SELECT DISTINCT player_id FROM player_zones WHERE player_id NOT IN (?, 7) LIMIT 4", (PID,))]
    ids = [9001, *others]
    with loaded:
        loaded.execute("INSERT INTO player_zones SELECT 9001, season, zone, fgm, fga FROM player_zones WHERE player_id=?", (PID,))
        loaded.execute("INSERT INTO player_shot_types SELECT 9001, season, shot_type, fgm, fga, fg3m, fg3a, gp FROM player_shot_types WHERE player_id=?", (PID,))
        loaded.execute("INSERT INTO teams (id, abbr, city, name) VALUES (?, 'OKC', 'Oklahoma City', 'Thunder')", (OKC,))
        loaded.execute("INSERT INTO teams (id, abbr, city, name) VALUES (?, 'LAL', 'Los Angeles', 'Lakers')", (LAL,))
        loaded.execute("UPDATE players SET position='Forward' WHERE id=?", (PID,))
        for n, q in enumerate(ids):
            loaded.execute("INSERT OR IGNORE INTO players (id, full_name, position, team_abbr) VALUES (?,?,?,?)",
                           (q, f"Candidate {q}", "Forward" if q == 9001 else "Guard", "LAL"))
            if q == 9001:
                loaded.execute("UPDATE players SET position='Forward' WHERE id=9001")
            for i in range(20):  # 20 games, 30 min, 15 FGA, 10 + i points; every 4th game is against OKC
                vs = "LAL vs. OKC" if i % 4 == 0 else "LAL @ BOS"
                ingest.upsert_log(loaded, dict(
                    player_id=q, game_id=f"0029{q}{i:02d}", season=SEASON, season_type="regular", game_date=f"2026-01-{i + 1:02d}", matchup=vs,
                    wl="W", min=30, fgm=6, fga=15, fg3m=1, fg3a=4, ftm=2, fta=3, oreb=1, dreb=3, reb=4, ast=3, stl=1, blk=0, tov=2,
                    pf=2, pts=10 + i, plus_minus=0, team_id=LAL))
        # a bench player with a perfect shot-profile clone must still be excluded by the role gate
        loaded.execute("INSERT INTO player_zones SELECT 9002, season, zone, fgm, fga FROM player_zones WHERE player_id=?", (PID,))
        for i in range(20):
            ingest.upsert_log(loaded, dict(player_id=9002, game_id=f"00299002{i:02d}", season=SEASON, season_type="regular", game_date=f"2026-02-{i + 1:02d}",
                                           matchup="LAL vs. OKC", wl="W", min=8, fgm=1, fga=2, fg3m=0, fg3a=0, ftm=0, fta=0, oreb=0, dreb=1, reb=1,
                                           ast=0, stl=0, blk=0, tov=0, pf=1, pts=2, plus_minus=0, team_id=LAL))
    # the target's own logs: starter-level volume so the gate (>= half his FGA) is meaningful
    with loaded:
        loaded.execute("UPDATE player_game_logs SET fga=14, min=34 WHERE player_id=?", (PID,))
    app = create_app(ReplaySource(fixtures_dir), db_path=str(tmp_path / "p.db"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c, ids


async def test_similar_players_rank_by_shot_profile(similar_client):
    c, ids = similar_client
    d = (await c.get(f"/api/players/{PID}/similar", params={"opp": OKC})).json()
    assert d["season"] == SEASON and d["opponent"]["abbr"] == "OKC" and d["mode"] == "shots"
    matches = [p["match"] for p in d["players"]]
    assert matches == sorted(matches, reverse=True) and all(0 <= m <= 100 for m in matches)
    assert d["players"][0]["player_id"] == 9001 and d["players"][0]["match"] == 100.0  # identical zones + shot types
    got = {p["player_id"] for p in d["players"]}
    assert PID not in got and 9002 not in got  # not himself; the bench clone fails the role gate
    assert got <= set(ids)


async def test_similar_players_games_and_averages(similar_client):
    c, _ = similar_client
    d = (await c.get(f"/api/players/{PID}/similar", params={"opp": OKC})).json()
    top = d["players"][0]
    assert top["games_vs_opp"] == 5 and top["averages"]["pts"] == pytest.approx(sum(10 + i for i in range(20)) / 20)
    mine = [g for g in d["games"] if g["player_id"] == top["player_id"]]
    assert [g["pts"] for g in mine] == [10 + i for i in (16, 12, 8, 4, 0)]  # games vs OKC only, newest first
    assert all(g["opp_abbr"] == "OKC" and g["season"] == SEASON for g in d["games"])
    assert [g["date"] for g in d["games"]] == sorted((g["date"] for g in d["games"]), reverse=True)
    assert all(g["player_name"] and "mates" in g for g in d["games"])
    assert {g["team_abbr"] for g in d["games"]} == {"LAL"}  # the team he was with in that game


async def test_similar_players_by_position(similar_client):
    c, _ = similar_client
    d = (await c.get(f"/api/players/{PID}/similar", params={"opp": OKC, "mode": "position"})).json()
    assert [p["player_id"] for p in d["players"]] == [9001]  # the only other Forward in the pool
    assert (await c.get(f"/api/players/{PID}/similar", params={"mode": "bogus"})).status_code == 422


async def test_similar_players_without_opponent_or_profile(similar_client):
    c, _ = similar_client
    d = (await c.get(f"/api/players/{PID}/similar", params={"opp": OKC})).json()
    assert d["opponent"]["abbr"] == "OKC"
    none = (await c.get(f"/api/players/{PID}/similar")).json()  # no schedule in this fixture -> no opponent, no games
    assert none["opponent"] is None and none["games"] == [] and none["players"]
    assert (await c.get("/api/players/7/similar")).status_code == 404
    assert (await c.get(f"/api/players/{PID}/similar", params={"opp": 5})).status_code == 404
