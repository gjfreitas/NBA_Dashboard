from datetime import datetime, timedelta, timezone

import httpx
import pytest

from nbadash import db, injuries
from nbadash.app import create_app
from nbadash.injury_changes import recent_changes
from nbadash.sources import ReplaySource

NOW = datetime(2026, 10, 23, 18, 0, tzinfo=timezone.utc)
DAY = "2026-10-23"


def add_report(c, report_id, minutes_ago, rows, pending=()):
    """rows: (team_id, abbr, player_id, name, status[, date]); pending: (team_id, abbr[, date])."""
    when = NOW - timedelta(minutes=minutes_ago)
    with c:
        c.execute("INSERT INTO injury_reports VALUES (?,?,?,?,?,?)", (report_id, when.isoformat(timespec="minutes"), when.isoformat(timespec="seconds"),
                                                                         when.isoformat(), len(rows), len(pending)))
        for i, r in enumerate(rows):
            tid, abbr, pid, name, status = r[:5]
            c.execute("INSERT INTO injuries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (report_id, i, r[5] if len(r) > 5 else DAY, "07:00 (ET)", "AAA@BBB", "G1", abbr, tid, abbr, name, pid, status, "reason"))
        for p in pending:
            c.execute("INSERT INTO injury_pending VALUES (?,?,?,?,?)", (report_id, p[2] if len(p) > 2 else DAY, "AAA@BBB", p[1], p[0]))


@pytest.fixture
def c(tmp_path):
    conn = db.connect(tmp_path / "c.db")
    with conn:
        for pid, name in ((10, "Zach Collins"), (11, "Nic Claxton"), (12, "Josh Giddey")):
            conn.execute("INSERT INTO players (id, full_name, team_abbr) VALUES (?,?,?)", (pid, name, "CHI"))
    return conn


def kinds(events):
    return sorted((e["kind"], e["player_id"], e["from_status"], e["to_status"]) for e in events)


def test_status_moves_and_adds_and_removals(c):
    add_report(c, "r1", 60, [(1, "CHI", 10, "Collins, Zach", "Questionable"), (1, "CHI", 11, "Claxton, Nic", "Out")])
    add_report(c, "r2", 30, [(1, "CHI", 10, "Collins, Zach", "Out"), (1, "CHI", 12, "Giddey, Josh", "Probable")])
    events = recent_changes(c, 24, NOW)
    assert kinds(events) == [("added", 12, None, "Probable"), ("removed", 11, "Out", None), ("worsened", 10, "Questionable", "Out")]
    assert {e["report_id"] for e in events} == {"r2"}
    add_report(c, "r3", 10, [(1, "CHI", 10, "Collins, Zach", "Probable"), (1, "CHI", 12, "Giddey, Josh", "Probable")])
    later = recent_changes(c, 24, NOW)
    assert later[0]["kind"] == "improved" and later[0]["report_id"] == "r3"  # newest report first
    assert len(later) == 4  # r3 only moved Collins; the removed/added events from r2 are still in the window


def test_a_teams_first_filing_is_not_news(c):
    add_report(c, "r1", 60, [(1, "CHI", 10, "Collins, Zach", "Out")], pending=[(2, "MIL")])
    add_report(c, "r2", 30, [(1, "CHI", 10, "Collins, Zach", "Out"), (2, "MIL", 13, "Someone, Else", "Questionable")])
    assert recent_changes(c, 24, NOW) == []  # MIL went from "not yet submitted" to filed: those are not additions


def test_a_new_game_day_is_not_news_but_clearing_a_listed_team_is(c):
    add_report(c, "r1", 60, [(1, "CHI", 10, "Collins, Zach", "Out")])
    add_report(c, "r2", 30, [(1, "CHI", 10, "Collins, Zach", "Out", DAY), (1, "CHI", 12, "Giddey, Josh", "Out", "2026-10-24")])
    assert recent_changes(c, 24, NOW) == []
    add_report(c, "r3", 10, [(1, "CHI", 12, "Giddey, Josh", "Out", "2026-10-24")])  # Collins no longer listed for the 23rd
    assert recent_changes(c, 24, NOW) == []  # the 23rd is absent from r3 altogether (that game day is over): not "cleared"


def test_removed_only_when_the_team_is_still_covered(c):
    add_report(c, "r1", 60, [(1, "CHI", 10, "Collins, Zach", "Out"), (1, "CHI", 11, "Claxton, Nic", "Out")])
    add_report(c, "r2", 30, [(1, "CHI", 10, "Collins, Zach", "Out")], pending=[])
    assert kinds(recent_changes(c, 24, NOW)) == [("removed", 11, "Out", None)]
    add_report(c, "r3", 10, [], pending=[(1, "CHI")])  # CHI went back to "not yet submitted" for the same day: nobody was cleared
    assert kinds(recent_changes(c, 24, NOW)) == [("removed", 11, "Out", None)]


def test_window_uses_the_report_before_it_as_baseline(c):
    add_report(c, "old", 600, [(1, "CHI", 10, "Collins, Zach", "Out")])
    add_report(c, "new", 30, [(1, "CHI", 10, "Collins, Zach", "Probable")])
    assert kinds(recent_changes(c, 2, NOW)) == [("improved", 10, "Out", "Probable")]
    assert recent_changes(c, 0.1, NOW) == []  # nothing newer than the window starts with: only one report, nothing to compare


def test_unmatched_players_are_compared_by_normalised_name(c):
    add_report(c, "r1", 60, [(1, "CHI", None, "Hawkins, Jordan", "Out")])
    add_report(c, "r2", 30, [(1, "CHI", None, "Hawkins, Jordan", "Questionable")])
    assert [(e["kind"], e["player_id"]) for e in recent_changes(c, 24, NOW)] == [("improved", None)]


def test_no_reports_or_one_report(c):
    assert recent_changes(c, 24, NOW) == []
    add_report(c, "r1", 60, [(1, "CHI", 10, "Collins, Zach", "Out")])
    assert recent_changes(c, 24, NOW) == []


# ---------------------------------------------------------------- API + backfill

@pytest.fixture
async def client(tmp_path, fixtures_dir):
    c = db.connect(tmp_path / "d.db")
    with c:
        c.execute("INSERT INTO players (id, full_name, team_abbr) VALUES (10, 'Zach Collins', 'CHI')")
    now = datetime.now(timezone.utc)
    for rid, mins, status in (("a", 50, "Questionable"), ("b", 20, "Out")):
        when = now - timedelta(minutes=mins)
        with c:
            c.execute("INSERT INTO injury_reports VALUES (?,?,?,?,1,0)", (rid, when.isoformat(timespec="minutes"), when.isoformat(timespec="seconds"), when.isoformat()))
            c.execute("INSERT INTO injuries VALUES (?,0,?,?,?,?,?,1,?,?,10,?,?)", (rid, DAY, "07:00 (ET)", "AAA@BBB", "G1", "Chicago Bulls", "CHI", "Collins, Zach", status, "x"))
    app = create_app(ReplaySource(fixtures_dir), db_path=str(tmp_path / "d.db"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as cl:
        yield cl


async def test_changes_endpoint(client):
    d = (await client.get("/api/injuries/changes")).json()
    assert d["reports_compared"] == 2
    [ch] = d["changes"]
    assert (ch["kind"], ch["name"], ch["from_status"], ch["to_status"], ch["team_abbr"]) == ("worsened", "Zach Collins", "Questionable", "Out", "CHI")
    assert (await client.get("/api/injuries/changes", params={"team_id": 99})).json()["changes"] == []
    assert (await client.get("/api/injuries/changes", params={"game_id": "G1"})).json()["changes"] != []
    assert (await client.get("/api/injuries/changes", params={"hours": 0})).status_code == 422


def test_backfill_stores_the_missing_reports_in_the_window(tmp_path, fixtures_dir):
    conn = db.connect(tmp_path / "e.db")
    index = (fixtures_dir / "injury" / "index.html").read_bytes()
    have = {p.name: p.read_bytes() for p in (fixtures_dir / "injury").glob("*.pdf")}
    asked = []

    def getter(url):
        asked.append(url)
        return index if "official.nba.com" in url else have.get(url.rsplit("/", 1)[1])

    res = injuries.backfill_injuries(conn, getter, hours=24)
    stored = conn.execute("SELECT COUNT(*) FROM injury_reports").fetchone()[0]
    assert res["stored"] == stored == len(have)  # only two PDFs are saved as fixtures; the other listed ones were not downloadable
    assert res["skipped"] == 33 - len(have)
    asked.clear()
    assert injuries.backfill_injuries(conn, getter, hours=24)["stored"] == 0  # reports we already have are not fetched again
    assert not [u for u in asked if u.endswith(tuple(have))]


def test_a_new_report_pulls_in_the_ones_missed_while_asleep(tmp_path, fixtures_dir):
    conn = db.connect(tmp_path / "f.db")
    index = (fixtures_dir / "injury" / "index.html").read_bytes()
    pdfs = {p.name: p.read_bytes() for p in (fixtures_dir / "injury").glob("*.pdf")}
    getter = lambda url: index if "official.nba.com" in url else pdfs.get(url.rsplit("/", 1)[1])  # noqa: E731
    plain = injuries.sync_injuries(conn, getter)
    assert plain["new"] == 1 and "caught_up" not in plain and conn.execute("SELECT COUNT(*) FROM injury_reports").fetchone()[0] == 1
    for hours, expected in ((3, 0), (5, 1)):  # the saved 04:00 AM report is 4 hours before the newest (08:00 AM)
        c2 = db.connect(tmp_path / f"g{hours}.db")
        res = injuries.sync_injuries(c2, getter, catch_up_hours=hours)
        assert res["new"] == 1 and res["caught_up"] == expected
        assert c2.execute("SELECT COUNT(*) FROM injury_reports").fetchone()[0] == 1 + expected
