import types

import httpx
import pytest

from nbadash import db, without_api
from nbadash.app import create_app
from nbadash.sources import ReplaySource

T, OTHER = 100, 200
STAR, GUARD, WING, BENCH, FORMER = 1, 2, 3, 4, 5


@pytest.fixture
def env(tmp_path):
    c = db.connect(tmp_path / "w.db")
    with c:
        for pid, name, team in ((STAR, "The Star", T), (GUARD, "Guard Gary", T), (WING, "Wing Walt", T), (BENCH, "Bench Ben", T), (FORMER, "Former Fred", OTHER)):
            c.execute("INSERT INTO players (id, full_name, team_id, is_active) VALUES (?,?,?,1)", (pid, name, team))
    n = [0]

    def game(season, date, star_plays, guard=(20, 5, 5, 30), wing=(10, 4, 2, 25), bench=(2, 1, 0, 5), former=(30, 5, 5, 35), team=T):
        n[0] += 1
        gid = f"G{n[0]:03d}"
        with c:
            c.execute("INSERT INTO team_games (game_id, team_id, season, game_date, abbr, opp_abbr, home, wl, pts, plus_minus) VALUES (?,?,?,?,'T','X',1,'W',100,3)", (gid, team, season, date))
            rows = [(GUARD, guard), (WING, wing), (BENCH, bench), (FORMER, former)]
            if star_plays:
                rows.append((STAR, (30, 8, 6, 34)))
            for pid, (pts, reb, ast, mins) in rows:
                c.execute("INSERT INTO player_game_logs (player_id, game_id, season, season_type, game_date, min, pts, reb, ast, team_id) VALUES (?,?,?,'regular',?,?,?,?,?,?)",
                          (pid, gid, season, date, mins, pts, reb, ast, OTHER if pid == FORMER else team))
        return gid
    return types.SimpleNamespace(db=c, game=game)


def season(env, with_n, without_n, s="2025-26", **kw):
    for i in range(with_n):
        env.game(s, f"2025-11-{i + 1:02d}", True)
    for i in range(without_n):
        env.game(s, f"2025-12-{i + 1:02d}", False, **kw)


def test_teammates_with_and_without_the_star(env):
    season(env, 12, 4, guard=(26, 6, 9, 36), wing=(14, 5, 3, 30), bench=(3, 1, 1, 8))
    w = without_api.build(env.db, STAR)
    assert (w.seasons, w.games_with, w.games_without, w.team_id) == (["2025-26"], 12, 4, T)
    assert [t.name for t in w.teammates][:2] == ["Guard Gary", "Wing Walt"]  # biggest points jump first
    g = w.teammates[0]
    assert (g.with_player.pts, g.without.pts, g.pts_diff, g.min_diff, g.without.games, g.small_sample) == (20.0, 26.0, 6.0, 6.0, 4, True)
    assert "Bench Ben" not in [t.name for t in w.teammates]  # barely plays either way: noise
    assert "Former Fred" not in [t.name for t in w.teammates]  # no longer on the team
    assert "The Star" not in [t.name for t in w.teammates]


def test_too_few_missed_games_or_seasons_say_nothing(env):
    season(env, 12, 1)
    w = without_api.build(env.db, STAR)
    assert (w.games_without, w.teammates) == (1, [])
    assert without_api.build(env.db, GUARD).games_with >= 0  # a player with no qualifying seasons or history returns empty, not an error
    assert without_api.build(env.db, 999) is None


def test_a_short_season_with_the_team_is_not_counted(env):
    for i in range(6):
        env.game("2024-25", f"2024-11-{i + 1:02d}", True)  # only 6 games with the team that year
    for i in range(5):
        env.game("2024-25", f"2024-12-{i + 1:02d}", False)
    assert without_api.build(env.db, STAR).seasons == []


def test_a_mid_season_arrival_ignores_games_before_he_joined(env):
    # he played for another team early in the season; his new team's earlier games must not count as "without him"
    with env.db:
        for i in range(5):
            gid = f"E{i}"
            env.db.execute("INSERT INTO team_games (game_id, team_id, season, game_date, abbr, opp_abbr, home, wl, pts, plus_minus) VALUES (?, ?, '2025-26', ?, 'O', 'X', 1, 'W', 100, 3)", (gid, OTHER, f"2025-10-{i + 1:02d}"))
            env.db.execute("INSERT INTO player_game_logs (player_id, game_id, season, season_type, game_date, min, pts, reb, ast, team_id) VALUES (?, ?, '2025-26', 'regular', ?, 30, 20, 5, 5, ?)", (STAR, gid, f"2025-10-{i + 1:02d}", OTHER))
    for i in range(6):
        env.game("2025-26", f"2025-10-{i + 1:02d}", False)  # the new team's games in October, before the trade
    season(env, 12, 3)  # November: with him, December: without
    w = without_api.build(env.db, STAR)
    assert (w.games_with, w.games_without) == (12, 3)  # the six October games are not counted


async def test_without_endpoint(env, tmp_path, fixtures_dir):
    season(env, 12, 4, guard=(26, 6, 9, 36))
    app = create_app(ReplaySource(fixtures_dir), db_path=str(tmp_path / "w.db"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        d = (await client.get(f"/api/players/{STAR}/without")).json()
        assert d["teammates"][0]["name"] == "Guard Gary" and d["games_without"] == 4
        assert (await client.get("/api/players/999/without")).status_code == 404
