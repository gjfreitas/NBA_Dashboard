"""The two odds providers behind `odds.OddsSource`.

TheOddsApi   https://the-odds-api.com  : one free call lists events, then one call per event for the player markets.
             Cost per event = markets returned x regions credits (the free plan has 500 credits a month).
SportsGameOdds https://sportsgameodds.com : one call returns every event with all its odds. An event is one "object" (the free plan has 2,500 a month).

The Odds API parsing follows its documented v4 shape. SportsGameOdds parsing follows the documented v2 shape but has not been checked against a
real NBA response yet: run `python -m nbadash.odds capture DIR` once with a key and compare (see tests/test_odds.py).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from .odds import BINARY_MARKETS, WINDOW_HOURS, FetchResult, Http, OddsError, PropLine

# provider market key -> our market key
TOA_MARKETS = {
    "player_points": "pts", "player_rebounds": "reb", "player_assists": "ast", "player_threes": "fg3m",
    "player_points_assists": "pa", "player_points_rebounds": "pr", "player_rebounds_assists": "ra", "player_points_rebounds_assists": "pra",
    "player_steals": "stl", "player_blocks": "blk", "player_blocks_steals": "sb", "player_turnovers": "tov",
    "player_double_double": "dd", "player_triple_double": "td",
    "player_points_q1": "q1pts", "player_rebounds_q1": "q1reb", "player_assists_q1": "q1ast",  # The Odds API has no 1st-half player market
}
SGO_STATS = {
    "points": "pts", "rebounds": "reb", "assists": "ast", "threePointersMade": "fg3m", "points+assists": "pa", "points+rebounds": "pr",
    "rebounds+assists": "ra", "points+rebounds+assists": "pra", "steals": "stl", "blocks": "blk", "blocks+steals": "sb", "turnovers": "tov",
}
# (periodID, statID) -> our market, for first-quarter and first-half lines. Double/triple double are not mapped: their statIDs are unconfirmed.
SGO_PERIODS = {("1q", "points"): "q1pts", ("1q", "rebounds"): "q1reb", ("1q", "assists"): "q1ast", ("1h", "points"): "h1pts"}


def _price(v: Any) -> Optional[int]:
    try:
        return int(float(str(v).replace("+", "")))
    except (TypeError, ValueError):
        return None


def _num(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _check(status: int, body: Any, what: str) -> Any:
    if status in (401, 403):
        raise OddsError(f"{what}: the API key was refused (HTTP {status})")
    if status == 429:
        raise OddsError(f"{what}: rate limited or quota used up (HTTP 429)")
    if status != 200 or body is None:
        raise OddsError(f"{what}: HTTP {status}")
    return body


class TheOddsApi:
    name = "theoddsapi"
    base = "https://api.the-odds-api.com/v4"

    def __init__(self, key: "str | list[str]", markets: list[str], bookmakers: list[str] = (), regions: str = "us"):
        wanted = set(markets)
        self.keys = [key] if isinstance(key, str) else list(key)
        self.key, self.regions, self.bookmakers = self.keys[0], regions, list(bookmakers)
        self.provider_markets = [pm for pm, ours in TOA_MARKETS.items() if ours in wanted]
        if not self.provider_markets:
            raise OddsError(f"none of {markets} is available from The Odds API")

    def _get(self, http: Http, url: str, params: dict) -> tuple[int, Any, dict]:
        """One call; a key that is refused or out of credits hands over to the next key (a refused call costs nothing)."""
        while True:
            status, body, hdrs = http(url, {}, dict(params, apiKey=self.key))
            if status in (401, 403, 429) and self.keys.index(self.key) + 1 < len(self.keys):
                self.key = self.keys[self.keys.index(self.key) + 1]
                continue
            return status, body, hdrs

    def fetch(self, now: datetime, budget: int, http: Http) -> FetchResult:
        res = FetchResult()
        status, body, _ = self._get(http, f"{self.base}/sports/basketball_nba/events", {"dateFormat": "iso"})  # free: costs 0 credits
        events = _check(status, body, "The Odds API events")
        horizon = now + timedelta(hours=WINDOW_HOURS)
        soon = sorted((e for e in events if now - timedelta(hours=1) <= datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00")) <= horizon),
                      key=lambda e: e["commence_time"])
        per_event = len(self.provider_markets) * max(1, len(self.regions.split(",")))
        for ev in soon:
            if res.spent + per_event > budget:
                break  # keep the rest of the month's credits for later days
            params = {"regions": self.regions, "markets": ",".join(self.provider_markets), "oddsFormat": "american", "dateFormat": "iso"}
            if self.bookmakers:
                params["bookmakers"] = ",".join(self.bookmakers)
            status, body, hdrs = self._get(http, f"{self.base}/sports/basketball_nba/events/{ev['id']}/odds", params)
            try:
                body = _check(status, body, f"The Odds API odds for {ev.get('away_team')} @ {ev.get('home_team')}")
            except OddsError:
                if res.events:
                    break  # every key is used up: keep what this fetch already got
                raise
            used = _price(hdrs.get("x-requests-last"))
            res.spent += used if used is not None else per_event
            res.remaining = _price(hdrs.get("x-requests-remaining")) if hdrs.get("x-requests-remaining") is not None else res.remaining
            res.events += 1
            res.lines.extend(self.parse_event(body))
        return res

    def parse_event(self, ev: dict) -> list[PropLine]:
        out: list[PropLine] = []
        for bk in ev.get("bookmakers", []):
            for mk in bk.get("markets", []):
                ours = TOA_MARKETS.get(mk.get("key", ""))
                if ours is None:
                    continue
                pairs: dict[tuple[str, float], dict] = {}  # (player, point) -> {"Over": price, "Under": price}; alternates are separate points
                binary = ours in BINARY_MARKETS  # yes/no: stored as line 0.5, Yes in the "over" slot, No in the "under" slot
                for oc in mk.get("outcomes", []):
                    player, side, point = oc.get("description"), oc.get("name"), _num(oc.get("point"))
                    if binary:
                        if side not in ("Yes", "No") and player in ("Yes", "No"):
                            player, side = side, player  # some books put the player in `name` and Yes/No in `description`
                        if not player or side not in ("Yes", "No"):
                            continue
                        pairs.setdefault((player, 0.5), {})["Over" if side == "Yes" else "Under"] = _price(oc.get("price"))
                        continue
                    if not player or side not in ("Over", "Under") or point is None:
                        continue
                    pairs.setdefault((player, point), {})[side] = _price(oc.get("price"))
                for (player, point), d in pairs.items():  # odds.main_lines later keeps the main point per book
                    out.append(PropLine(source=self.name, event_id=ev["id"], start_utc=ev.get("commence_time"), home_name=ev.get("home_team", ""),
                                        away_name=ev.get("away_team", ""), player_name=player, market=ours, book=bk.get("key", ""), line=point,
                                        over_price=d.get("Over"), under_price=d.get("Under"), book_updated_at=mk.get("last_update") or bk.get("last_update")))
        return out


class SportsGameOdds:
    name = "sportsgameodds"
    base = "https://api.sportsgameodds.com/v2"

    def __init__(self, key: str, markets: list[str], bookmakers: list[str] = ()):
        wanted = set(markets)
        self.key, self.bookmakers = key, list(bookmakers)
        self.stats = {s: ours for s, ours in SGO_STATS.items() if ours in wanted}
        self.periods = {k: ours for k, ours in SGO_PERIODS.items() if ours in wanted}
        if not self.stats and not self.periods:
            raise OddsError(f"none of {markets} is available from SportsGameOdds")

    def fetch(self, now: datetime, budget: int, http: Http) -> FetchResult:
        res = FetchResult()
        params: dict[str, Any] = {"leagueID": "NBA", "oddsAvailable": "true", "startsAfter": _iso(now - timedelta(hours=1)),
                                  "startsBefore": _iso(now + timedelta(hours=WINDOW_HOURS)), "limit": 25}
        if self.bookmakers:
            params["bookmakerID"] = ",".join(self.bookmakers)
        cursor = None
        while True:
            page = dict(params, **({"cursor": cursor} if cursor else {}))
            status, body, _ = http(f"{self.base}/events", {"x-api-key": self.key}, page)
            body = _check(status, body, "SportsGameOdds events")
            events = body.get("data") or []
            if res.spent + max(1, len(events)) > budget:
                break  # an event is one object; stay inside the monthly allowance
            res.spent += max(1, len(events))
            res.events += len(events)
            for ev in events:
                res.lines.extend(self.parse_event(ev))
            cursor = body.get("nextCursor")
            if not cursor or not events:
                break
        return res

    def parse_event(self, ev: dict) -> list[PropLine]:
        teams = ev.get("teams") or {}
        names = {side: ((teams.get(side) or {}).get("names") or {}) for side in ("home", "away")}
        home = names["home"].get("long") or names["home"].get("medium") or ""
        away = names["away"].get("long") or names["away"].get("medium") or ""
        players = ev.get("players") or {}
        odds = ev.get("odds") or {}
        out: list[PropLine] = []
        for odd in odds.values():
            if odd.get("betTypeID") != "ou" or odd.get("sideID") != "over":
                continue
            period, stat = odd.get("periodID"), odd.get("statID", "")
            ours = self.stats.get(stat) if period == "game" else self.periods.get((period, stat))
            pid = odd.get("playerID")
            if ours is None or not pid:
                continue
            p = players.get(pid) or {}
            name = p.get("name") or " ".join(x for x in (p.get("firstName"), p.get("lastName")) if x)
            if not name:
                continue
            under = (odds.get(odd.get("opposingOddID") or "") or {}).get("byBookmaker") or {}
            for book, b in (odd.get("byBookmaker") or {}).items():
                line = _num(b.get("overUnder"))
                if line is None or b.get("available") is False:
                    continue
                out.append(PropLine(source=self.name, event_id=ev.get("eventID", ""), start_utc=(ev.get("status") or {}).get("startsAt"), home_name=home, away_name=away,
                                    player_name=name, market=ours, book=book, line=line, over_price=_price(b.get("odds")),
                                    under_price=_price((under.get(book) or {}).get("odds")), book_updated_at=b.get("lastUpdatedAt")))
        return out
