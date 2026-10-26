import types

import httpx
import pytest

from nbadash import boost_api, db
from nbadash.app import create_app
from nbadash.sources import ReplaySource

PREV, CUR = "2025-26", "2026-27"
A, B, C, D = 1, 2, 3, 4  # B is a soft defence last season and an average one this season; C is tough last season; A and D are average


def test_helpers():
    assert [boost_api.ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 30)] == ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "30th"]
    assert boost_api.rank_text("UTA", 1, 30, True) == "UTA allow the 1st most"
    assert boost_api.rank_text("DET", 30, 30, False) == "DET allow the 1st fewest"  # the team that allows the 30th most allows the 1st fewest
    assert boost_api.rank_text("DET", 2, 30, True, " (effective FG%)") == "DET allow the 2nd most (effective FG%)"
    assert boost_api.weighted_effect([(0.5, 0.10), (0.5, -0.04)]) == pytest.approx(3.0)
    assert boost_api.weighted_effect([(0.0, 0.5)]) is None and boost_api.weighted_effect([]) is None
    assert boost_api.combine(None, 4.0, 2.0) == 3.0 and boost_api.combine(None, None) is None


def test_the_ramp_from_last_season_to_this_one():
    r = boost_api.ramp
    assert [r(g) for g in (None, 0, 5, 10)] == [0.0, 0.0, 0.0, 0.0]  # up to 10 games: all last season
    assert (r(15), r(20), r(25), r(30), r(60)) == (0.25, 0.5, 0.75, 1.0, 1.0)  # a straight line, then all this season
    assert (r(20, 0.7), r(30, 0.7), r(80, 0.7)) == (0.5, 0.7, 0.7)  # the noisiest numbers never go past 70% this season
    assert boost_api.blend(0.2, 0.0, 0.5) == pytest.approx(0.1)
    assert boost_api.blend(None, 0.3, 0.9) == 0.3 and boost_api.blend(0.3, None, 0.0) == 0.3 and boost_api.blend(None, None, 0.5) is None


