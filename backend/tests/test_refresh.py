import json
from datetime import datetime, timedelta, timezone

import pytest

from nbadash import db, ingest, refresh
from test_preview import LeagueFetcher

SEASON = "2025-26"
NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


def board(*games):
    return {"scoreboard": {"games": [{"gameId": gid, "gameStatus": st} for gid, st in games]}}


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "r.db")
    c.execute("INSERT INTO team_games VALUES (1610612747, '0022600001', '2026-27', 'LAL', 'HOU', '2026-10-20', 1, 'W', 100, 5)")
    c.commit()
    return c


def mark_last(conn, when):
    with conn:
        conn.execute("INSERT OR REPLACE INTO sync VALUES (0, ?, ?)", (refresh.LAST_KIND, when.isoformat()))


def test_finished_games_ignore_unfinished_and_preseason():
    sb = board(("0022600001", 3), ("0022600002", 2), ("0022600003", 1), ("0012600004", 3), ("0032600005", 3), ("0042600006", 3))
    assert refresh.finished_game_ids(sb) == ["0022600001", "0042600006"]


def test_unknown_finals_compares_with_team_games(conn):
    assert refresh.unknown_finals(conn, board(("0022600001", 3), ("0022600002", 3))) == ["0022600002"]
    assert refresh.unknown_finals(conn, board(("0022600001", 3))) == []
    assert refresh.unknown_finals(conn, board()) == []


def test_decision_matrix(conn):
    known, new = board(("0022600001", 3)), board(("0022600001", 3), ("0022600002", 3))

    def ok(sb, **kw):
        return refresh.should_refresh(conn, sb, now=NOW, **kw)

    assert ok(known) == (True, "never refreshed")
    mark_last(conn, NOW - timedelta(minutes=10))
    go, why = ok(new)
    assert not go and "10 min ago" in why  # a new final still waits out the minimum gap
    mark_last(conn, NOW - timedelta(minutes=45))
    go, why = ok(new)
    assert go and "0022600002" in why  # a game the database doesn't have
    assert ok(known) == (False, "up to date")
    assert ok(None) == (False, "up to date")  # scoreboard unavailable: nothing to act on yet
    mark_last(conn, NOW - timedelta(hours=26))
    go, why = ok(known)
    assert go and "26 h ago" in why  # daily catch-up even with nothing new
    assert ok(known, force=True) == (True, "forced")
    mark_last(conn, NOW - timedelta(minutes=1))
    assert ok(known, force=True)[0]  # force beats the minimum gap


class PropsFetcher(LeagueFetcher):
    """Every league-wide call served from saved responses; remembers what was asked."""

    def __init__(self, fixtures_dir):
        super().__init__(fixtures_dir / "teams")
        self.stats = fixtures_dir / "stats"

    def _s(self, name, tag):
        self.calls.append(tag)
        return json.loads((self.stats / name).read_text(encoding="utf-8"))

    def league_game_logs(self, season, measure="Base", period=0):
        name = "pgl_usage.json" if measure == "Usage" else "pgl_q2.json" if period == 2 else "pgl_q1.json"  # q1 doubles as the base log
        return self._s(name, f"logs:{measure}:{period}")

    def player_zones(self, season):
        return self._s("player_shotloc.json", "zones")

    def team_zones_def(self, season):
        return self._s("team_shotloc_opp.json", "team_zones")

    def player_shot_types(self, season, general_range):
        return self._s("player_ptshot_Catch_and_Shoot.json", "shot_types")

    def team_shot_types_def(self, season, general_range):
        return self._s("opp_pt_shot_cs.json", "team_shot_types")

    def synergy(self, season, play_type, who):
        return self._s("synergy_iso_player.json" if who == "P" else "synergy_iso_team_def.json", f"synergy:{who}")

    def player_index(self, season):
        return self._s("player_index.json", "index")


@pytest.fixture
def schedule(fixtures_dir):
    fx = json.loads((fixtures_dir / "scheduleLeagueV2_1.json").read_text(encoding="utf-8"))
    return lambda: fx


def test_run_refresh_refetches_game_data_but_not_slow_data(conn, fixtures_dir, schedule):
    f = PropsFetcher(fixtures_dir)
    first = refresh.run_refresh(conn, f, seasons=[SEASON], fetch_schedule=schedule)
    assert first["schedule_games"] > 1200 and "logs" in first["props"][SEASON] and "player_zones" in first["props"][SEASON]
    assert refresh.last_refresh(conn) is not None
    assert conn.execute("SELECT COUNT(*) FROM players WHERE position IS NOT NULL").fetchone()[0] >= 70  # player index applied

    f.calls.clear()
    second = refresh.run_refresh(conn, f, seasons=[SEASON], fetch_schedule=schedule)
    assert "logs" in second["props"][SEASON] and "standings" in f.calls and "teamgames" in f.calls  # game-driven: refetched
    assert not {"zones", "team_zones", "shot_types", "index"} & set(f.calls)  # slow-moving: still fresh
    assert not any(c.startswith("synergy") for c in f.calls)
    assert "player_zones" not in second["props"][SEASON]


