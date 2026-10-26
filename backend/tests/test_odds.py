"""Odds tests. The payloads below are written from each provider's DOCUMENTED shape, not captured from a live key
(`python -m nbadash.odds capture DIR` saves real ones: replace these with those once a key exists)."""
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from nbadash import db, health, odds, odds_api, refresh
from nbadash.app import create_app
from nbadash.odds import OddsError, sync_odds
from nbadash.odds_providers import SportsGameOdds, TheOddsApi
from nbadash.sources import ReplaySource

NOW = datetime(2026, 10, 24, 14, 0, tzinfo=timezone.utc)
TIP = "2026-10-24T23:00:00Z"
DEN, NOP = 1610612743, 1610612740


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "o.db")
    with c:
        c.execute("INSERT INTO teams (id, abbr, city, name) VALUES (?, 'DEN', 'Denver', 'Nuggets')", (DEN,))
        c.execute("INSERT INTO teams (id, abbr, city, name) VALUES (?, 'NOP', 'New Orleans', 'Pelicans')", (NOP,))
        c.execute("INSERT INTO schedule (game_id, season, game_date, start_utc, status, home_id, away_id, home_abbr, away_abbr) "
                  "VALUES ('G1', '2026-27', '2026-10-24', ?, 1, ?, ?, 'DEN', 'NOP')", (TIP, DEN, NOP))
        c.execute("INSERT INTO players (id, full_name, team_abbr, is_active) VALUES (203999, 'Nikola Jokić', 'DEN', 1)")
        c.execute("INSERT INTO players (id, full_name, team_abbr, is_active) VALUES (1, 'Zion Williamson', 'NOP', 1)")
    return c


# ------------------------------------------------------------------ The Odds API

def toa_event(points=24.5, over=-115, under=-105, book="draftkings"):
    return {"id": "e1", "commence_time": TIP, "home_team": "Denver Nuggets", "away_team": "New Orleans Pelicans", "bookmakers": [{
        "key": book, "title": "DraftKings", "last_update": "2026-10-24T13:55:00Z", "markets": [{
            "key": "player_points", "last_update": "2026-10-24T13:55:00Z", "outcomes": [
                {"name": "Over", "description": "Nikola Jokic", "price": over, "point": points},
                {"name": "Under", "description": "Nikola Jokic", "price": under, "point": points},
                {"name": "Over", "description": "Nikola Jokic", "price": 250, "point": 34.5},  # an alternate line: ignored
                {"name": "Over", "description": "Zion Williamson", "price": 100, "point": 22.5},
            ]}, {"key": "player_rebounds", "outcomes": [
                {"name": "Over", "description": "Nikola Jokic", "price": -120, "point": 12.5},
                {"name": "Under", "description": "Nikola Jokic", "price": 100, "point": 12.5}]}]}]}


class FakeToa:
    """Routes The Odds API URLs; records every call."""

    def __init__(self, events=None, odds_status=200, last_cost=2):
        self.calls, self.events, self.odds_status, self.last_cost = [], events if events is not None else [{"id": "e1", "commence_time": TIP}], odds_status, last_cost

    def __call__(self, url, headers, params):
        self.calls.append((url, dict(params)))
        if url.endswith("/events"):
            return 200, self.events, {}
        return self.odds_status, toa_event() if self.odds_status == 200 else None, {"x-requests-last": str(self.last_cost), "x-requests-remaining": "480"}


def toa(markets=("pts", "reb")):
    return TheOddsApi("KEY", list(markets))


def test_the_odds_api_parses_every_point_and_main_lines_picks_the_real_one():
    lines = toa().parse_event(toa_event())
    pts = [ln for ln in lines if ln.player_name == "Nikola Jokic" and ln.market == "pts"]
    assert sorted(ln.line for ln in pts) == [24.5, 34.5]  # the 34.5 alternate is parsed too ...
    jok = odds.main_lines(lines)
    by = {(ln.player_name, ln.market): ln for ln in jok}
    assert (by[("Nikola Jokic", "pts")].line, by[("Nikola Jokic", "pts")].over_price, by[("Nikola Jokic", "pts")].under_price) == (24.5, -115, -105)  # ... and dropped here
    assert by[("Zion Williamson", "pts")].under_price is None  # only an Over was posted
    assert by[("Nikola Jokic", "reb")].line == 12.5 and len(jok) == 3


