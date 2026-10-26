import httpx
import pytest

from nbadash import db, ingest
from nbadash.app import create_app
from nbadash.sources import ReplaySource
from test_preview import LeagueFetcher

SEASON = "2025-26"
T1, T2 = 1610612747, 1610612760  # LAL, OKC


def log(conn, pid, i, team, *, season=SEASON, stype="regular", **o):
    base = dict(min=30, fgm=5, fga=10, fg3m=1, fg3a=3, ftm=2, fta=2, oreb=1, dreb=3, reb=4, ast=3, stl=1, blk=0, tov=2, pf=2, pts=14, plus_minus=0)
    base.update(o)
    ingest.upsert_log(conn, dict(player_id=pid, game_id=f"{'004' if stype == 'playoffs' else '002'}{team % 1000:03d}{i:04d}", season=season,
                                 season_type=stype, game_date=f"2026-01-{i + 1:02d}", matchup="X vs. Y", wl="W", team_id=team, **base))


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "l.db")
    ingest.load_roster(c, [{"id": i, "full_name": n, "first_name": n, "last_name": "X", "is_active": True}
                           for i, n in ((1, "Star"), (2, "Part Timer"), (3, "Just Enough"), (4, "Big Man"), (5, "Other Team"), (6, "Zero"))])
    c.execute("INSERT INTO teams (id, abbr, city, name) VALUES (?, 'LAL', 'Los Angeles', 'Lakers')", (T1,))
    c.execute("INSERT INTO teams (id, abbr, city, name) VALUES (?, 'OKC', 'Oklahoma City', 'Thunder')", (T2,))
    with c:
        # Team 1 plays 10 games. Star: all 10, 30 pts / 10 reb / 5 ast on 40% shooting (10-25).
        for i in range(10):
            log(c, 1, i, T1, pts=30, reb=10, ast=5, fgm=10, fga=25, fg3m=3, fg3a=8, ftm=7, fta=8, min=36, stl=2, blk=1, usg_pct=0.30)
        # Part Timer: 6 of 10 games, but huge numbers (40 ppg) -> below the 70% games rule (needs 7)
        for i in range(6):
            log(c, 2, i, T1, pts=40, reb=2, ast=2, fgm=15, fga=20, min=34)
        # Just Enough: exactly 7 of 10 games -> qualifies; 20 pts, a triple-double in 2 of them
        for i in range(7):
            log(c, 3, i, T1, pts=20, reb=10 if i < 2 else 4, ast=10 if i < 2 else 3, fgm=2, fga=4, min=25)
        # Big Man: 10 games, rebounds only
        for i in range(10):
            log(c, 4, i, T1, pts=8, reb=14, ast=1, fgm=3, fga=5, fg3m=0, fg3a=0, ftm=2, fta=2, min=28, blk=3)
        # the other team plays only 8 games: its player must be judged against 8 (needs ceil(5.6) = 6), not 10
        for i in range(6):
            log(c, 5, i, T2, pts=25, reb=5, ast=5, fgm=9, fga=18, min=33)
        for i in range(8):
            log(c, 6, i, T2, pts=0, reb=0, ast=0, fgm=0, fga=0, fg3m=0, fg3a=0, ftm=0, fta=0, min=5, stl=0, blk=0, tov=0)  # a player who never records anything
        # playoffs are a separate board
        for i in range(4):
            log(c, 1, i, T1, stype="playoffs", pts=10, reb=1, ast=1)
        # Star's usage: 5 games at 36 min / 20%, then 5 games at 12 min / 40% (usage is stored separately from the box score)
        c.execute("UPDATE player_game_logs SET usg_pct=0.20 WHERE player_id=1 AND season_type='regular' AND game_date < '2026-01-06'")
        c.execute("UPDATE player_game_logs SET usg_pct=0.40, min=12 WHERE player_id=1 AND season_type='regular' AND game_date >= '2026-01-06'")
    return c


