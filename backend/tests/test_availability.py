import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone

import pytest

from nbadash import availability_api as availability_api_module
from nbadash import db, ingest, injuries, lineups

NEWEST = "Injury-Report_2026-10-23_08_00AM.pdf"
EARLIER = "Injury-Report_2026-10-23_04_00AM.pdf"


def pdf(fixtures_dir, name=NEWEST):
    return (fixtures_dir / "injury" / name).read_bytes()


@pytest.fixture
def report(fixtures_dir):
    return injuries.parse_report(pdf(fixtures_dir))


# ---------------------------------------------------------------- the PDF parser

def test_report_header_and_counts(report):
    assert report.published_at == datetime(2026, 10, 23, 8, 0)
    # counted independently with a line-based regex on the same PDF: 85 players; 16 teams had not filed yet
    assert len(report.entries) == 85 and len(report.pending) == 16
    assert Counter(e.status for e in report.entries) == {"Out": 51, "Questionable": 20, "Probable": 7, "Available": 4, "Doubtful": 3}
    assert all(e.status and e.reason and e.team_name and e.matchup and e.game_date for e in report.entries)


def by_name(report, name):
    return next(e for e in report.entries if e.player_name == name)


def test_game_team_context_is_forward_filled(report):
    awaka, collins = by_name(report, "Awaka, Tobe"), by_name(report, "Collins, Zach")
    for e in (awaka, collins):
        assert (e.game_date, e.game_time, e.matchup, e.team_name) == ("2026-10-23", "04:00 (ET)", "CHI@MIL", "Chicago Bulls")
    # printed without a time because it tips at the same time as the game above: the time carries over
    lively = by_name(report, "Lively II, Dereck")
    assert (lively.matchup, lively.team_name, lively.game_time) == ("DAL@IND", "Dallas Mavericks", "07:00 (ET)")
    # the second team in a game starts a new block
    assert by_name(report, "Knueppel, Kon").team_name == "Charlotte Hornets"
    assert by_name(report, "Biberovic, Tarik").team_name == "Dallas Mavericks"


def test_wrapped_reasons_are_centred_on_their_player(report):
    # Collins' two reason lines sit ABOVE and BELOW his name, wedged between Claxton's row and his own
    assert by_name(report, "Collins, Zach").reason == "Injury/Illness - Right Quadriceps Strain"
    assert by_name(report, "Claxton, Nic").reason == "Injury/Illness - Left Hamstring Strain"  # single line, not stolen by Collins
    assert by_name(report, "Thiero, Adou").reason == "Injury/Illness - Left Knee Effusion / Swelling"
    assert by_name(report, "Butler III, Jimmy").reason == "Injury/Illness - Right ACL Repair / Surgery"
    assert by_name(report, "Porzingis, Kristaps").reason == "Not With Team"  # no "Injury/Illness" prefix
    # a wrapped reason on the first row after a page break
    assert by_name(report, "Howard, Jett").reason == "Injury/Illness - Right Calf Tightness / Soreness"
    assert by_name(report, "Dennis, RayJ").reason == "G League - Two-Way"


def test_pending_teams_are_listed_with_their_game(report):
    miami = report.pending[0]
    assert (miami.game_date, miami.matchup, miami.team_name) == ("2026-10-24", "MIA@CHA", "Miami Heat")
    assert {p.team_name for p in report.pending} >= {"Charlotte Hornets", "Phoenix Suns", "Denver Nuggets"}
    assert len({(p.matchup, p.team_name) for p in report.pending}) == 16


def test_earlier_report_parses_too(fixtures_dir):
    r = injuries.parse_report(pdf(fixtures_dir, EARLIER))
    assert r.published_at == datetime(2026, 10, 23, 4, 0) and len(r.entries) == 85


def test_not_a_report_is_rejected():
    with pytest.raises(Exception):
        injuries.parse_report(b"%PDF-1.4 not really")


# ------------------------------------------------------------ names, teams, games

@pytest.mark.parametrize("a,b", [
    ("Lively II, Dereck", "Dereck Lively II"), ("Butler III, Jimmy", "Jimmy Butler"), ("Jaquez Jr., Jaime", "Jaime Jaquez Jr."),
    ("Gilgeous-Alexander, Shai", "Shai Gilgeous-Alexander"), ("Dončić, Luka", "Luka Doncic"), ("Dennis, RayJ", "RayJ Dennis"),
    ("Nembhard  Jr., Andrew", "Andrew Nembhard"),
])
def test_name_normalisation(a, b):
    assert injuries.norm_name(injuries.flip(a)) == injuries.norm_name(b)


def test_distinct_players_stay_distinct():
    assert injuries.norm_name("Andrew Nembhard") != injuries.norm_name("Ryan Nembhard")
    assert injuries.flip("Smith, John") == "John Smith" and injuries.flip("John Smith") == "John Smith"