def pl(book, line, over, under, player="P", market="pts"):
    return odds.PropLine("s", "e", TIP, "Denver Nuggets", "New Orleans Pelicans", player, market, book, line, over, under)


def test_main_lines_follow_the_consensus_not_the_first_line_seen():
    """The shape of the real data: some books list an alternate under the main market (a lopsided 24.5 beside the real 28.5)."""
    lines = [pl("fanduel", 28.5, -125, -106), pl("draftkings", 28.5, -115, -111), pl("caesars", 28.5, -120, -112),
             pl("bovada", 24.5, -275, 200), pl("bovada", 28.5, -120, -110),
             pl("betmgm", 27.5, -125, None)]  # a one-sided price from a book with a single line is kept, not invented away
    kept = {ln.book: ln.line for ln in odds.main_lines(lines)}
    assert kept == {"fanduel": 28.5, "draftkings": 28.5, "caesars": 28.5, "bovada": 28.5, "betmgm": 27.5}
    # two lines at one book: the one nearer the consensus wins; an exact tie goes to the more balanced prices
    close = [pl("a", 5.5, -140, 110), pl("b", 5.5, -145, 110), pl("c", 5.5, -150, 115), pl("c", 6.5, 120, -160), pl("d", 5.5, -150, 115), pl("d", 6.5, 105, -135)]
    assert {ln.book: ln.line for ln in odds.main_lines(close)}["c"] == 5.5
    assert odds.main_lines([]) == []
    # players and markets are separate groups
    mixed = [pl("a", 25.5, -110, -110, "X"), pl("a", 7.5, -110, -110, "X", "reb"), pl("a", 12.5, -110, -110, "Y")]
    assert len(odds.main_lines(mixed)) == 3


def test_the_odds_api_fetch_costs_follow_the_headers_and_the_budget():
    http = FakeToa()
    res = toa().fetch(NOW, 100, http)
    assert (res.events, res.spent, res.remaining) == (1, 2, 480) and len(res.lines) == 4
    events_call, odds_call = http.calls
    assert events_call[0].endswith("/sports/basketball_nba/events") and odds_call[0].endswith("/events/e1/odds")
    assert odds_call[1]["markets"] == "player_points,player_rebounds" and odds_call[1]["regions"] == "us" and odds_call[1]["oddsFormat"] == "american"
    # not enough budget for another event (2 credits each): nothing is fetched, and the free events call is the only one made
    http2 = FakeToa()
    res2 = toa().fetch(NOW, 1, http2)
    assert res2.events == 0 and len(http2.calls) == 1


def test_only_games_in_the_window_are_fetched_nearest_first():
    far = {"id": "e9", "commence_time": "2026-10-27T01:00:00Z"}
    past = {"id": "e0", "commence_time": "2026-10-23T01:00:00Z"}
    later = {"id": "e2", "commence_time": "2026-10-25T01:00:00Z"}
    http = FakeToa(events=[far, later, {"id": "e1", "commence_time": TIP}, past])
    toa().fetch(NOW, 100, http)
    assert [c[0].split("/events/")[1].split("/")[0] for c in http.calls[1:]] == ["e1", "e2"]  # the far and the finished games cost nothing


@pytest.mark.parametrize("status,words", [(401, "key was refused"), (429, "quota"), (500, "HTTP 500")])
def test_provider_errors_are_clear(status, words):
    with pytest.raises(OddsError, match=words):
        toa().fetch(NOW, 100, FakeToa(odds_status=status))


def test_markets_must_be_known(monkeypatch):
    with pytest.raises(OddsError, match="unknown markets"):
        odds.configured_markets({"ODDS_MARKETS": "pts,bogus"})
    assert odds.configured_markets({}) == list(odds.MARKETS)
    with pytest.raises(OddsError):
        TheOddsApi("k", ["h1pts"])  # The Odds API has no first-half player market