@pytest.fixture
async def client(conn, tmp_path, fixtures_dir):
    app = create_app(ReplaySource(fixtures_dir), db_path=str(tmp_path / "l.db"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def get(client, **params):
    r = await client.get("/api/leaders/players", params={"season": SEASON, **params})
    assert r.status_code == 200, r.text
    return r.json()


async def test_per_game_leaders_apply_the_games_rule(client):
    d = await get(client)
    names = [r["name"] for r in d["rows"]]
    assert "Part Timer" not in names  # 6 of 10 games < 70%
    assert names[0] == "Star" and d["rows"][0]["value"] == 30 and d["rows"][0]["rank"] == 1
    assert names.index("Other Team") == 1 and d["rows"][1]["value"] == 25  # 6 of the 8 games his team played (>= 6) qualifies
    assert [r["value"] for r in d["rows"]] == sorted((r["value"] for r in d["rows"]), reverse=True)
    assert d["team_games"] == 10 and "70% of their team" in d["requirement"] and "7 of 10" in d["requirement"]
    assert d["total"] == len(d["rows"]) and d["mode"] == "pg" and d["label"] == "Points"


async def test_everyone_option_includes_the_part_timer(client):
    d = await get(client, qualified=False)
    assert d["rows"][0]["name"] == "Part Timer" and d["rows"][0]["value"] == 40 and d["rows"][0]["gp"] == 6
    assert d["requirement"] is None


async def test_totals_mode(client):
    d = await get(client, mode="total", qualified=False)
    assert d["rows"][0]["name"] == "Star" and d["rows"][0]["value"] == 300  # 30 x 10
    assert next(r for r in d["rows"] if r["name"] == "Part Timer")["value"] == 240
    reb = await get(client, stat="reb", mode="total")
    assert reb["rows"][0]["name"] == "Big Man" and reb["rows"][0]["value"] == 140 and reb["requirement"] is None  # no games rule for totals


async def test_rate_stats_have_attempt_requirements(client):
    d = await get(client, stat="fg_pct")
    # Other Team .500 (54 FGM, needs 3.65 x 8 = 29.2) leads Star .400 (100 FGM, needs 36.5).
    # Big Man shoots .600 but made only 30 (< 36.5), and Part Timer's .750 fails the games rule.
    # Just Enough has the games (7 of 10) but only 14 FGM; Zero made none. Exactly two players qualify.
    assert [(r["name"], round(r["value"], 3)) for r in d["rows"]] == [("Other Team", 0.5), ("Star", 0.4)]
    assert "field goals made" in d["requirement"]
    everyone = await get(client, stat="fg_pct", qualified=False)
    assert everyone["rows"][0]["name"] == "Part Timer" and everyone["rows"][0]["value"] == pytest.approx(0.75)
    assert next(r for r in everyone["rows"] if r["name"] == "Big Man")["value"] == pytest.approx(0.6)


async def test_three_point_pct_skips_players_who_never_shoot_threes(client):
    d = await get(client, stat="fg3_pct", qualified=False)
    names = [r["name"] for r in d["rows"]]
    assert "Big Man" not in names and "Zero" not in names  # 0 attempts -> no percentage
    assert (d["rows"][0]["name"], d["rows"][0]["value"]) == ("Star", pytest.approx(30 / 80))  # 3-of-8 every game
    assert next(r for r in d["rows"] if r["name"] == "Other Team")["value"] == pytest.approx(1 / 3)


async def test_double_and_triple_doubles(client):
    dd = await get(client, stat="dd")
    # Star: pts 30 + reb 10 in all 10 games. Just Enough: pts 20 + reb 10 + ast 10 in 2 games (a triple-double each time).
    # Big Man (reb 14 only) and everyone else have none and are left out rather than listed with zeros.
    assert [(r["name"], r["dd"]) for r in dd["rows"]] == [("Star", 10), ("Just Enough", 2)]
    td = await get(client, stat="td")
    assert [(r["name"], r["td"]) for r in td["rows"]] == [("Just Enough", 2)]


async def test_usage_is_minutes_weighted_and_optional(client):
    d = await get(client, stat="usg")
    # 5 games at 36 min with .20 usage + 5 games at 12 min with .40: weighted (36+24)/240 = 25%, not the plain average 30%
    assert d["rows"][0]["name"] == "Star" and d["rows"][0]["value"] == pytest.approx(25.0)
    assert all(r["name"] != "Big Man" for r in d["rows"])  # no usage data -> not ranked


async def test_playoffs_are_separate_and_seasons_validated(client):
    po = await get(client, season_type="playoffs")
    assert [(r["name"], r["gp"], r["value"]) for r in po["rows"]] == [("Star", 4, 10)]
    assert (await client.get("/api/leaders/players", params={"season": "1999-00"})).status_code == 404
    assert (await client.get("/api/leaders/players", params={"stat": "bogus"})).status_code == 422
    assert (await client.get("/api/leaders/players", params={"mode": "weird"})).status_code == 422
    assert len((await get(client, limit=2))["rows"]) == 2


async def test_ties_are_stable(client, conn):
    with conn:
        for i in range(10):
            log(conn, 7, i, T1, pts=30, reb=10, ast=5, fgm=10, fga=25)  # same 30 ppg as Star
        ingest.load_roster(conn, [{"id": 7, "full_name": "Twin", "first_name": "T", "last_name": "W", "is_active": True}])
    a = [r["name"] for r in (await get(client))["rows"]][:3]
    b = [r["name"] for r in (await get(client))["rows"]][:3]
    assert a == b and set(a[:2]) == {"Star", "Twin"}


@pytest.fixture
async def team_client(tmp_path, fixtures_dir):
    c = db.connect(tmp_path / "t.db")
    ingest.sync_league(c, LeagueFetcher(fixtures_dir / "teams"), [SEASON])
    app = create_app(ReplaySource(fixtures_dir), db_path=str(tmp_path / "t.db"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        yield client


async def test_team_leaders_best_first(team_client):
    net = (await team_client.get("/api/leaders/teams", params={"stat": "net_rtg"})).json()
    vals = [r["value"] for r in net["rows"]]
    assert len(vals) == 30 and vals == sorted(vals, reverse=True) and net["lower_is_better"] is False
    assert net["rows"][0]["rank"] == 1 and net["rows"][-1]["rank"] == 30
    # lower is better for defence and turnovers: the best defence has the LOWEST rating
    d = (await team_client.get("/api/leaders/teams", params={"stat": "def_rtg"})).json()
    dv = [r["value"] for r in d["rows"]]
    assert d["lower_is_better"] is True and dv == sorted(dv)
    t = (await team_client.get("/api/leaders/teams", params={"stat": "tov"})).json()
    assert [r["value"] for r in t["rows"]] == sorted(r["value"] for r in t["rows"]) and t["team_games"] == 82
    row = net["rows"][0]
    assert set(row["stats"]) >= {"pts", "def_rtg", "net_rtg", "pace"} and row["w"] + row["l"] == 82
    assert (await team_client.get("/api/leaders/teams", params={"stat": "nope"})).status_code == 422
    assert (await team_client.get("/api/leaders/teams", params={"season": "1999-00"})).status_code == 404