class _FrozenDatetime(datetime):
    """The saved injury report is from 2026-10-23: age it from a fixed moment, or these tests fail once it is more than 36 hours old."""

    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 23, 14, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch):
    monkeypatch.setattr(availability_api_module, "datetime", _FrozenDatetime)


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "a.db")
    with c:
        for tid, abbr, city, name in ((1, "CHI", "Chicago", "Bulls"), (2, "MIL", "Milwaukee", "Bucks"), (3, "DAL", "Dallas", "Mavericks"), (4, "IND", "Indiana", "Pacers")):
            c.execute("INSERT INTO teams (id, abbr, city, name) VALUES (?,?,?,?)", (tid, abbr, city, name))
        c.execute("INSERT INTO schedule (game_id, season, game_date, status, home_id, away_id, home_abbr, away_abbr) VALUES ('G1','2026-27','2026-10-23',1,2,1,'MIL','CHI')")
        c.execute("INSERT INTO schedule (game_id, season, game_date, status, home_id, away_id, home_abbr, away_abbr) VALUES ('G2','2026-27','2026-10-23',1,4,3,'IND','DAL')")
        for pid, name, team in ((10, "Zach Collins", "CHI"), (11, "Nic Claxton", "CHI"), (12, "Dereck Lively II", "DAL"), (13, "Tobe Awaka", "CHI"),
                                (14, "Jordan Hawkins", "CHI"), (15, "Jordan Hawkins", "DAL")):  # two players share a name on different teams
            c.execute("INSERT INTO players (id, full_name, team_abbr) VALUES (?,?,?)", (pid, name, team))
    return c


def test_resolve_matches_team_game_and_player(conn, report):
    collins = injuries.resolve(conn, by_name(report, "Collins, Zach"))
    assert collins == {"team_id": 1, "team_abbr": "CHI", "game_id": "G1", "player_id": 10}
    lively = injuries.resolve(conn, by_name(report, "Lively II, Dereck"))
    assert (lively["team_abbr"], lively["game_id"], lively["player_id"]) == ("DAL", "G2", 12)  # suffix on one side only
    # same name on two teams: the team on the report decides
    hawkins = injuries.resolve(conn, by_name(report, "Hawkins, Jordan"))
    assert hawkins["player_id"] == 14


def test_unknown_player_stays_unmatched_but_keeps_team_and_game(conn, report):
    e = injuries.Entry("2026-10-23", "04:00 (ET)", "CHI@MIL", "Chicago Bulls", "Nobody, Made Up", "Out", "x")
    assert injuries.resolve(conn, e) == {"team_id": 1, "team_abbr": "CHI", "game_id": "G1", "player_id": None}


def test_ambiguous_name_without_a_team_is_not_guessed(conn):
    e = injuries.Entry("2026-10-23", None, None, None, "Hawkins, Jordan", "Out", "x")  # two Jordan Hawkins, no team to choose
    assert injuries.resolve(conn, e)["player_id"] is None


def test_store_report_keeps_unmatched_players(conn, report):
    n = injuries.store_report(conn, "2026-10-23_08_00AM", report)
    assert n == 85
    assert conn.execute("SELECT COUNT(*) FROM injuries").fetchone()[0] == 85
    assert conn.execute("SELECT COUNT(*) FROM injuries WHERE player_id IS NOT NULL").fetchone()[0] < 85  # only the few seeded players match
    row = conn.execute("SELECT * FROM injury_reports").fetchone()
    assert (row["entries"], row["pending"], row["published_at"]) == (85, 16, "2026-10-23T08:00")
    assert row["published_utc"] == "2026-10-23T12:00:00+00:00"  # 8:00 ET (EDT) = 12:00 UTC
    # storing the same report again replaces, it doesn't duplicate
    injuries.store_report(conn, "2026-10-23_08_00AM", report)
    assert conn.execute("SELECT COUNT(*) FROM injuries").fetchone()[0] == 85


# ----------------------------------------------------------------- the index + sync

@pytest.fixture
def web(fixtures_dir):
    """A fake NBA site: the saved index page and the two saved PDFs. Records every URL asked for."""
    index = (fixtures_dir / "injury" / "index.html").read_text(encoding="utf-8")
    asked: list[str] = []
    files = {NEWEST: pdf(fixtures_dir), EARLIER: pdf(fixtures_dir, EARLIER)}

    def getter(url):
        asked.append(url)
        if "official.nba.com" in url:
            return index.encode()
        return files.get(url.rsplit("/", 1)[1])

    getter.asked, getter.index = asked, index
    return getter


def test_index_lists_reports_oldest_first(web):
    reps = injuries.list_reports(web.index)
    assert len(reps) == 33 and reps[0][0] == "2026-10-23_12_00AM" and reps[-1][0] == "2026-10-23_08_00AM"
    assert reps == sorted(reps, key=lambda r: r[2])  # 12:xx AM sorts first although "12" > "08" alphabetically
    assert {(b[2] - a[2]) for a, b in zip(reps, reps[1:])} == {timedelta(minutes=15)}