# ------------------------------------------------------------------ SportsGameOdds

def sgo_event():
    over = {"oddID": "points-NIKOLA_JOKIC_1_NBA-game-ou-over", "opposingOddID": "points-NIKOLA_JOKIC_1_NBA-game-ou-under", "statID": "points",
            "playerID": "NIKOLA_JOKIC_1_NBA", "periodID": "game", "betTypeID": "ou", "sideID": "over",
            "byBookmaker": {"draftkings": {"odds": "-115", "overUnder": "24.5", "lastUpdatedAt": "2026-10-24T13:50:00.000Z", "available": True},
                            "fanduel": {"odds": "+100", "overUnder": "25.5", "available": True},
                            "caesars": {"odds": "-110", "overUnder": "24.5", "available": False}}}
    under = {"oddID": "points-NIKOLA_JOKIC_1_NBA-game-ou-under", "statID": "points", "playerID": "NIKOLA_JOKIC_1_NBA", "periodID": "game",
             "betTypeID": "ou", "sideID": "under", "byBookmaker": {"draftkings": {"odds": "-105", "overUnder": "24.5"}, "fanduel": {"odds": "-120", "overUnder": "25.5"}}}
    first_half = dict(over, oddID="points-NIKOLA_JOKIC_1_NBA-1h-ou-over", periodID="1h")
    game_line = {"oddID": "points-home-game-ml-home", "statID": "points", "betTypeID": "ml", "sideID": "home", "periodID": "game", "byBookmaker": {}}
    return {"eventID": "ev1", "status": {"startsAt": TIP}, "teams": {"home": {"names": {"long": "Denver Nuggets"}}, "away": {"names": {"long": "New Orleans Pelicans"}}},
            "players": {"NIKOLA_JOKIC_1_NBA": {"playerID": "NIKOLA_JOKIC_1_NBA", "name": "Nikola Jokić"}},
            "odds": {o["oddID"]: o for o in (over, under, first_half, game_line)}}


def test_sportsgameodds_parses_over_lines_with_the_under_price_and_skips_the_rest():
    lines = SportsGameOdds("K", ["pts"]).parse_event(sgo_event())
    by = {ln.book: ln for ln in lines}
    assert set(by) == {"draftkings", "fanduel"}  # caesars is not available; first-half and moneyline odds are skipped
    dk = by["draftkings"]
    assert (dk.player_name, dk.market, dk.line, dk.over_price, dk.under_price, dk.home_name) == ("Nikola Jokić", "pts", 24.5, -115, -105, "Denver Nuggets")
    assert (by["fanduel"].line, by["fanduel"].over_price, by["fanduel"].under_price) == (25.5, 100, -120)
    assert SportsGameOdds("K", ["reb"]).parse_event(sgo_event()) == []  # we only asked for rebounds


def test_sportsgameodds_pages_count_objects_and_stop_at_the_budget():
    pages = [{"data": [sgo_event(), sgo_event()], "nextCursor": "c2"}, {"data": [sgo_event()], "nextCursor": None}]
    calls = []

    def http(url, headers, params):
        calls.append((headers, dict(params)))
        return 200, pages[len(calls) - 1], {}

    res = SportsGameOdds("SECRET", ["pts"]).fetch(NOW, 100, http)
    assert (res.events, res.spent) == (3, 3) and len(calls) == 2
    assert calls[0][0] == {"x-api-key": "SECRET"} and "cursor" not in calls[0][1] and calls[1][1]["cursor"] == "c2"
    assert calls[0][1]["leagueID"] == "NBA" and calls[0][1]["startsBefore"].endswith("Z")
    calls.clear()
    res = SportsGameOdds("K", ["pts"]).fetch(NOW, 2, http)  # the first page alone is 2 objects; the second would go over
    assert (res.events, res.spent) == (2, 2)


# ------------------------------------------------------------------ storage, matching, sync