@pytest.fixture
def env(tmp_path):
    c = db.connect(tmp_path / "b.db")
    with c:
        for tid, abbr in ((A, "AAA"), (B, "BBB"), (C, "CCC"), (D, "DDD")):
            c.execute("INSERT INTO teams (id, abbr, city, name) VALUES (?,?,?,?)", (tid, abbr, abbr, abbr))
            c.execute("INSERT INTO team_season (team_id, season, name, gp, w, l) VALUES (?,?,?,82,41,41)", (tid, PREV, abbr))
            c.execute("INSERT INTO team_season (team_id, season, name, gp, w, l) VALUES (?,?,?,30,15,15)", (tid, CUR, abbr))
        c.execute("INSERT INTO schedule (game_id, season, game_date, start_utc, status, home_id, away_id, home_abbr, away_abbr) VALUES ('G1',?,'2026-11-26','2026-11-26T23:00:00Z',1,?,?,'AAA','BBB')", (CUR, A, B))
        c.execute("INSERT INTO schedule (game_id, season, game_date, start_utc, status, home_id, away_id, home_abbr, away_abbr) VALUES ('G2',?,'2026-11-26','2026-11-27T01:00:00Z',1,?,?,'CCC','DDD')", (CUR, C, D))
        # points per 100 possessions allowed. Last season: B soft (1.30), C tough (0.90), A and D average; this season everybody is average.
        last = {A: 1.10, B: 1.30, C: 0.90, D: 1.10}
        for tid in (A, B, C, D):
            for season, ppp in ((PREV, last[tid]), (CUR, 1.10)):
                c.execute("INSERT INTO team_play_types_def VALUES (?,?,'Transition',100,?)", (tid, season, 100 * ppp))
                c.execute("INSERT INTO team_play_types_def VALUES (?,?,'Postup',100,?)", (tid, season, 100 * ppp))
                c.execute("INSERT INTO team_play_types_def VALUES (?,?,'Isolation',100,100)", (tid, season))
                c.execute("INSERT INTO team_shot_types_def VALUES (?,?,'catch_shoot',40,100,10,30)", (tid, season))
        people = ((10, "Fast Guard", A), (11, "Bench Guy", A), (12, "Rookie", A), (13, "Hurt Star", A), (14, "Post Man", A), (15, "This Season", A),
                  (20, "Their Guard", B), (30, "Cold Guard", C), (40, "Plain Guard", D))
        for pid, name, team in people:
            c.execute("INSERT INTO players (id, full_name, team_id, position, is_active) VALUES (?,?,?,'Guard',1)", (pid, name, team))
        for pid in (10, 13, 15, 20, 30, 40):  # half transition, half isolation (last season)
            c.execute("INSERT INTO player_play_types VALUES (?,?,'Transition',30,300.0,300,0,0)", (pid, PREV))
            c.execute("INSERT INTO player_play_types VALUES (?,?,'Isolation',30,300.0,300,0,0)", (pid, PREV))
        c.execute("INSERT INTO player_play_types VALUES (14,?,'Postup',30,300.0,600,0,0)", (PREV,))  # all of his points are post-ups
        c.execute("INSERT INTO player_play_types VALUES (15,?,'Postup',16,160.0,320,0,0)", (CUR,))  # this season he is all post-ups
        n = [0]

        def games(pid, season, count, pts):
            for _ in range(count):
                n[0] += 1
                c.execute("INSERT INTO player_game_logs (player_id, game_id, season, season_type, game_date, min, pts, team_id) VALUES (?,?,?,'regular','2025-12-01',30,?,1)", (pid, f"L{n[0]}", season, pts))
        for pid in (10, 13, 14, 20, 30, 40):
            games(pid, PREV, 30, 20)
        games(11, PREV, 30, 4)  # bench: under the scoring floor
        games(12, PREV, 5, 20)  # too few games
        games(15, PREV, 30, 20); games(15, CUR, 16, 20)  # enough games this season: his own profile switches to this season's
        c.execute("INSERT INTO injury_reports VALUES ('r','2026-11-26T09:00','2026-11-26T13:00:00+00:00','x',1,0)")
        c.execute("INSERT INTO injuries VALUES ('r',0,'2026-11-26','x','BBB@AAA','G1','AAA',?, 'AAA','Star, Hurt',13,'Out','x')", (A,))

    def set_gp(team, gp):
        with c:
            c.execute("UPDATE team_season SET gp=? WHERE team_id=? AND season=?", (gp, team, CUR))
    return types.SimpleNamespace(db=c, set_gp=set_gp)


def fast(env):
    return {x.name: x for x in boost_api.build(env.db, "2026-11-26").all}["Fast Guard"]


def test_the_defence_moves_from_last_season_to_this_one_as_the_team_plays(env):
    soft_last_season = 0.5 * 100 * (1.30 / 1.10 - 1)  # half his points are transition, where B allowed 18.2% more than the league
    env.set_gp(B, 8)
    assert fast(env).style_pct == pytest.approx(soft_last_season, abs=0.1) and fast(env).season_weight == 0.0  # barely played: all last season
    env.set_gp(B, 10)
    assert fast(env).style_pct == pytest.approx(soft_last_season, abs=0.1)
    env.set_gp(B, 20)
    assert fast(env).style_pct == pytest.approx(soft_last_season / 2, abs=0.1) and fast(env).season_weight == 0.5 and fast(env).opp_games == 20
    env.set_gp(B, 30)
    assert fast(env).style_pct == pytest.approx(0.0, abs=0.1) and fast(env).season_weight == 1.0  # this season B is average


