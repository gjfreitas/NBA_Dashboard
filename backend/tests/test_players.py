import json
from datetime import timedelta

import httpx
import pytest

from nbadash import db, ingest
from nbadash.app import create_app
from nbadash.sources import ReplaySource

PID, SEASON = 2544, "2025-26"


@pytest.fixture
def pdir(fixtures_dir):
    return fixtures_dir / "players"


def load(pdir, name):
    return json.loads((pdir / name).read_text(encoding="utf-8"))


def emptied(d):
    for rs in d["resultSets"]:
        rs["rowSet"] = []
    return d


class FixtureFetcher:
    """Serves saved nba_api responses and counts calls."""

    def __init__(self, pdir):
        self.pdir, self.calls = pdir, []

    def info(self, pid):
        self.calls.append("info"); return load(self.pdir, f"commonplayerinfo_{pid}.json")

    def career(self, pid):
        self.calls.append("career"); return load(self.pdir, f"playercareerstats_{pid}.json")

    def gamelog(self, pid, season, st):
        self.calls.append(f"gamelog:{season}:{st}")
        d = load(self.pdir, f"playergamelog_{pid}_{season}.json")
        return d if st == "regular" else emptied(d)  # only regular-season fixtures were recorded

    def shots(self, pid, season, st):
        self.calls.append(f"shots:{season}:{st}")
        d = load(self.pdir, f"shotchartdetail_{pid}_{season}.json")
        return d if st == "regular" else emptied(d)


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    ingest.load_roster(c, [{"id": PID, "full_name": "LeBron James", "first_name": "LeBron", "last_name": "James", "is_active": True},
                           {"id": 1, "full_name": "Retired Guy", "first_name": "Retired", "last_name": "Guy", "is_active": False}])
    return c


def test_sync_stores_everything_and_is_resumable(conn, pdir):
    f = FixtureFetcher(pdir)
    first = ingest.sync_player(conn, f, PID, seasons=[SEASON])
    assert first["info"] and first["career"] and first["gamelogs"] == 60 and first["shots"] == 919
    assert "gamelog:2025-26:regular" in f.calls
    n = len(f.calls)
    second = ingest.sync_player(conn, f, PID, seasons=[SEASON])  # fresh -> no network
    assert len(f.calls) == n and second == {"info": False, "career": False, "gamelogs": 0, "shots": 0}
    stale = ingest.sync_player(conn, f, PID, seasons=[SEASON], max_age=timedelta(0))
    assert stale["info"] and len(f.calls) > n
    assert conn.execute("SELECT COUNT(*) FROM player_shots").fetchone()[0] == 919  # replaced, not duplicated


def test_career_totals_match_season_sum(conn, pdir):
    ingest.store_career(conn, PID, load(pdir, "playercareerstats_2544.json"))
    r = conn.execute("SELECT SUM(pts) s FROM player_seasons WHERE season!='Career' AND season_type='regular' AND team_abbr!='TOT'").fetchone()
    c = conn.execute("SELECT pts FROM player_seasons WHERE season='Career' AND season_type='regular'").fetchone()
    assert r["s"] == c["pts"]