def test_sync_stores_newest_once_and_is_cheap_when_unchanged(conn, web):
    first = injuries.sync_injuries(conn, web)
    assert first["new"] == 1 and first["latest"] == "2026-10-23_08_00AM" and first["entries"] == 85
    web.asked.clear()
    again = injuries.sync_injuries(conn, web)
    assert again["new"] == 0 and len(web.asked) == 1 and "official.nba.com" in web.asked[0]  # only the index page, no PDF download


def test_sync_picks_up_a_newer_report(conn, web, fixtures_dir):
    injuries.sync_injuries(conn, web)
    newer = web.index.replace("Injury-Report_2026-10-23_08_00AM.pdf", "Injury-Report_2026-10-23_08_15AM.pdf")
    web2 = lambda url: newer.encode() if "official.nba.com" in url else (pdf(fixtures_dir, EARLIER) if "08_15AM" in url else web(url))  # noqa: E731
    res = injuries.sync_injuries(conn, web2)
    assert res["new"] == 1 and res["latest"].endswith("08_15AM")
    assert [r["report_id"] for r in conn.execute("SELECT report_id FROM injury_reports ORDER BY published_utc")] == ["2026-10-23_08_00AM", "2026-10-23_08_15AM"]
    assert injuries.latest_report(conn)["report_id"] == "2026-10-23_08_15AM"


def test_sync_survives_missing_pdf_and_empty_index(conn, web):
    assert injuries.sync_injuries(conn, lambda url: web.index.encode() if "official.nba.com" in url else None)["new"] == 0
    assert injuries.sync_injuries(conn, lambda url: None)["new"] == 0
    assert conn.execute("SELECT COUNT(*) FROM injury_reports").fetchone()[0] == 0


# ------------------------------------------------------------------------ lineups

def lineup_file(fixtures_dir, day="20261023"):
    return json.loads((fixtures_dir / "lineups" / f"00_daily_lineups_{day}.json").read_text(encoding="utf-8"))


def test_first_store_records_one_event_per_team(conn, fixtures_dir):
    data = lineup_file(fixtures_dir)
    changes = lineups.store_lineups(conn, data, "2026-10-23T12:00:00+00:00")
    assert len(changes) == 24 and {c["status"] for c in changes} == {"Expected"}
    assert conn.execute("SELECT COUNT(*) FROM lineups WHERE starter=1").fetchone()[0] == 120  # 24 teams x 5
    assert conn.execute("SELECT COUNT(*) FROM lineup_events").fetchone()[0] == 24
    # nothing changed -> nothing new
    assert lineups.store_lineups(conn, data, "2026-10-23T12:01:00+00:00") == []
    assert conn.execute("SELECT COUNT(*) FROM lineup_events").fetchone()[0] == 24


def test_confirmation_and_a_changed_starter_are_events(conn, fixtures_dir):
    data = lineup_file(fixtures_dir)
    lineups.store_lineups(conn, data, "2026-10-23T12:00:00+00:00")
    game = data["games"][0]
    team = game["homeTeam"]
    for p in team["players"]:
        p["lineupStatus"] = "Confirmed"
    swapped = dict(team["players"][0], personId=999999, playerName="Late Replacement")  # a different starter than expected
    team["players"][0] = swapped
    changes = lineups.store_lineups(conn, data, "2026-10-23T19:40:00+00:00")
    assert len(changes) == 1  # only that team changed
    ch = changes[0]
    assert (ch["status"], ch["previous"], ch["game_id"]) == ("Confirmed", "Expected", game["gameId"]) and 999999 in ch["starters"]
    assert conn.execute("SELECT name FROM lineups WHERE game_id=? AND player_id=999999", (game["gameId"],)).fetchone()["name"] == "Late Replacement"
    # the replaced player is gone from the stored lineup
    assert conn.execute("SELECT COUNT(*) FROM lineups WHERE game_id=? AND team_id=?", (game["gameId"], team["teamId"])).fetchone()[0] == 5


def test_timing_report_measures_minutes_before_tip(conn, fixtures_dir):
    data = lineup_file(fixtures_dir)
    game = data["games"][0]
    tip = datetime(2026, 10, 23, 20, 0, tzinfo=timezone.utc)
    with conn:
        conn.execute("INSERT INTO schedule (game_id, season, game_date, start_utc, status, home_id, away_id) VALUES (?,?,?,?,?,?,?)",
                     (game["gameId"], "2026-27", "2026-10-23", tip.isoformat().replace("+00:00", "Z"), 1, game["homeTeam"]["teamId"], game["awayTeam"]["teamId"]))
    lineups.store_lineups(conn, data, (tip - timedelta(hours=8)).isoformat())
    for p in game["homeTeam"]["players"]:
        p["lineupStatus"] = "Confirmed"
    lineups.store_lineups(conn, data, (tip - timedelta(minutes=30)).isoformat())
    rep = {(r["game_id"], r["team"]): r for r in lineups.timing_report(conn)}
    home = next(r for r in rep.values() if r["game_id"] == game["gameId"] and r["confirmed_at"])
    assert home["first_status"] == "Expected" and home["first_seen_min_before_tip"] == 480
    assert home["confirmed_at_min_before_tip"] == 30 and home["five_changed"] is False
    away = next(r for r in rep.values() if r["game_id"] == game["gameId"] and not r["confirmed_at"])
    assert away["first_seen_min_before_tip"] == 480 and "confirmed_at_min_before_tip" not in away


