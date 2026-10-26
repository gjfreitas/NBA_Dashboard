import types
from datetime import datetime, timezone

import httpx
import pytest

from nbadash import db, today_api
from nbadash.app import create_app
from nbadash.sources import ReplaySource

NOW = datetime(2026, 10, 24, 14, 0, tzinfo=timezone.utc)
DEN, NOP = 1610612743, 1610612740


@pytest.fixture
def env(tmp_path):
    c = db.connect(tmp_path / "t.db")
    with c:
        c.execute("INSERT INTO teams (id, abbr, city, name) VALUES (?, 'DEN', 'Denver', 'Nuggets')", (DEN,))
        c.execute("INSERT INTO teams (id, abbr, city, name) VALUES (?, 'NOP', 'New Orleans', 'Pelicans')", (NOP,))
        c.execute("INSERT INTO schedule (game_id, season, game_date, start_utc, status, home_id, away_id, home_abbr, away_abbr) VALUES ('G1','2026-27','2026-10-24','2026-10-24T23:00:00Z',1,?,?,'DEN','NOP')", (DEN, NOP))
        c.execute("INSERT INTO schedule (game_id, season, game_date, start_utc, status, home_id, away_id, home_abbr, away_abbr) VALUES ('G0','2026-27','2026-10-23','2026-10-23T23:00:00Z',3,?,?,'DEN','NOP')", (DEN, NOP))
        for tid, abbr, w, l in ((DEN, "Denver Nuggets", 1, 0), (NOP, "New Orleans Pelicans", 0, 1)):
            c.execute("INSERT INTO team_season (team_id, season, name, gp, w, l) VALUES (?, '2026-27', ?, 1, ?, ?)", (tid, abbr, w, l))
        # yesterday's game: both teams played it (so tonight is a back-to-back for both)
        c.execute("INSERT INTO team_games (game_id, team_id, season, game_date, abbr, opp_abbr, home, wl, pts, plus_minus) VALUES ('G0', ?, '2026-27', '2026-10-23', 'DEN', 'NOP', 1, 'W', 110, 5)", (DEN,))
        c.execute("INSERT INTO team_games (game_id, team_id, season, game_date, abbr, opp_abbr, home, wl, pts, plus_minus) VALUES ('G0', ?, '2026-27', '2026-10-23', 'NOP', 'DEN', 0, 'L', 105, -5)", (NOP,))
        for pid, name, team in ((1, "Nikola Jokić", "DEN"), (2, "Zion Williamson", "NOP")):
            c.execute("INSERT INTO players (id, full_name, team_abbr, team_id, is_active) VALUES (?,?,?,?,1)", (pid, name, team, DEN if team == "DEN" else NOP))

    def add(pid, name, market, book, line, seen):
        with c:
            c.execute("INSERT INTO prop_lines (source,event_id,game_id,player_id,player_name,market,book,line,over_price,under_price,seen_at) VALUES ('s','e','G1',?,?,?,?,?,-110,-110,?)",
                      (pid, name, market, book, line, seen))
    return types.SimpleNamespace(db=c, add=add)


def test_line_moves_compare_the_consensus_now_with_the_consensus_at_the_first_sighting(env):
    for book in ("a", "b", "c"):
        env.add(1, "Nikola Jokic", "pts", book, 24.5, "2026-10-24T06:00:00+00:00")
        env.add(1, "Nikola Jokic", "pts", book, 26.0, NOW.isoformat(timespec="seconds"))
    env.add(2, "Zion Williamson", "pts", "a", 22.5, "2026-10-24T06:00:00+00:00")
    env.add(2, "Zion Williamson", "pts", "a", 23.0, NOW.isoformat(timespec="seconds"))  # moved half a point: below the 1.0 threshold
    moves = today_api.line_moves(env.db, "2026-10-24", 1.0, NOW)
    assert [(m.name, m.market, m.opening, m.now, m.move) for m in moves] == [("Nikola Jokić", "pts", 24.5, 26.0, 1.5)]
    assert len(today_api.line_moves(env.db, "2026-10-24", 0.5, NOW)) == 2 and today_api.line_moves(env.db, "2026-10-24", 2.0, NOW) == []
    with env.db:
        env.db.execute("UPDATE schedule SET status=2")  # under way: pre-game moves are no longer news
    assert today_api.line_moves(env.db, "2026-10-24", 1.0, NOW) == []


def test_today_lists_games_with_rest_records_and_line_counts(env):
    env.add(1, "Nikola Jokic", "pts", "a", 25.5, NOW.isoformat(timespec="seconds"))
    t = today_api.build_today(env.db, "2026-10-24", NOW)
    [g] = t.games
    assert (g.game_id, g.status, g.players_with_lines) == ("G1", 1, 1)
    assert (g.home.abbr, g.home.record, g.home.days_rest, g.home.back_to_back, g.home.streak) == ("DEN", "1-0", 0, True, "W1")
    assert (g.away.record, g.away.back_to_back, g.away.streak) == ("0-1", True, "L1")
    assert today_api.build_today(env.db, "2026-10-30", NOW).games == []


async def test_today_endpoints(env, tmp_path, fixtures_dir):
    app = create_app(ReplaySource(fixtures_dir), db_path=str(tmp_path / "t.db"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        d = (await client.get("/api/today", params={"date": "2026-10-24"})).json()
        assert d["date"] == "2026-10-24" and d["games"][0]["home"]["name"] == "Denver Nuggets" and d["moves"] == []
        assert (await client.get("/api/lines/moves", params={"date": "2026-10-24"})).json() == []
        assert (await client.get("/api/lines/moves", params={"min_move": 0.1})).status_code == 422
        assert (await client.get("/api/today", params={"date": "nope"})).status_code == 422