@pytest.fixture
async def client(conn, tmp_path, fixtures_dir, pdir):
    ingest.sync_player(conn, FixtureFetcher(pdir), PID, seasons=[SEASON])
    app = create_app(ReplaySource(fixtures_dir), db_path=str(tmp_path / "t.db"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def test_search(client):
    r = (await client.get("/api/players", params={"q": "lebr"})).json()
    assert [p["name"] for p in r] == ["LeBron James"]
    assert (await client.get("/api/players", params={"q": "retired"})).json() == []  # active only by default
    assert len((await client.get("/api/players", params={"q": "retired", "active": False})).json()) == 1
    assert (await client.get("/api/players", params={"q": "%"})).json() == []  # wildcard is escaped


async def test_profile(client):
    p = (await client.get(f"/api/players/{PID}")).json()
    assert p["name"] == "LeBron James" and p["full_bio_loaded"] and p["height"] == "6-9"
    assert p["draft"] == "2003 · Round 1 · Pick 1" and p["team"] == "PHI"
    rookie = next(x for x in p["regular"] if x["season"] == "2003-04")
    assert rookie["gp"] == 79 and rookie["ppg"] == 20.9 and rookie["mpg"] == 39.5
    assert rookie["fg_pct"] == 0.417 and 0.45 < rookie["ts_pct"] < 0.55
    assert p["career_regular"]["pts"] == 43454 and p["career_playoffs"]["gp"] > 250
    assert p["available"][0] == {"season": SEASON, "season_type": "regular", "games": 60, "shots": 919}


async def test_gamelog_and_shots(client):
    log = (await client.get(f"/api/players/{PID}/gamelog", params={"season": SEASON})).json()
    assert len(log) == 60 and log[0]["date"] >= log[-1]["date"] and log[0]["matchup"] == "LAL vs. UTA"
    sc = (await client.get(f"/api/players/{PID}/shots", params={"season": SEASON})).json()
    assert sc["attempts"] == 919 and sum(z["attempts"] for z in sc["zones"]) == 919
    assert sc["made"] == sum(s["made"] for s in sc["shots"]) and 0.4 < sc["fg_pct"] < 0.6
    assert (await client.get("/api/players/99999999")).status_code == 404


async def test_unloaded_player_is_graceful(client):
    p = (await client.get("/api/players/1")).json()
    assert p["full_bio_loaded"] is False and p["regular"] == [] and p["available"] == []


async def test_many_concurrent_requests_do_not_hit_sqlite_thread_errors(client):
    """Regression: FastAPI may set up a sync dependency, run the endpoint and tear it down on different
    worker threads; a thread-bound sqlite connection then raised ProgrammingError -> intermittent 500s."""
    import asyncio
    rs = await asyncio.gather(*[client.get(f"/api/players/{PID}") for _ in range(80)],
                              *[client.get("/api/players", params={"q": "le"}) for _ in range(80)])
    assert {r.status_code for r in rs} == {200}


def test_throttle_pauses_after_consecutive_failures_and_eases_back():
    class F:
        delay = 0.8

    slept = []
    th = ingest.Throttle(F(), trip_after=2, cooldown=300, sleep=slept.append)
    assert th.failed() is False and slept == []        # one bad player is just bad luck
    th.ok()                                            # ...and a success resets the streak
    assert th.failed() is False
    assert th.failed() is True and slept == [300]      # two in a row: cool down
    assert th.fetcher.delay == pytest.approx(1.2)      # and slow the pacing
    assert th.failed() is False and th.failed() is True and th.fetcher.delay == pytest.approx(1.8)
    for _ in range(40):
        th.ok()
    assert th.fetcher.delay == pytest.approx(0.8)      # normal pace again once it recovers
    for _ in range(20):                                # pacing is capped
        th.failed()
    assert th.fetcher.delay <= 3.0


def test_fold_text_removes_accents():
    from nbadash.db import fold_text
    assert fold_text("Nikola Jokić") == "nikola jokic" and fold_text("Luka Dončić") == "luka doncic" and fold_text("Łukasz") == "lukasz" and fold_text(None) == ""


async def test_search_ignores_accents(tmp_path, fixtures_dir):
    c = db.connect(tmp_path / "s.db")
    with c:
        c.execute("INSERT INTO players (id, full_name, is_active) VALUES (1, 'Nikola Jokić', 1)")
    app = create_app(ReplaySource(fixtures_dir), db_path=str(tmp_path / "s.db"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        for q in ("jokic", "JOKIĆ", "kola jok"):
            assert [p["id"] for p in (await client.get("/api/players", params={"q": q})).json()] == [1]


@pytest.mark.asyncio
async def test_the_profile_catches_season_totals_up_with_the_game_logs(conn):
    """The season row is written when a player is loaded; the logs are refreshed after every game. The profile must not lag behind the logs."""
    with conn:
        conn.execute("INSERT INTO player_seasons (player_id, season, season_type, team_abbr, gp, gs, min, pts, reb, ast) VALUES (?, '2026-27', 'regular', 'LAL', 1, 1, 30, 20, 5, 5)", (PID,))
        conn.execute("INSERT INTO player_seasons (player_id, season, season_type, team_abbr, gp, gs, min, pts, reb, ast) VALUES (?, 'Career', 'regular', '', 100, 100, 3000, 2000, 500, 500)", (PID,))
        for i, (pts, reb, ast) in enumerate([(20, 5, 5), (30, 7, 9), (25, 6, 4)]):
            conn.execute("INSERT INTO player_game_logs (player_id, game_id, season, season_type, game_date, min, pts, reb, ast, fgm, fga, fg3m, fg3a, ftm, fta, oreb, dreb, stl, blk, tov, pf) "
                         "VALUES (?, ?, '2026-27', 'regular', ?, 30, ?, ?, ?, 0,0,0,0,0,0,0,0,0,0,0,0)", (PID, f"G{i}", f"2026-10-2{i}", pts, reb, ast))
    app = create_app(ReplaySource(__import__("pathlib").Path(".")), db_path=conn.execute("PRAGMA database_list").fetchone()[2])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        prof = (await client.get(f"/api/players/{PID}")).json()
    cur = next(x for x in prof["regular"] if x["season"] == "2026-27")
    assert cur["gp"] == 3 and cur["ppg"] == 25.0 and cur["pts"] == 75  # three games, not the one the row was loaded with
    assert prof["career_regular"]["gp"] == 102 and prof["career_regular"]["pts"] == 2055  # the career row moves by the same two games