def test_fetch_day_handles_missing_files_and_et_dates():
    seen = []

    def getter(url):
        seen.append(url)
        return None if "20261024" in url else b'{"games": []}'

    assert lineups.fetch_day(date(2026, 10, 24), getter) is None  # tomorrow's file doesn't exist yet
    assert lineups.fetch_day(date(2026, 10, 23), getter) == {"games": []}
    assert seen[0].endswith("00_daily_lineups_20261024.json")
    # 03:30 UTC on the 24th is still the 23rd in New York (the late slate)
    assert lineups.et_today(datetime(2026, 10, 24, 3, 30, tzinfo=timezone.utc)) == date(2026, 10, 23)
    assert lineups.et_today(datetime(2026, 10, 24, 5, 0, tzinfo=timezone.utc)) == date(2026, 10, 24)


def test_poll_fetches_today_and_tomorrow_only(conn, fixtures_dir):
    asked = []

    def getter(url):
        asked.append(url.rsplit("_", 1)[1])
        return (fixtures_dir / "lineups" / "00_daily_lineups_20261023.json").read_bytes() if "20261023" in url else None

    lineups.poll(conn, now=datetime(2026, 10, 23, 14, 0, tzinfo=timezone.utc), getter=getter)
    assert asked == ["20261023.json", "20261024.json"]


# --------------------------------------------------------------------------- API

import httpx  # noqa: E402

from nbadash import availability_api  # noqa: E402
from nbadash.app import create_app  # noqa: E402
from nbadash.sources import ReplaySource  # noqa: E402

CHI, MIL, GAME = 1610612741, 1610612749, "0022600099"
GIDDEY, CLAXTON = 1630581, 1629651  # Giddey is one of Chicago's expected starters in the saved lineups file


