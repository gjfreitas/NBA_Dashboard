import types
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from nbadash import db, slate_api
from nbadash.app import create_app
from nbadash.sources import ReplaySource

NOW = datetime(2026, 10, 24, 14, 0, tzinfo=timezone.utc)
DEN, NOP = 1610612743, 1610612740


def row(book, line, over, under, opening=None):
    return {"book": book, "line": line, "over_price": over, "under_price": under, "opening_line": opening if opening is not None else line, "updated_at": None}


def test_consensus_is_the_most_common_line_and_best_prices_come_from_that_line():
    m = slate_api.market_lines([row("a", 24.5, -115, -105), row("b", 24.5, -110, -110), row("c", 25.5, 105, -135), row("d", 24.5, 100, -130)])
    assert m.line == 24.5
    assert (m.best_over.book, m.best_over.price) == ("d", 100)  # +100 beats -110: higher is better, and c's +105 is at a different line
    assert (m.best_under.book, m.best_under.price) == ("a", -105)
    assert [b.book for b in m.books] == ["a", "b", "d", "c"]  # nearest the consensus first, then by book name
    # a tie between two lines goes to the one nearest the median
    tie = slate_api.market_lines([row("a", 24.5, -110, -110), row("b", 24.5, -110, -110), row("c", 26.5, -110, -110), row("d", 26.5, -110, -110), row("e", 25.5, -110, -110)])
    assert tie.line == 24.5  # 24.5 and 26.5 are equally common and equally far from the median 25.5: the lower one
    one = slate_api.market_lines([row("a", 5.5, -120, None)])
    assert (one.line, one.best_under) == (5.5, None) and one.best_over.price == -120


def test_short_positions():
    assert slate_api.short_position("Guard-Forward") == "G-F" and slate_api.short_position("Center") == "C" and slate_api.short_position(None) is None


@pytest.fixture
def env(tmp_path):
    c = db.connect(tmp_path / "s.db")
    with c:
        c.execute("INSERT INTO teams (id, abbr, city, name) VALUES (?, 'DEN', 'Denver', 'Nuggets')", (DEN,))
        c.execute("INSERT INTO teams (id, abbr, city, name) VALUES (?, 'NOP', 'New Orleans', 'Pelicans')", (NOP,))
        c.execute("INSERT INTO schedule (game_id, season, game_date, start_utc, status, home_id, away_id, home_abbr, away_abbr) VALUES ('G1','2026-27','2026-10-24','2026-10-24T23:00:00Z',1,?,?,'DEN','NOP')", (DEN, NOP))
        c.execute("INSERT INTO schedule (game_id, season, game_date, start_utc, status, home_id, away_id, home_abbr, away_abbr) VALUES ('G2','2026-27','2026-10-25','2026-10-25T23:00:00Z',1,?,?,'DEN','NOP')", (DEN, NOP))
        for pid, name, team, pos in ((1, "Nikola Jokić", "DEN", "Center"), (2, "Zion Williamson", "NOP", "Forward"), (3, "Traded Guy", "LAL", "Guard")):
            c.execute("INSERT INTO players (id, full_name, team_abbr, position, is_active) VALUES (?,?,?,?,1)", (pid, name, team, pos))

    def add(game, pid, name, market, book, line, over, under, seen):
        with c:
            c.execute("INSERT INTO prop_lines (source,event_id,game_id,player_id,player_name,market,book,line,over_price,under_price,seen_at) VALUES ('s','e',?,?,?,?,?,?,?,?,?)",
                      (game, pid, name, market, book, line, over, under, seen))
    return types.SimpleNamespace(db=c, add=add)


def test_slate_groups_players_by_game_and_orders_stars_first(env):
    conn = env
    seen = NOW.isoformat(timespec="seconds")
    conn.add("G1", 2, "Zion Williamson", "pts", "dk", 22.5, -110, -110, seen)
    conn.add("G1", 1, "Nikola Jokic", "pts", "dk", 24.5, -110, -110, "2026-10-24T06:00:00+00:00")  # opened at 24.5 ...
    conn.add("G1", 1, "Nikola Jokic", "pts", "dk", 25.5, -115, -105, seen)  # ... and moved to 25.5
    conn.add("G1", 3, "Traded Guy", "ast", "dk", 5.5, -110, -110, seen)
    conn.add("G2", 1, "Nikola Jokic", "pts", "dk", 30.5, -110, -110, seen)  # another day's game is not on this slate
    s = slate_api.build_slate(conn.db, "2026-10-24", NOW)
    assert [g.game_id for g in s.games] == ["G1"] and (s.games[0].away.abbr, s.games[0].home.abbr) == ("NOP", "DEN")
    names = [(p.name, p.team_abbr, p.position) for p in s.games[0].players]
    assert names[:2] == [("Nikola Jokić", "DEN", "C"), ("Zion Williamson", "NOP", "F")]  # our spelling; higher points line first
    assert ("Traded Guy", None, "G") in names  # not on either team of this game: kept, but not placed on a side
    jok = s.games[0].players[0].markets["pts"]
    assert (jok.line, jok.books[0].opening_line) == (25.5, 24.5)
    assert slate_api.build_slate(conn.db, "2026-10-26", NOW).games == []