def lines_for(source="theoddsapi", **kw):
    return odds.main_lines(toa().parse_event(toa_event(**kw))) if source == "theoddsapi" else []


def test_store_matches_the_game_and_players_and_dedupes(conn):
    out = odds.store_lines(conn, lines_for(), "2026-10-24T14:00:00+00:00")
    assert out["added"] == 3 and out["unmatched_games"] == [] and out["unmatched_players"] == []
    row = conn.execute("SELECT * FROM prop_lines WHERE player_name='Nikola Jokic' AND market='pts'").fetchone()
    assert (row["game_id"], row["player_id"]) == ("G1", 203999)  # accent-less provider name still finds Jokić
    again = odds.store_lines(conn, lines_for(), "2026-10-24T20:00:00+00:00")
    assert again["added"] == 0 and again["unchanged"] == 3
    moved = odds.store_lines(conn, lines_for(points=25.5), "2026-10-24T21:00:00+00:00")
    assert moved["added"] == 1  # only the points line changed
    assert [r["line"] for r in conn.execute("SELECT line FROM prop_lines WHERE player_id=203999 AND market='pts' ORDER BY id")] == [24.5, 25.5]


def test_unmatched_games_and_players_are_reported_not_hidden(conn):
    ev = toa_event()
    ev["home_team"] = "Atlantis Krakens"
    ln = odds.main_lines(toa().parse_event(ev))
    out = odds.store_lines(conn, ln)
    assert out["unmatched_games"] == ["New Orleans Pelicans @ Atlantis Krakens"]
    assert conn.execute("SELECT COUNT(*) FROM prop_lines WHERE game_id IS NULL").fetchone()[0] == 3  # stored anyway, just not linked to a game
    odds.store_lines(conn, [odds.PropLine("s", "e", TIP, "Denver Nuggets", "New Orleans Pelicans", "Nobody Real", "pts", "dk", 5.5)])
    assert odds.store_lines(conn, [odds.PropLine("s", "e", TIP, "Denver Nuggets", "New Orleans Pelicans", "Nobody Real", "pts", "dk", 6.5)])["unmatched_players"] == ["Nobody Real"]


def test_game_matching_uses_the_nearest_start_time(conn):
    with conn:
        conn.execute("INSERT INTO schedule (game_id, season, game_date, start_utc, status, home_id, away_id, home_abbr, away_abbr) "
                     "VALUES ('G2', '2026-27', '2026-11-20', '2026-11-20T23:00:00Z', 1, ?, ?, 'DEN', 'NOP')", (DEN, NOP))
    assert odds.match_game(conn, "Denver Nuggets", "New Orleans Pelicans", TIP) == "G1"
    assert odds.match_game(conn, "Denver Nuggets", "New Orleans Pelicans", "2026-11-20T23:30:00Z") == "G2"
    assert odds.match_game(conn, "Denver Nuggets", "New Orleans Pelicans", "2026-12-25T23:00:00Z") is None


def env(**kw):
    return {"THE_ODDS_API_KEY": "KEY", **kw}


def test_sync_without_a_key_does_nothing_and_never_calls_out(conn):
    assert sync_odds(conn, now=NOW, env={}) == {"skipped": "no odds API key set"}
    assert conn.execute("SELECT COUNT(*) FROM prop_lines").fetchone()[0] == 0


def test_sync_stores_then_waits_then_respects_the_monthly_budget(conn):
    http = FakeToa()
    out = sync_odds(conn, http=http, now=NOW, env=env(ODDS_MARKETS="pts,reb"))
    assert (out["events"], out["lines"], out["added"], out["spent"]) == (1, 3, 3, 2)
    assert sync_odds(conn, http=http, now=NOW + timedelta(hours=3), env=env())["skipped"] == "fresh"
    assert sync_odds(conn, http=FakeToa(), now=NOW + timedelta(hours=13), env=env(ODDS_MARKETS="pts,reb", ODDS_MONTHLY_BUDGET="2"))["skipped"] == "monthly budget used up"
    assert odds.spent_this_month(conn, "theoddsapi", NOW) == 2
    # next month the counter starts again
    assert odds.spent_this_month(conn, "theoddsapi", NOW + timedelta(days=30)) == 0
    forced = sync_odds(conn, http=FakeToa(), now=NOW + timedelta(hours=1), force=True, env=env(ODDS_MARKETS="pts,reb"))
    assert forced["added"] == 0 and forced["unchanged"] == 3