@pytest.fixture
async def api(tmp_path, fixtures_dir):
    c = db.connect(tmp_path / "b.db")
    with c:
        c.execute("INSERT INTO teams (id, abbr, city, name) VALUES (?, 'CHI', 'Chicago', 'Bulls')", (CHI,))
        c.execute("INSERT INTO teams (id, abbr, city, name) VALUES (?, 'MIL', 'Milwaukee', 'Bucks')", (MIL,))
        c.execute("INSERT INTO schedule (game_id, season, game_date, start_utc, status, home_id, away_id, home_abbr, away_abbr) "
                  "VALUES (?, '2026-27', '2026-10-23', '2026-10-23T20:00:00Z', 1, ?, ?, 'MIL', 'CHI')", (GAME, MIL, CHI))
        c.execute("INSERT INTO players (id, full_name, team_abbr) VALUES (?, 'Josh Giddey', 'CHI')", (GIDDEY,))
        c.execute("INSERT INTO players (id, full_name, team_abbr) VALUES (?, 'Nic Claxton', 'CHI')", (CLAXTON,))
    injuries.sync_injuries(c, lambda url: (fixtures_dir / "injury" / "index.html").read_bytes() if "official.nba.com" in url
                           else (fixtures_dir / "injury" / url.rsplit("/", 1)[1]).read_bytes() if (fixtures_dir / "injury" / url.rsplit("/", 1)[1]).exists() else None)
    lineups.store_lineups(c, lineup_file(fixtures_dir), "2026-10-23T12:00:00+00:00")
    app = create_app(ReplaySource(fixtures_dir), db_path=str(tmp_path / "b.db"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        yield client, c


async def test_injuries_endpoint(api):
    client, _ = api
    d = (await client.get("/api/injuries")).json()
    assert d["report"]["report_id"] == "2026-10-23_08_00AM" and d["report"]["published_at"] == "2026-10-23T08:00"
    assert isinstance(d["report"]["stale"], bool) and d["report"]["age_minutes"] >= 0
    assert len(d["entries"]) == 85 and len(d["pending"]) == 16
    chi = [e for e in d["entries"] if e["team_abbr"] == "CHI"]
    assert [e["name"] for e in chi][0] == "Nic Claxton"  # most severe (Out) first within the team; matched players use our spelling
    assert {e["name"] for e in chi} == {"Nic Claxton", "Josh Giddey", "Tobe Awaka", "Zach Collins", "Jordan Hawkins", "Dailyn Swain"}  # unmatched ones are flipped to "First Last"
    assert next(e for e in chi if e["name"] == "Josh Giddey")["player_id"] == GIDDEY
    assert next(e for e in chi if e["name"] == "Zach Collins")["player_id"] is None
    keys = [(e["game_date"] or "", e["game_id"] or "") for e in d["entries"]]
    assert keys == sorted(keys)  # grouped by game


async def test_injuries_filters(api):
    client, _ = api
    out = (await client.get("/api/injuries", params={"status": "Out"})).json()
    assert len(out["entries"]) == 51 and {e["status"] for e in out["entries"]} == {"Out"}
    team = (await client.get("/api/injuries", params={"team_id": CHI})).json()
    assert len(team["entries"]) == 6 and {e["team_id"] for e in team["entries"]} == {CHI}
    assert (await client.get("/api/injuries", params={"status": "Bogus"})).status_code == 422


async def test_injuries_when_nothing_is_stored(tmp_path, fixtures_dir):
    db.connect(tmp_path / "e.db").close()
    app = create_app(ReplaySource(fixtures_dir), db_path=str(tmp_path / "e.db"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        assert (await client.get("/api/injuries")).json() == {"report": None, "entries": [], "pending": [], "espn": [], "espn_meta": None}


async def test_game_availability(api):
    client, conn = api
    d = (await client.get(f"/api/games/{GAME}/availability")).json()
    away, home = d["away"], d["home"]
    assert (away["abbr"], home["abbr"]) == ("CHI", "MIL") and d["report"]["report_id"] == "2026-10-23_08_00AM"
    assert away["lineup_status"] == "Expected" and len(away["starters"]) == 5 and len(home["starters"]) == 5
    pos = [s["position"] for s in away["starters"]]
    assert pos == sorted(pos, key=lambda p: availability_api.POSITION_ORDER.get(p, 9))  # PG, SG, SF, PF, C
    giddey = next(s for s in away["starters"] if s["player_id"] == GIDDEY)
    assert (giddey["injury_status"], giddey["injury_reason"]) == ("Probable", "Injury/Illness - Left Wrist Sprain")  # a starter on the report
    assert all(s["injury_status"] is None for s in away["starters"] if s["player_id"] != GIDDEY)
    assert [i["status"] for i in away["injuries"]][0] == "Out" and len(away["injuries"]) == 6
    assert away["report_pending"] is False
    with conn:
        conn.execute("INSERT INTO injury_pending VALUES ('2026-10-23_08_00AM', '2026-10-23', 'CHI@MIL', 'Milwaukee Bucks', ?)", (MIL,))
    assert (await client.get(f"/api/games/{GAME}/availability")).json()["home"]["report_pending"] is True
    assert (await client.get("/api/games/0029999999/availability")).status_code == 404


async def test_game_without_a_lineup_yet(api):
    client, conn = api
    with conn:
        conn.execute("DELETE FROM lineups")
    d = (await client.get(f"/api/games/{GAME}/availability")).json()
    assert d["away"]["lineup_status"] is None and d["away"]["starters"] == [] and len(d["away"]["injuries"]) == 6


# ------------------------------------------------------- how old is too old

def test_report_age_and_staleness(api_sync=None):
    from datetime import datetime, timezone
    row = {"report_id": "r", "published_at": "2026-10-23T08:00", "published_utc": "2026-10-23T12:00:00+00:00"}
    meta = lambda hours: availability_api.report_meta(row, datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc) + timedelta(hours=hours))  # noqa: E731
    assert meta(1).age_minutes == 60 and meta(1).stale is False
    assert meta(36).stale is False and meta(36.5).stale is True
    assert availability_api.report_meta(None) is None


async def test_player_injury_is_hidden_once_the_report_is_stale(api):
    _, conn = api
    published = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
    inj = availability_api.current_injury(conn, GIDDEY, now=published + timedelta(hours=3))
    assert (inj.status, inj.matchup, inj.reported_at) == ("Probable", "CHI@MIL", "2026-10-23T08:00")
    assert availability_api.current_injury(conn, GIDDEY, now=published + timedelta(hours=40)) is None  # old news is not "injured now"
    assert availability_api.current_injury(conn, 123, now=published) is None  # not on the report


# =============================================================== ESPN (secondary source)

from nbadash import espn_injuries  # noqa: E402


def espn_json(*teams, timestamp="2026-10-23T12:40:37Z"):
    """Shaped like ESPN's response. teams = (displayName, [(athlete, status, details, date), ...])."""
    return {"timestamp": timestamp, "status": "success", "injuries": [
        {"id": str(i), "displayName": name, "injuries": [
            {"id": f"{i}-{j}", "status": st, "date": date or "2026-10-23T04:00Z", "details": details,
             "athlete": {"displayName": who}, "shortComment": "Some Reporter said he is hurt.", "longComment": "Long text."}
            for j, (who, st, details, date) in enumerate(rows)]} for i, (name, rows) in enumerate(teams)]}


def test_parse_the_real_sample(fixtures_dir):
    entries, snapshot = espn_injuries.parse(json.loads((fixtures_dir / "injury" / "espn_injuries.json").read_text(encoding="utf-8")))
    assert len(entries) == 78 and snapshot == "2026-10-23T12:40:37Z"
    assert Counter(e.status for e in entries) == {"Out": 50, "Day-To-Day": 28}
    gueye = next(e for e in entries if e.player_name == "Mouhamed Gueye")
    assert (gueye.team_name, gueye.status, gueye.injury, gueye.return_date) == ("Atlanta Hawks", "Out", "Left Foot Fracture", "2026-11-20")
    assert all(e.return_date for e in entries) and not any("Not Specified" in e.injury for e in entries)


def test_injury_text_drops_vague_and_repeated_parts():
    t = espn_injuries.injury_text
    assert t({"side": "Left", "type": "Foot", "detail": "Fracture"}) == "Left Foot Fracture"
    assert t({"side": "Not Specified", "type": "Hamstring", "detail": "Not Specified"}) == "Hamstring"
    assert t({"side": "Right", "type": "Knee", "detail": "Knee"}) == "Right Knee"  # no stutter
    assert t({"type": "Illness"}) == "Illness" and t({}) == "Undisclosed" and t(None) == "Undisclosed"


def test_comments_are_never_stored(tmp_path):
    cols = {r[1] for r in db.connect(tmp_path / "c.db").execute("PRAGMA table_info(espn_injuries)")}
    assert not {c for c in cols if "comment" in c}  # ESPN's text is third-party editorial content


def seed_teams(c):
    with c:
        for tid, abbr, city, name in ((1, "LAC", "LA", "Clippers"), (2, "LAL", "Los Angeles", "Lakers"), (3, "NYK", "New York", "Knicks"), (4, "GSW", "Golden State", "Warriors")):
            c.execute("INSERT INTO teams (id, abbr, city, name) VALUES (?,?,?,?)", (tid, abbr, city, name))


def test_team_names_resolve_despite_espn_abbreviation_differences(tmp_path):
    c = db.connect(tmp_path / "t.db")
    seed_teams(c)
    r = espn_injuries.resolve_team
    assert r(c, "LA Clippers") == (1, "LAC") and r(c, "Los Angeles Lakers") == (2, "LAL")
    assert r(c, "Golden State Warriors") == (4, "GSW") and r(c, "New York Knicks") == (3, "NYK")
    assert r(c, "Los Angeles Clippers") == (1, "LAC")  # a different way of writing the same team
    assert r(c, "Springfield Isotopes") == (None, None)


def test_store_replaces_the_whole_list(tmp_path):
    c = db.connect(tmp_path / "s.db")
    seed_teams(c)
    first = [espn_injuries.EspnEntry("a", "Player One", "LA Clippers", "Out", "Knee", "2026-11-01", None),
             espn_injuries.EspnEntry("b", "Player Two", "New York Knicks", "Day-To-Day", "Ankle", "2026-10-25", None)]
    espn_injuries.store(c, first, "2026-10-23T12:00:00Z")
    assert {r["espn_id"] for r in c.execute("SELECT * FROM espn_injuries")} == {"a", "b"}
    espn_injuries.store(c, first[:1], "2026-10-23T13:00:00Z")  # Player Two recovered: he is gone from ESPN's list, so from ours
    assert [r["espn_id"] for r in c.execute("SELECT * FROM espn_injuries")] == ["a"]


def test_sync_fetches_at_most_once_an_hour_and_never_wipes_on_a_blank_answer(tmp_path, fixtures_dir):
    c = db.connect(tmp_path / "y.db")
    body = (fixtures_dir / "injury" / "espn_injuries.json").read_bytes()
    asked = []

    def get(url):
        asked.append(url)
        return body

    t0 = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
    assert espn_injuries.sync_espn(c, get, now=t0)["new"] == 1 and len(asked) == 1
    assert espn_injuries.sync_espn(c, get, now=t0 + timedelta(minutes=30)) == {"new": 0, "reason": "fresh"} and len(asked) == 1
    assert espn_injuries.sync_espn(c, get, now=t0 + timedelta(minutes=56))["new"] == 1 and len(asked) == 2
    n = c.execute("SELECT COUNT(*) FROM espn_injuries").fetchone()[0]
    assert n == 78
    blank = lambda url: json.dumps({"timestamp": "x", "injuries": []}).encode()  # noqa: E731
    assert "keeping the previous list" in espn_injuries.sync_espn(c, blank, now=t0 + timedelta(hours=3))["reason"]
    assert c.execute("SELECT COUNT(*) FROM espn_injuries").fetchone()[0] == n
    assert espn_injuries.sync_espn(c, lambda u: None, now=t0 + timedelta(hours=6))["reason"] == "unavailable"


@pytest.fixture
async def merged(api):
    """The official-report fixture plus a handcrafted ESPN list covering every dedupe case."""
    client, conn = api
    with conn:
        conn.execute("INSERT INTO players (id, full_name, team_abbr) VALUES (777, 'Patrick Williams', 'CHI')")
        conn.execute("INSERT INTO players (id, full_name, team_abbr) VALUES (778, 'Bobby Portis', 'MIL')")
    data = espn_json(
        ("Chicago Bulls", [
            ("Josh Giddey", "Day-To-Day", {"side": "Left", "type": "Wrist", "detail": "Sprain", "returnDate": "2026-10-24"}, None),  # also on the official report
            ("Zach Collins", "Day-To-Day", {"type": "Quadriceps", "detail": "Strain", "returnDate": "2026-10-25"}, None),  # official too, but not matched by id
            ("Patrick Williams", "Out", {"side": "Right", "type": "Foot", "detail": "Surgery", "returnDate": "2026-12-01"}, None)]),  # ESPN only
        ("Milwaukee Bucks", [
            ("Bobby Portis", "Day-To-Day", {"type": "Knee", "detail": "Soreness", "returnDate": "2026-10-24"}, None),
            ("Nobody Made-Up", "Out", {"type": "Back", "returnDate": "2027-01-01"}, None)]),  # unmatched, ESPN only
    )
    entries, snap = espn_injuries.parse(data)
    espn_injuries.store(conn, entries, snap, "2026-10-23T12:30:00+00:00")
    return client, conn


async def test_espn_only_players_are_listed_separately(merged):
    client, _ = merged
    d = (await client.get("/api/injuries")).json()
    names = [e["name"] for e in d["espn"]]
    assert sorted(names) == ["Bobby Portis", "Nobody Made-Up", "Patrick Williams"]
    assert "Josh Giddey" not in names  # already on the official report (matched by id)
    assert "Zach Collins" not in names  # already on it (matched by name)
    assert d["espn"][0]["status"] == "Out"  # Out before Day-To-Day
    pw = next(e for e in d["espn"] if e["name"] == "Patrick Williams")
    assert (pw["player_id"], pw["team_abbr"], pw["injury"], pw["return_date"]) == (777, "CHI", "Right Foot Surgery", "2026-12-01")
    assert next(e for e in d["espn"] if e["name"] == "Nobody Made-Up")["player_id"] is None
    assert d["espn_meta"]["fetched_at"] == "2026-10-23T12:30:00+00:00"
    assert len(d["entries"]) == 85  # the official list itself is untouched


async def test_official_entries_get_espn_return_dates(merged):
    client, _ = merged
    d = (await client.get("/api/injuries")).json()
    by = {e["name"]: e for e in d["entries"]}
    assert by["Josh Giddey"]["espn_return_date"] == "2026-10-24"  # matched by player id
    assert by["Zach Collins"]["espn_return_date"] == "2026-10-25"  # matched by normalised name
    assert by["Nic Claxton"]["espn_return_date"] is None  # ESPN does not list him


async def test_filters_apply_to_both_lists(merged):
    client, _ = merged
    chi = (await client.get("/api/injuries", params={"team_id": CHI})).json()
    assert [e["name"] for e in chi["espn"]] == ["Patrick Williams"] and len(chi["entries"]) == 6
    out = (await client.get("/api/injuries", params={"status": "Out"})).json()
    assert {e["status"] for e in out["espn"]} == {"Out"} and "Bobby Portis" not in {e["name"] for e in out["espn"]}


async def test_game_availability_lists_espn_only_players_per_team(merged):
    client, _ = merged
    d = (await client.get(f"/api/games/{GAME}/availability")).json()
    assert [e["name"] for e in d["away"]["espn_only"]] == ["Patrick Williams"]  # Chicago
    giddey = next(s for s in d["away"]["starters"] if s["player_id"] == GIDDEY)
    assert giddey["injury_status"] == "Probable"  # the official status stays the one shown


async def test_profile_shows_espn_only_when_the_official_report_does_not_cover_the_player(merged):
    _, conn = merged
    now = datetime(2026, 10, 23, 13, 0, tzinfo=timezone.utc)
    pw = availability_api.espn_injury_for(conn, 777, now)
    assert (pw.status, pw.injury, pw.return_date) == ("Out", "Right Foot Surgery", "2026-12-01")
    assert availability_api.espn_injury_for(conn, GIDDEY, now) is None  # the official report covers him
    assert availability_api.current_injury(conn, GIDDEY, now).espn_return_date == "2026-10-24"
    assert availability_api.espn_injury_for(conn, 123456, now) is None


def test_a_stale_espn_snapshot_is_ignored(tmp_path):
    c = db.connect(tmp_path / "z.db")
    seed_teams(c)
    espn_injuries.store(c, [espn_injuries.EspnEntry("a", "Player One", "LA Clippers", "Out", "Knee", "2026-11-01", None)], "t", "2026-10-23T12:00:00+00:00")
    rows, meta = availability_api.espn_state(c, datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc))
    assert len(rows) == 1 and meta.age_minutes == 24 * 60
    rows, meta = availability_api.espn_state(c, datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc))
    assert rows == [] and meta.age_minutes == 72 * 60  # too old to mean "injured now"; the age is still reported
    assert availability_api.espn_state(db.connect(tmp_path / "empty.db"))[1] is None  # never fetched


# ======================================================== scoreboard summary (key players)

async def test_summary_flags_only_top_scorers_and_counts_the_rest(api):
    client, conn = api
    with conn:
        conn.execute("UPDATE players SET team_id=? WHERE id IN (?,?)", (CHI, GIDDEY, CLAXTON))
        conn.execute("INSERT INTO league_players (player_id, season, team_id, name, gp, pts) VALUES (?, '2026-27', ?, 'Josh Giddey', 12, 19.4)", (GIDDEY, CHI))
        conn.execute("INSERT INTO league_players (player_id, season, team_id, name, gp, pts) VALUES (?, '2026-27', ?, 'Nic Claxton', 12, 3.1)", (CLAXTON, CHI))
        for i in range(5):  # five better scorers push Claxton out of the top five
            conn.execute("INSERT INTO players (id, full_name, team_id, team_abbr) VALUES (?, ?, ?, 'CHI')", (900 + i, f"Star {i}", CHI))
            conn.execute("INSERT INTO league_players (player_id, season, team_id, name, gp, pts) VALUES (?, '2026-27', ?, ?, 12, ?)", (900 + i, CHI, f"Star {i}", 30 - i))
        conn.execute("UPDATE injuries SET status='Out' WHERE player_id=?", (GIDDEY,))
    [g] = (await client.get("/api/availability/summary", params={"game_ids": f"{GAME},0029999999"})).json()  # unknown ids are skipped
    away = g["away"]
    assert g["game_id"] == GAME and away["abbr"] == "CHI" and away["lineup_status"] == "Expected"
    assert [(k["name"], k["status"]) for k in away["key_players"]] == []  # Giddey (19.4) is 6th on the team: not "key"
    assert away["others_out"] >= 2  # Claxton and Giddey are Out but not key scorers
    with conn:
        conn.execute("UPDATE league_players SET pts=40 WHERE player_id=?", (GIDDEY,))
    [g] = (await client.get("/api/availability/summary", params={"game_ids": GAME})).json()
    assert [(k["name"], k["status"], k["ppg"]) for k in g["away"]["key_players"]] == [("Josh Giddey", "Out", 40.0)]
    assert g["home"]["key_players"] == [] and g["home"]["report_pending"] is False


async def test_summary_uses_the_previous_season_while_this_one_is_young(api):
    _, conn = api
    with conn:
        conn.execute("UPDATE players SET team_id=? WHERE id=?", (CHI, GIDDEY))
        conn.execute("INSERT INTO league_players (player_id, season, team_id, name, gp, pts) VALUES (?, '2026-27', ?, 'Josh Giddey', 2, 2.0)", (GIDDEY, CHI))
        conn.execute("INSERT INTO league_players (player_id, season, team_id, name, gp, pts) VALUES (?, '2025-26', ?, 'Josh Giddey', 70, 17.0)", (GIDDEY, CHI))
    assert availability_api.key_scorers(conn, CHI) == {GIDDEY: 17.0}


async def test_summary_limits(api):
    client, _ = api
    assert (await client.get("/api/availability/summary", params={"game_ids": ",".join(f"G{i}" for i in range(41))})).status_code == 422
    assert (await client.get("/api/availability/summary")).status_code == 422


def test_father_and_son_are_told_apart_by_who_is_active(conn):
    with conn:
        conn.execute("INSERT INTO players (id, full_name, team_abbr, is_active) VALUES (501, 'Tim Hardaway', NULL, 0)")
        conn.execute("INSERT INTO players (id, full_name, team_abbr, is_active) VALUES (502, 'Tim Hardaway Jr.', 'DAL', 1)")
        conn.execute("INSERT INTO players (id, full_name, team_abbr, is_active) VALUES (503, 'Jordan Hawkins II', 'NOP', 1)")
        conn.execute("INSERT INTO players (id, full_name, team_abbr, is_active) VALUES (504, 'Jordan Hawkins Sr.', NULL, 0)")
    assert injuries.find_player(conn, "Tim Hardaway Jr", None) == 502
    assert injuries.find_player(conn, "Tim Hardaway", "DAL") == 502
    assert injuries.find_player(conn, "Jordan Hawkins", None) == 503  # the other namesakes in this fixture are not active
    with conn:
        conn.execute("UPDATE players SET is_active=1 WHERE id IN (14, 15)")
    assert injuries.find_player(conn, "Jordan Hawkins", None) is None  # several active namesakes and no team: never guessed


def test_a_player_listed_twice_or_a_second_writer_never_crashes_the_store(conn, fixtures_dir):
    data = lineup_file(fixtures_dir)
    team = data["games"][0]["homeTeam"]
    team["players"].append(dict(team["players"][0]))  # the same player twice in one team's list
    lineups.store_lineups(conn, data, "2026-10-23T12:00:00+00:00")
    lineups.store_lineups(conn, data, "2026-10-23T12:01:00+00:00")  # and a second writer storing the same file again
    n = conn.execute("SELECT COUNT(*) FROM lineups WHERE game_id=? AND team_id=?", (data["games"][0]["gameId"], team["teamId"])).fetchone()[0]
    assert n == len({p["personId"] for p in team["players"]})
