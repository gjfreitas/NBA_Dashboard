import json
from datetime import date

import httpx
import pytest

from nbadash import db, ingest
from nbadash.app import create_app
from nbadash.sources import ReplaySource

LAL, HOU, SEASON = 1610612747, 1610612745, "2025-26"


class LeagueFetcher:
    """Serves saved league-wide responses; counts calls."""

    def __init__(self, tdir):
        self.tdir, self.calls = tdir, []

    def _load(self, name):
        return json.loads((self.tdir / name).read_text(encoding="utf-8"))

    def team_stats(self, season, measure):
        self.calls.append(f"teamstats:{measure}")
        return self._load(f"teamstats_{measure.lower()}_{season}.json")

    def team_games(self, season):
        self.calls.append("teamgames"); return self._load(f"leaguegamelog_{season}.json")

    def league_players(self, season):
        self.calls.append("players"); return self._load(f"playerleaders_{season}.json")

    def standings(self, season):
        self.calls.append("standings"); return self._load(f"standings_{season}.json")


@pytest.fixture
def conn(tmp_path):
    return db.connect(tmp_path / "p.db")


@pytest.fixture
def tdir(fixtures_dir):
    return fixtures_dir / "teams"


def test_sync_league_is_cached(conn, tdir):
    f = LeagueFetcher(tdir)
    first = ingest.sync_league(conn, f, [SEASON])
    assert first[SEASON] == {"teams": 30, "games": 2460, "players": 582, "standings": 30}
    n = len(f.calls)
    assert ingest.sync_league(conn, f, [SEASON])[SEASON] == {} and len(f.calls) == n  # fresh -> no calls
    # every game appears once per team; both sides of a game agree on who won
    assert conn.execute("SELECT COUNT(*) FROM team_games").fetchone()[0] == 2460
    bad = conn.execute("""SELECT COUNT(*) FROM team_games a JOIN team_games b ON a.game_id=b.game_id AND a.team_id<b.team_id
                          WHERE (a.pts > b.pts) != (a.wl = 'W')""").fetchone()[0]
    assert bad == 0


@pytest.fixture
async def client(conn, tmp_path, tdir, fixtures_dir):
    ingest.sync_league(conn, LeagueFetcher(tdir), [SEASON])
    app = create_app(ReplaySource(fixtures_dir), db_path=str(tmp_path / "p.db"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def test_preview(client):
    r = await client.get("/api/preview", params={"home": LAL, "away": HOU})
    assert r.status_code == 200
    p = r.json()
    assert p["season"] == SEASON and p["is_fallback"] is False
    assert p["home"]["abbr"] == "LAL" and p["away"]["abbr"] == "HOU"
    assert p["home"]["wins"] + p["home"]["losses"] == 82
    assert 1 <= p["home"]["ranks"]["pts"] <= 30 and p["home"]["stats"]["net_rtg"] is not None
    assert len(p["home"]["form"]) == 10 and p["home"]["form"][0]["date"] >= p["home"]["form"][-1]["date"]
    assert [l["pts"] for l in p["home"]["leaders"]] == sorted((l["pts"] for l in p["home"]["leaders"]), reverse=True)
    s = p["series"]
    assert s["games"] and s["home_wins"] + s["away_wins"] == len(s["games"])
    g = s["games"][0]
    assert {g["home_abbr"], g["away_abbr"]} == {"LAL", "HOU"} and g["winner_id"] in (LAL, HOU)
    assert (g["home_pts"] > g["away_pts"]) == (g["winner_id"] == (LAL if g["home_abbr"] == "LAL" else HOU))


async def test_preview_missing_data(client):
    assert (await client.get("/api/preview", params={"home": 1, "away": 2})).status_code == 404


# ---------------------------------------------------------------- rest, streak and splits

def games_before(conn, team, day):
    return conn.execute("SELECT game_date, home, wl, plus_minus FROM team_games WHERE team_id=? AND season=? AND game_date<? ORDER BY game_date DESC",
                        (team, SEASON, day)).fetchall()


async def test_context_matches_the_raw_games(client, conn, tmp_path):
    day = "2026-01-15"
    with conn:
        conn.execute("INSERT INTO schedule (game_id, season, game_date, status, home_id, away_id, home_abbr, away_abbr) VALUES ('GX', ?, ?, 1, ?, ?, 'LAL', 'HOU')",
                     (SEASON, day, LAL, HOU))
    p = (await client.get("/api/preview", params={"home": LAL, "away": HOU, "game_id": "GX"})).json()
    for side, tid in (("home", LAL), ("away", HOU)):
        ctx, rows = p[side]["context"], games_before(conn, tid, day)
        last = date.fromisoformat(rows[0]["game_date"])
        assert ctx["last_game_date"] == rows[0]["game_date"] and ctx["days_rest"] == (date.fromisoformat(day) - last).days - 1
        assert ctx["back_to_back"] == (ctx["days_rest"] == 0)
        assert ctx["games_last_7"] == sum(1 for g in rows if g["game_date"] >= "2026-01-08")
        assert (ctx["home"]["w"] + ctx["home"]["l"], ctx["away"]["w"] + ctx["away"]["l"]) == (sum(1 for g in rows if g["home"]), sum(1 for g in rows if not g["home"]))
        assert ctx["home"]["w"] + ctx["away"]["w"] == sum(1 for g in rows if g["wl"] == "W")
        run = next((i for i, g in enumerate(rows) if g["wl"] != rows[0]["wl"]), len(rows))
        assert ctx["streak"] == f"{rows[0]['wl']}{run}"
        assert ctx["last5"]["w"] + ctx["last5"]["l"] == 5
    assert p["home"]["context"]["home"]["margin"] == round(
        sum(g["plus_minus"] for g in games_before(conn, LAL, day) if g["home"]) / sum(1 for g in games_before(conn, LAL, day) if g["home"]), 1)


async def test_context_stops_at_the_game_date(client, conn):
    with conn:
        conn.execute("INSERT INTO schedule (game_id, season, game_date, status, home_id, away_id, home_abbr, away_abbr) VALUES ('GY', ?, '2025-10-30', 1, ?, ?, 'LAL', 'HOU')",
                     (SEASON, LAL, HOU))
    early = (await client.get("/api/preview", params={"home": LAL, "away": HOU, "game_id": "GY"})).json()["home"]["context"]
    total = early["home"]["w"] + early["home"]["l"] + early["away"]["w"] + early["away"]["l"]
    assert total == len(games_before(conn, LAL, "2025-10-30")) < 10  # only the games already played; nothing from the future
    with conn:
        conn.execute("INSERT INTO schedule (game_id, season, game_date, status, home_id, away_id, home_abbr, away_abbr) VALUES ('GZ', ?, '2025-10-01', 1, ?, ?, 'LAL', 'HOU')",
                     (SEASON, LAL, HOU))
    assert (await client.get("/api/preview", params={"home": LAL, "away": HOU, "game_id": "GZ"})).json()["home"]["context"] is None  # season hasn't started: no context, no crash