def test_refresh_once_skips_then_runs_on_new_final(conn, fixtures_dir, schedule):
    f = PropsFetcher(fixtures_dir)
    kw = dict(seasons=[SEASON], fetch_schedule=schedule)
    known = lambda: board(("0022600001", 3))  # noqa: E731  (already in team_games)
    assert refresh.refresh_once(conn, f, get_scoreboard=known, **kw)  # never refreshed -> runs
    assert refresh.refresh_once(conn, f, get_scoreboard=known, **kw) is None  # minimum gap
    mark_last(conn, datetime.now(timezone.utc) - timedelta(hours=1))
    assert refresh.refresh_once(conn, f, get_scoreboard=known, **kw) is None  # nothing new
    new = lambda: board(("0022600099", 3))  # noqa: E731  (a final game the database has never seen)
    assert refresh.refresh_once(conn, f, get_scoreboard=new, **kw)


def test_scoreboard_failure_does_not_block_the_daily_catch_up(conn, fixtures_dir, schedule):
    def broken():
        raise ConnectionError("cdn down")

    f = PropsFetcher(fixtures_dir)
    kw = dict(seasons=[SEASON], fetch_schedule=schedule, get_scoreboard=broken)
    mark_last(conn, datetime.now(timezone.utc) - timedelta(hours=30))
    assert refresh.refresh_once(conn, f, **kw)  # the daily rule still fires
    assert refresh.refresh_once(conn, f, **kw) is None


def test_cli_main_runs_a_pass_and_writes_a_log(tmp_path, fixtures_dir, schedule, monkeypatch):
    monkeypatch.setattr(refresh, "fetch_scoreboard", lambda: board())
    monkeypatch.setattr(ingest, "fetch_schedule_json", schedule)
    monkeypatch.setattr(refresh, "current_season", lambda: SEASON)
    log = tmp_path / "refresh.log"
    args = ["--db", str(tmp_path / "cli.db"), "--log-file", str(log)]
    assert refresh.main(args, fetcher=PropsFetcher(fixtures_dir)) == 0
    assert "refreshing: never refreshed" in log.read_text(encoding="utf-8")
    assert refresh.main(args, fetcher=PropsFetcher(fixtures_dir)) == 0
    assert "skip: refreshed" in log.read_text(encoding="utf-8")


# ------------------------------------------------------- injuries + lineups on every pass

def files(fixtures_dir):
    """A fake NBA site serving the saved injury index/PDFs and today's lineups file."""
    def getter(url):
        if "official.nba.com" in url:
            return (fixtures_dir / "injury" / "index.html").read_bytes()
        if "Injury-Report" in url:
            p = fixtures_dir / "injury" / url.rsplit("/", 1)[1]
            return p.read_bytes() if p.exists() else None
        if "20261023" in url:
            return (fixtures_dir / "lineups" / "00_daily_lineups_20261023.json").read_bytes()
        return None
    return getter


@pytest.mark.real_availability
def test_availability_stores_both_feeds(conn, fixtures_dir, monkeypatch):
    monkeypatch.setattr(refresh.webget, "fetch", files(fixtures_dir))
    monkeypatch.setattr(refresh.injuries.webget, "fetch", files(fixtures_dir))
    monkeypatch.setattr(refresh.lineups, "et_today", lambda now=None: __import__("datetime").date(2026, 10, 23))
    monkeypatch.setattr(refresh.lineups, "fetch_day", lambda day, getter=None: refresh.lineups.json.loads(files(fixtures_dir)(f"x_{day:%Y%m%d}").decode()) if day.day == 23 else None)
    out = refresh.refresh_availability(conn)
    assert out["injuries"]["new"] == 1 and out["injuries"]["entries"] == 85
    assert out["lineup_changes"] == 24
    again = refresh.refresh_availability(conn)
    assert again["injuries"]["new"] == 0 and again["lineup_changes"] == 0  # nothing new, nothing written


@pytest.mark.real_availability
def test_one_broken_feed_does_not_stop_the_other(conn, fixtures_dir, monkeypatch):
    def boom(*a, **k):
        raise ConnectionError("nba is down")
    monkeypatch.setattr(refresh.injuries, "sync_injuries", boom)
    monkeypatch.setattr(refresh.lineups, "poll", lambda c: [{"x": 1}, {"y": 2}])
    out = refresh.refresh_availability(conn)
    assert "nba is down" in out["injuries_error"] and out["lineup_changes"] == 2


def test_every_pass_updates_availability_even_when_the_heavy_refresh_is_skipped(conn, fixtures_dir, schedule):
    calls = []
    mark_last(conn, datetime.now(timezone.utc) - timedelta(minutes=5))  # inside the minimum gap -> heavy refresh skipped
    res = refresh.refresh_once(conn, PropsFetcher(fixtures_dir), seasons=[SEASON], fetch_schedule=schedule, get_scoreboard=lambda: board(),
                               availability=lambda c: calls.append(1) or {})
    assert res is None and calls == [1]
    assert conn.execute("SELECT last_ok FROM source_checks WHERE source='pass'").fetchone()[0]  # the scheduler heartbeat is recorded on every pass