def test_noisy_play_types_never_go_fully_to_this_season(env):
    env.set_gp(B, 50)  # a full ramp: 100% this season, except for numbers that stay noisy
    post = {x.name: x for x in boost_api.build(env.db, "2026-11-26").all}["Post Man"]
    # post-ups are 100% of his points; B allowed +18.2% last season and 0% this season: 30% of last season stays in
    assert post.style_pct == pytest.approx(100 * 0.3 * (1.30 / 1.10 - 1), abs=0.1)
    assert fast(env).style_pct == pytest.approx(0.0, abs=0.1)  # transition is not noisy: fully this season's, where B is average (isolation is average in both seasons)


def test_a_players_own_profile_uses_this_season_once_he_has_played_enough(env):
    by = {x.name: x for x in boost_api.build(env.db, "2026-11-26").all}
    assert (by["Fast Guard"].profile_season, by["This Season"].profile_season) == (PREV, CUR)  # 30 games last season only; 16 games this season
    assert by["This Season"].drivers[0].label == "Post up"  # his current-season mix, not last season's


def test_players_who_do_not_qualify_are_left_out(env):
    names = {x.name for x in boost_api.build(env.db, "2026-11-26").all}
    assert "Bench Guy" not in names and "Rookie" not in names and "Hurt Star" not in names
    assert boost_api.build(env.db, "2026-12-25").all == []  # no games that day


def test_soft_and_tough_defences_move_the_boost_in_opposite_directions(env):
    env.set_gp(B, 10)  # B: all last season, soft
    b = boost_api.build(env.db, "2026-11-26")
    by = {x.name: x for x in b.all}
    assert by["Fast Guard"].boost_pct > 0 and abs(by["Plain Guard"].boost_pct) < 0.1  # Plain Guard (D) faces C, which has played 30 games: this season it is average
    env.set_gp(C, 10)  # C early in the season: last season's tough defence still counts
    by = {x.name: x for x in boost_api.build(env.db, "2026-11-26").all}
    assert by["Plain Guard"].style_pct == pytest.approx(0.5 * 100 * (0.90 / 1.10 - 1), abs=0.1)  # now C is all last season: tough in transition
    best = [x.name for x in boost_api.build(env.db, "2026-11-26").best]
    assert set(best[:2]) == {"Post Man", "This Season"} and best[2] == "Fast Guard"  # all of those two's points are post-ups against the soft defence; half of Fast Guard's are transition
    assert [x.name for x in boost_api.build(env.db, "2026-11-26").toughest][0] == "Plain Guard"


def test_with_no_previous_season_the_current_one_is_used_whatever_the_games(env):
    with env.db:
        for t in ("team_season", "team_play_types_def", "team_shot_types_def", "player_play_types"):
            env.db.execute(f"DELETE FROM {t} WHERE season=?", (PREV,))
        env.db.execute("DELETE FROM player_game_logs WHERE season=?", (PREV,))
        env.db.execute("INSERT INTO player_play_types VALUES (10,?,'Transition',16,160.0,320,0,0)", (CUR,))
        for i in range(16):
            env.db.execute("INSERT INTO player_game_logs (player_id, game_id, season, season_type, game_date, min, pts, team_id) VALUES (10,?,?,'regular','2026-11-01',30,20,1)", (f"N{i}", CUR))
    env.set_gp(B, 3)  # three games and nothing to fall back on
    got = {x.name: x for x in boost_api.build(env.db, "2026-11-26").all}
    assert "Fast Guard" in got and got["Fast Guard"].season_weight == 0.0  # the weight says "none of it is this season's", yet it is the only data there is


async def test_boosts_endpoint(env, tmp_path, fixtures_dir):
    app = create_app(ReplaySource(fixtures_dir), db_path=str(tmp_path / "b.db"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        d = (await client.get("/api/today/boosts", params={"date": "2026-11-26"})).json()
        assert (d["season"], d["previous_season"]) == (CUR, PREV) and d["all"][0]["drivers"][0]["detail"] and "season_weight" in d["all"][0]
        assert (await client.get("/api/today/boosts", params={"date": "bad"})).status_code == 422