def test_old_lines_and_injuries(env):
    conn = env
    conn.add("G1", 1, "Nikola Jokic", "pts", "dk", 25.5, -110, -110, (NOW - timedelta(hours=40)).isoformat(timespec="seconds"))
    assert slate_api.build_slate(conn.db, "2026-10-24", NOW).games[0].players == []  # a day and a half old: not today's line
    conn.add("G1", 1, "Nikola Jokic", "pts", "dk", 25.5, -110, -110, NOW.isoformat(timespec="seconds"))
    with conn.db:
        conn.db.execute("INSERT INTO injury_reports VALUES ('r', '2026-10-24T09:00', ?, ?, 1, 0)", (NOW.isoformat(timespec="seconds"), NOW.isoformat()))
        conn.db.execute("INSERT INTO injuries VALUES ('r',0,'2026-10-24','07:00 (ET)','NOP@DEN','G1','Denver Nuggets',?, 'DEN','Jokic, Nikola',1,'Questionable','Injury/Illness - Left Knee')", (DEN,))
    p = slate_api.build_slate(conn.db, "2026-10-24", NOW).games[0].players[0]
    assert (p.injury.status, p.injury.reason) == ("Questionable", "Injury/Illness - Left Knee")


async def test_slate_endpoint(env, tmp_path, fixtures_dir):
    conn = env
    conn.add("G1", 1, "Nikola Jokic", "pts", "dk", 25.5, -110, -110, datetime.now(timezone.utc).isoformat(timespec="seconds"))
    app = create_app(ReplaySource(fixtures_dir), db_path=str(tmp_path / "s.db"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        d = (await client.get("/api/slate", params={"date": "2026-10-24"})).json()
        assert d["date"] == "2026-10-24" and d["games"][0]["players"][0]["markets"]["pts"]["line"] == 25.5
        assert (await client.get("/api/slate", params={"date": "tomorrow"})).status_code == 422
        assert "games" in (await client.get("/api/slate")).json()


def test_one_player_is_one_row_whichever_way_each_provider_spells_the_name(env):
    conn = env
    seen = NOW.isoformat(timespec="seconds")
    conn.add("G1", 1, "Nikola Jokic", "pts", "dk", 25.5, -110, -110, seen)   # one provider
    conn.add("G1", 1, "Nikola Jokić", "pts", "dk", 25.5, -112, -108, seen)   # another spells it differently, same book: the newer one wins
    conn.add("G1", 1, "Nikola Jokic", "pts", "fd", 26.5, -105, -115, seen)
    players = slate_api.build_slate(conn.db, "2026-10-24", NOW).games[0].players
    assert len(players) == 1
    m = players[0].markets["pts"]
    assert sorted(b.book for b in m.books) == ["dk", "fd"] and [b for b in m.books if b.book == "dk"][0].over_price == -112


def test_game_props_include_usual_minutes_only_with_enough_games(env):
    conn = env
    conn.add("G1", 1, "Nikola Jokic", "pts", "dk", 25.5, -110, -110, NOW.isoformat(timespec="seconds"))
    conn.add("G1", 2, "Zion Williamson", "pts", "dk", 22.5, -110, -110, NOW.isoformat(timespec="seconds"))
    with conn.db:
        conn.db.execute("INSERT INTO league_players (player_id, season, team_id, name, gp, min, pts) VALUES (1, '2025-26', ?, 'Nikola Jokic', 70, 34.5, 27)", (DEN,))
        conn.db.execute("INSERT INTO league_players (player_id, season, team_id, name, gp, min, pts) VALUES (1, '2026-27', ?, 'Nikola Jokic', 2, 20.0, 25)", (DEN,))  # 2 games: ignored
        conn.db.execute("INSERT INTO league_players (player_id, season, team_id, name, gp, min, pts) VALUES (2, '2026-27', ?, 'Zion Williamson', 3, 30.0, 20)", (NOP,))
    gp = slate_api.game_props(conn.db, "G1", NOW)
    assert gp.game.game_id == "G1" and len(gp.game.players) == 2
    assert gp.avg_min == {1: 34.5}  # Zion has only 3 games and no earlier season: no usual minutes
    assert slate_api.game_props(conn.db, "NOPE", NOW) is None


async def test_game_props_endpoint(env, tmp_path, fixtures_dir):
    env.add("G1", 1, "Nikola Jokic", "pts", "dk", 25.5, -110, -110, datetime.now(timezone.utc).isoformat(timespec="seconds"))
    app = create_app(ReplaySource(fixtures_dir), db_path=str(tmp_path / "s.db"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        assert (await client.get("/api/games/G1/props")).json()["game"]["game_id"] == "G1"
        assert (await client.get("/api/games/NOPE/props")).status_code == 404