def test_provider_choice_and_errors(conn):
    assert odds.build_source({}) is None
    assert odds.build_source({"SPORTSGAMEODDS_API_KEY": "k"}).name == "sportsgameodds"
    assert odds.build_source({"SPORTSGAMEODDS_API_KEY": "k", "THE_ODDS_API_KEY": "k"}).name == "theoddsapi"
    assert odds.build_source({"SPORTSGAMEODDS_API_KEY": "k", "THE_ODDS_API_KEY": "k", "ODDS_PROVIDER": "sportsgameodds"}).name == "sportsgameodds"
    assert odds.build_source({"ODDS_PROVIDER": "theoddsapi"}) is None  # asked for it but has no key
    with pytest.raises(OddsError, match="not one of"):
        odds.build_source({"ODDS_PROVIDER": "nope", "THE_ODDS_API_KEY": "k"})


# ------------------------------------------------------------------ job isolation, health, API, secrets

def test_refresh_odds_isolates_failures_and_reports_them(conn, monkeypatch):
    assert refresh.refresh_odds(conn) == {"skipped": "no odds API key set"}
    assert "odds" not in {r["source"] for r in conn.execute("SELECT source FROM source_checks")}  # no key: nothing to report on the status page
    monkeypatch.setenv("THE_ODDS_API_KEY", "KEY")
    soon = [{"id": "e1", "commence_time": (datetime.now(timezone.utc) + timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ")}]  # this test uses the real clock
    monkeypatch.setattr(odds, "http_get", FakeToa(events=soon, odds_status=401))
    out = refresh.refresh_odds(conn)
    assert "key was refused" in out["odds_error"]
    item = next(i for i in health.build(conn, NOW).items if i.key == "odds")
    assert item.status == "error" and "refused" in item.last_error
    monkeypatch.setattr(odds, "http_get", FakeToa(events=soon))
    monkeypatch.setenv("ODDS_MARKETS", "pts,reb")
    assert refresh.refresh_odds(conn)["added"] == 3
    assert next(i for i in health.build(conn).items if i.key == "odds").status == "ok"


async def test_lines_endpoint(conn, tmp_path, fixtures_dir):
    odds.store_lines(conn, lines_for(), datetime.now(timezone.utc).isoformat(timespec="seconds"))
    odds.store_lines(conn, lines_for(points=25.5), datetime.now(timezone.utc).isoformat(timespec="seconds"))
    app = create_app(ReplaySource(fixtures_dir), db_path=str(tmp_path / "o.db"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        d = (await client.get("/api/players/203999/lines")).json()
        assert d["game_id"] == "G1" and d["source"] == "theoddsapi" and set(d["markets"]) == {"pts", "reb"}
        [pts] = d["markets"]["pts"]
        assert (pts["book"], pts["line"], pts["opening_line"], pts["over_price"]) == ("draftkings", 25.5, 24.5, -115)  # the line moved a point since the open
        assert (await client.get("/api/players/77/lines")).json() == {"game_id": None, "source": None, "as_of": None, "markets": {}}
        assert (await client.get("/api/players/203999")).status_code == 200  # the profile route still works next to /lines


def test_old_lines_and_started_games_are_not_shown(conn):
    odds.store_lines(conn, lines_for(), "2026-10-20T00:00:00+00:00")
    assert odds_api.player_lines(conn, 203999, now=NOW).markets == {}  # seen four days ago: stale
    odds.store_lines(conn, lines_for(points=26.5), NOW.isoformat(timespec="seconds"))
    assert "pts" in odds_api.player_lines(conn, 203999, now=NOW).markets
    with conn:
        conn.execute("UPDATE schedule SET status=2")
    assert odds_api.player_lines(conn, 203999, now=NOW).markets == {}  # the game is under way: pre-game lines no longer apply


def test_capture_never_writes_the_key(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("THE_ODDS_API_KEY", "SUPERSECRET")
    monkeypatch.setenv("ODDS_MARKETS", "pts")
    monkeypatch.setattr(odds, "http_get", FakeToa())
    out = tmp_path / "cap"
    assert odds.main(["capture", str(out), "--db", str(tmp_path / "c.db")]) == 0
    files = sorted(out.glob("*.json"))
    assert files and all("SUPERSECRET" not in f.read_text(encoding="utf-8") for f in files)
    assert json.loads(files[0].read_text(encoding="utf-8"))["status"] == 200


# ------------------------------------------------------------------ more markets and several keys

def test_double_double_and_quarter_markets_are_parsed():
    ev = toa_event()
    ev["bookmakers"][0]["markets"] += [
        {"key": "player_double_double", "outcomes": [{"name": "Yes", "description": "Nikola Jokic", "price": -300}, {"name": "No", "description": "Nikola Jokic", "price": 240}]},
        {"key": "player_triple_double", "outcomes": [{"name": "Nikola Jokic", "description": "Yes", "price": 150}]},  # player in `name`, only the Yes side listed
        {"key": "player_points_q1", "outcomes": [{"name": "Over", "description": "Nikola Jokic", "price": -110, "point": 7.5}, {"name": "Under", "description": "Nikola Jokic", "price": -110, "point": 7.5}]},
    ]
    lines = {(ln.market): ln for ln in TheOddsApi("K", ["dd", "td", "q1pts"]).parse_event(ev)}
    assert (lines["dd"].line, lines["dd"].over_price, lines["dd"].under_price) == (0.5, -300, 240)
    assert (lines["td"].line, lines["td"].over_price, lines["td"].under_price) == (0.5, 150, None)
    assert (lines["q1pts"].line, lines["q1pts"].over_price) == (7.5, -110)


def test_sportsgameodds_reads_first_quarter_and_half_lines():
    ev = {"eventID": "s1", "status": {"startsAt": TIP}, "teams": {"home": {"names": {"long": "Denver Nuggets"}}, "away": {"names": {"long": "New Orleans Pelicans"}}},
          "players": {"P1": {"name": "Nikola Jokic"}}, "odds": {
              "a": {"betTypeID": "ou", "sideID": "over", "periodID": "1q", "statID": "points", "playerID": "P1", "byBookmaker": {"fanduel": {"overUnder": "8.5", "odds": "-110"}}},
              "b": {"betTypeID": "ou", "sideID": "over", "periodID": "1h", "statID": "points", "playerID": "P1", "byBookmaker": {"fanduel": {"overUnder": "16.5", "odds": "-115"}}}}}
    got = {ln.market: ln.line for ln in SportsGameOdds("K", ["q1pts", "h1pts"]).parse_event(ev)}
    assert got == {"q1pts": 8.5, "h1pts": 16.5}


def test_a_used_up_key_hands_over_to_the_next_and_the_budget_grows_with_the_keys():
    class TwoKeys(FakeToa):
        def __call__(self, url, headers, params):
            if params.get("apiKey") == "A":
                self.calls.append((url, dict(params)))
                return 429, None, {}
            return super().__call__(url, headers, params)

    http = TwoKeys()
    res = TheOddsApi(["A", "B"], ["pts", "reb"]).fetch(NOW, 100, http)
    assert res.events == 1 and res.lines
    assert [c[1]["apiKey"] for c in http.calls if not c[0].endswith("/events")][-1] == "B"
    assert odds.monthly_budget("theoddsapi", {"THE_ODDS_API_KEY": "A, B,C"}) == 3 * 450
    assert odds.monthly_budget("theoddsapi", {"THE_ODDS_API_KEY": "A", "ODDS_MONTHLY_BUDGET": "100"}) == 100
