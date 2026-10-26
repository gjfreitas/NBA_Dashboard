import types

import httpx
import pytest
from fastapi import HTTPException

from nbadash import db, matchup_api
from nbadash.app import create_app
from nbadash.sources import ReplaySource

A, B, C = 1, 2, 3
S = "2025-26"


@pytest.fixture
def env(tmp_path):
    c = db.connect(tmp_path / "m.db")
    with c:
        for tid, abbr, pace in ((A, "AAA", 104.0), (B, "BBB", 98.0), (C, "CCC", 101.0)):
            c.execute("INSERT INTO teams (id, abbr, city, name) VALUES (?,?,?,?)", (tid, abbr, abbr, abbr))
            c.execute("INSERT INTO team_season (team_id, season, name, gp, w, l, pace) VALUES (?,?,?,20,10,10,?)", (tid, S, abbr, pace))
        # one guard, forward and center on each team (positions as the NBA writes them)
        for pid, team, pos in ((11, A, "Guard-Forward"), (12, A, "Forward"), (13, A, "Center"), (21, B, "Guard"), (22, B, "Forward-Center"), (23, B, "Center"), (31, C, "Guard"), (32, C, "Forward"), (33, C, "Center")):
            c.execute("INSERT INTO players (id, full_name, team_id, position, is_active) VALUES (?,?,?,?,1)", (pid, f"P{pid}", team, pos))
        game = [0]

        def play(home, away, pts_by_player):  # home/away team ids, {player_id: (team, pts)}
            game[0] += 1
            gid = f"G{game[0]}"
            for t in (home, away):
                c.execute("INSERT INTO team_games (game_id, team_id, season, game_date, abbr, opp_abbr, home, wl, pts, plus_minus) VALUES (?,?,?,?,'X','Y',1,'W',100,1)", (gid, t, S, f"2025-11-{game[0]:02d}"))
            for pid, (team, pts) in pts_by_player.items():
                c.execute("INSERT INTO player_game_logs (player_id, game_id, season, season_type, game_date, min, pts, reb, ast, team_id) VALUES (?,?,?,'regular','2025-11-01',30,?,5,3,?)", (pid, gid, S, pts, team))
        # A's opponents' guards (players 21, 31) score a lot against A; B's opponents' guards score little
        play(A, B, {11: (A, 20), 12: (A, 10), 13: (A, 8), 21: (B, 30), 22: (B, 12), 23: (B, 9)})
        play(A, C, {11: (A, 20), 12: (A, 10), 13: (A, 8), 31: (C, 26), 32: (C, 11), 33: (C, 10)})
        play(B, C, {21: (B, 12), 22: (B, 9), 23: (B, 7), 31: (C, 14), 32: (C, 8), 33: (C, 6)})
        # zones: A shoots mostly at the rim, B's defence is bad at the rim; C is average
        for pid, zone, fgm, fga in ((11, "Restricted Area", 30, 40), (11, "Mid-Range", 5, 20), (12, "Restricted Area", 10, 20)):
            c.execute("INSERT INTO player_zones VALUES (?,?,?,?,?)", (pid, S, zone, fgm, fga))
        for tid, rim, mid in ((A, (60, 100), (40, 100)), (B, (75, 100), (45, 100)), (C, (65, 100), (40, 100))):
            c.execute("INSERT INTO team_zones_def VALUES (?,?,?,?,?)", (tid, S, "Restricted Area", *rim))
            c.execute("INSERT INTO team_zones_def VALUES (?,?,?,?,?)", (tid, S, "Mid-Range", *mid))
    return types.SimpleNamespace(db=c)


def test_defence_by_position_ranks_and_averages(env):
    m = matchup_api.build(env.db, A, B)
    a = {r.position: r for r in m.home.defence_by_position}  # A's defence: opposing guards scored 30 and 26
    assert (a["G"].pts, a["G"].games) == (28.0, 2) and a["G"].pts_rank == 3  # the most points allowed to guards in the league
    assert a["F"].pts == 11.5 and a["C"].pts == 9.5
    b = {r.position: r for r in m.away.defence_by_position}  # B's defence: the opposing guard scored 20 (from A) and 14 (from C)
    assert b["G"].pts == 17.0 and b["G"].pts_rank == 2  # C's defence allowed 16 (guards scored 20 and 12): the stingiest
    assert a["G"].league_pts == round((28 + 17 + 16) / 3, 1)
    # a forward-center is counted as a forward (the first position listed)
    assert matchup_api.pos_letter("Forward-Center") == "F" and matchup_api.pos_letter("Guard-Forward") == "G" and matchup_api.pos_letter(None) is None


def test_pace_and_expected_tempo(env):
    p = matchup_api.build(env.db, A, B).pace
    assert (p.home, p.away, p.expected, p.league, p.home_rank, p.away_rank) == (104.0, 98.0, 101.0, 101.0, 1, 3)


def test_zone_matchups_use_the_attackers_shots_and_the_defenders_percentages(env):
    m = matchup_api.build(env.db, A, B)
    rim = next(z for z in m.home.offence_vs_opponent_zones if z.zone == "Restricted Area")
    assert rim.shot_share == 0.75  # 60 of A's 80 shots are at the rim (40 + 20), 20 are mid-range
    assert (rim.fg_pct_allowed, rim.def_rank) == (0.75, 3)  # B allows 75% at the rim: the worst defence of the three
    assert rim.league_fg_pct == round((60 + 75 + 65) / 300, 3)
    away_rim = next(z for z in m.away.offence_vs_opponent_zones if z.zone == "Restricted Area")
    assert (away_rim.shot_share, away_rim.fg_pct_allowed, away_rim.def_rank) == (0.0, 0.6, 1)  # B has no shot data here; A's defence is the best at the rim


def test_unknown_teams_are_a_404(env):
    with pytest.raises(HTTPException):
        matchup_api.build(env.db, 98, 99)


async def test_matchup_endpoint(env, tmp_path, fixtures_dir):
    app = create_app(ReplaySource(fixtures_dir), db_path=str(tmp_path / "m.db"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        d = (await client.get("/api/preview/matchup", params={"home": A, "away": B})).json()
        assert d["season"] == S and d["is_fallback"] is False and d["pace"]["expected"] == 101.0
        assert (await client.get("/api/preview/matchup", params={"home": 98, "away": 99})).status_code == 404
