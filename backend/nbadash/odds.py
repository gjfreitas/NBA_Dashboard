"""Player-prop lines from a licensed odds API, snapshotted into SQLite (never fetched per page view).

  python -m nbadash.odds once [--force]   fetch now (normally at most once every ODDS_MIN_HOURS hours)
  python -m nbadash.odds show             print the stored lines for upcoming games
  python -m nbadash.odds capture DIR      fetch now and save every raw response under DIR (to build test fixtures)

Configuration (environment, nothing is read from files):
  THE_ODDS_API_KEY        key for the-odds-api.com; several keys may be given, comma separated: the next is used when one is used up
  SPORTSGAMEODDS_API_KEY  key for sportsgameodds.com
  ODDS_PROVIDER           theoddsapi | sportsgameodds (default: whichever key is set, The Odds API first)
  ODDS_MARKETS            comma list of our market keys (default: every market we know); see MARKETS below
  ODDS_MONTHLY_BUDGET     credits (The Odds API) / objects (SportsGameOdds) we allow ourselves per month per key (default 450 / 2300)
  ODDS_MIN_HOURS          minimum hours between fetches (default 12)
  ODDS_BOOKMAKERS         optional comma list of bookmaker keys to keep (default: all the provider returns)
  ODDS_REGIONS            The Odds API regions, each multiplies the cost (default us)

Lines are stored append-only: a new row only when a book's line or price changed, so the first row is the opening line.
Both providers are used under their own terms: lines may be shown in the app, but the raw data must not be resold or republished as a feed.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional, Protocol
from zoneinfo import ZoneInfo

from . import db
from .espn_injuries import resolve_team
from .injuries import find_player

log = logging.getLogger("nbadash.odds")
ET = ZoneInfo("America/New_York")

#: our market keys (the frontend's) that a provider can supply
#: dd/td are yes/no markets (stored with line 0.5, "over" = Yes price, "under" = No price); q1* and h1pts are first-quarter / first-half lines
MARKETS = ("pts", "reb", "ast", "fg3m", "pa", "pr", "ra", "pra", "dd", "td", "q1pts", "q1reb", "q1ast", "h1pts", "stl", "blk", "sb", "tov")
DEFAULT_MARKETS = MARKETS
BINARY_MARKETS = ("dd", "td")
WINDOW_HOURS = 30  # only games starting within this long are fetched: lines for later games barely exist and cost budget


@dataclass
class PropLine:
    source: str
    event_id: str
    start_utc: Optional[str]
    home_name: str
    away_name: str
    player_name: str
    market: str
    book: str
    line: float
    over_price: Optional[int] = None
    under_price: Optional[int] = None
    book_updated_at: Optional[str] = None


@dataclass
class FetchResult:
    lines: list[PropLine] = field(default_factory=list)
    events: int = 0
    spent: int = 0  # credits or objects this fetch used
    remaining: Optional[int] = None  # as reported by the provider, if it says


def _implied(price: Optional[int]) -> Optional[float]:
    if price is None or price == 0:
        return None
    return 100 / (price + 100) if price > 0 else -price / (-price + 100)


def _balance(ln: "PropLine") -> float:
    """How far the over/under prices are from an even split (0 = perfectly balanced). A one-sided price counts as unbalanced."""
    o, u = _implied(ln.over_price), _implied(ln.under_price)
    return abs(o - u) if o is not None and u is not None else 1.0


def main_lines(lines: list["PropLine"]) -> list["PropLine"]:
    """Keep one line per player, market and book: the main one. Books list alternate lines under the same market (a 24.5 at -275 next to
    the real 28.5), so for each player and market we take each book's most balanced line, find the consensus of those (the median),
    and keep, per book, the line closest to it (a tie goes to the more balanced one)."""
    groups: dict[tuple, dict[str, list[PropLine]]] = {}
    for ln in lines:
        groups.setdefault((ln.source, ln.event_id, ln.player_name, ln.market), {}).setdefault(ln.book, []).append(ln)
    out: list[PropLine] = []
    for books in groups.values():
        balanced = sorted(min(c, key=_balance).line for c in books.values())
        mid = len(balanced) // 2
        consensus = balanced[mid] if len(balanced) % 2 else (balanced[mid - 1] + balanced[mid]) / 2
        for cands in books.values():
            out.append(min(cands, key=lambda c: (abs(c.line - consensus), _balance(c))))
    return out


class Http(Protocol):
    def __call__(self, url: str, headers: dict, params: dict) -> tuple[int, Any, dict]: ...


def http_get(url: str, headers: dict, params: dict) -> tuple[int, Any, dict]:
    """(status, parsed JSON or None, lower-cased response headers). The only function that touches the network."""
    from curl_cffi import requests as cffi
    r = cffi.get(url, headers=headers, params=params, timeout=30)
    try:
        body = r.json()
    except ValueError:
        body = None
    return r.status_code, body, {k.lower(): v for k, v in r.headers.items()}


class OddsSource(Protocol):
    """A provider of prop lines. `budget` is how many credits/objects this fetch may spend."""
    name: str

    def fetch(self, now: datetime, budget: int, http: Http) -> FetchResult: ...


class OddsError(RuntimeError):
    pass


# ---------------------------------------------------------------- configuration

def configured_markets(env: Optional[dict] = None) -> list[str]:
    raw = (env or os.environ).get("ODDS_MARKETS", "")
    keys = [k.strip() for k in raw.split(",") if k.strip()] or list(DEFAULT_MARKETS)
    bad = [k for k in keys if k not in MARKETS]
    if bad:
        raise OddsError(f"ODDS_MARKETS has unknown markets {bad}; choose from {list(MARKETS)}")
    return keys


def build_source(env: Optional[dict] = None) -> Optional[OddsSource]:
    """The provider the environment asks for, or None when no key is set."""
    from .odds_providers import SportsGameOdds, TheOddsApi
    env = env if env is not None else os.environ
    markets = configured_markets(env)
    books = [b.strip() for b in env.get("ODDS_BOOKMAKERS", "").split(",") if b.strip()]
    toa, sgo = split_keys(env.get("THE_ODDS_API_KEY", "")), env.get("SPORTSGAMEODDS_API_KEY", "").strip()
    pick = env.get("ODDS_PROVIDER", "").strip().lower() or ("theoddsapi" if toa else "sportsgameodds" if sgo else "")
    if pick == "theoddsapi" and toa:
        return TheOddsApi(toa, markets, books, regions=env.get("ODDS_REGIONS", "us").strip() or "us")
    if pick == "sportsgameodds" and sgo:
        return SportsGameOdds(sgo, markets, books)
    if pick and pick not in ("theoddsapi", "sportsgameodds"):
        raise OddsError(f"ODDS_PROVIDER={pick!r} is not one of theoddsapi, sportsgameodds")
    return None


def split_keys(raw: str) -> list[str]:
    return [k.strip() for k in raw.split(",") if k.strip()]


def monthly_budget(source: str, env: Optional[dict] = None) -> int:
    """Credits/objects allowed per month: ODDS_MONTHLY_BUDGET per key, times the number of The Odds API keys given."""
    env = env if env is not None else os.environ
    default = 450 if source == "theoddsapi" else 2300
    try:
        per_key = int(env.get("ODDS_MONTHLY_BUDGET", default))
    except ValueError:
        per_key = default
    return per_key * (max(1, len(split_keys(env.get("THE_ODDS_API_KEY", "")))) if source == "theoddsapi" else 1)


def min_age(env: Optional[dict] = None) -> timedelta:
    env = env if env is not None else os.environ
    try:
        return timedelta(hours=float(env.get("ODDS_MIN_HOURS", 12)))
    except ValueError:
        return timedelta(hours=12)


# ---------------------------------------------------------------- matching and storage

def match_game(conn: sqlite3.Connection, home_name: str, away_name: str, start_utc: Optional[str]) -> Optional[str]:
    """Our schedule game for a provider's event: same two teams, nearest start time."""
    h, _ = resolve_team(conn, home_name)
    a, _ = resolve_team(conn, away_name)
    if h is None or a is None:
        return None
    rows = conn.execute("SELECT game_id, start_utc FROM schedule WHERE home_id=? AND away_id=?", (h, a)).fetchall()
    if not rows:
        return None
    if not start_utc:
        return rows[0]["game_id"] if len(rows) == 1 else None
    when = datetime.fromisoformat(start_utc.replace("Z", "+00:00"))
    best = None
    for r in rows:
        if not r["start_utc"]:
            continue
        gap = abs((datetime.fromisoformat(r["start_utc"].replace("Z", "+00:00")) - when).total_seconds())
        if gap <= 12 * 3600 and (best is None or gap < best[0]):
            best = (gap, r["game_id"])
    return best[1] if best else None


def store_lines(conn: sqlite3.Connection, lines: list[PropLine], seen_at: Optional[str] = None) -> dict:
    """Append lines that are new or changed. Returns counts, including how many events/players could not be matched."""
    seen = seen_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    added = unchanged = 0
    unmatched_games: set[str] = set()
    unmatched_players: set[str] = set()
    games: dict[str, Optional[str]] = {}
    with conn:
        for ln in lines:
            if ln.event_id not in games:
                games[ln.event_id] = match_game(conn, ln.home_name, ln.away_name, ln.start_utc)
                if games[ln.event_id] is None:
                    unmatched_games.add(f"{ln.away_name} @ {ln.home_name}")
            game_id = games[ln.event_id]
            # a prop line doesn't say which team the player is on, so find_player relies on a unique league-wide name match
            pid = find_player(conn, ln.player_name, None)
            if pid is None:
                unmatched_players.add(ln.player_name)
            last = conn.execute("SELECT line, over_price, under_price FROM prop_lines WHERE source=? AND event_id=? AND player_name=? AND market=? AND book=? "
                                "ORDER BY id DESC LIMIT 1", (ln.source, ln.event_id, ln.player_name, ln.market, ln.book)).fetchone()
            if last and (last["line"], last["over_price"], last["under_price"]) == (ln.line, ln.over_price, ln.under_price):
                unchanged += 1
                continue
            conn.execute("INSERT INTO prop_lines (source, event_id, game_id, player_id, player_name, market, book, line, over_price, under_price, book_updated_at, seen_at) "
                         "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (ln.source, ln.event_id, game_id, pid, ln.player_name, ln.market, ln.book, ln.line,
                                                              ln.over_price, ln.under_price, ln.book_updated_at, seen))
            added += 1
    return {"added": added, "unchanged": unchanged, "unmatched_games": sorted(unmatched_games), "unmatched_players": sorted(unmatched_players)}


def spent_this_month(conn: sqlite3.Connection, source: str, now: datetime) -> int:
    r = conn.execute("SELECT spent FROM odds_usage WHERE source=? AND period=?", (source, now.strftime("%Y-%m"))).fetchone()
    return r["spent"] if r else 0


def record_usage(conn: sqlite3.Connection, source: str, now: datetime, spent: int, remaining: Optional[int]) -> None:
    with conn:
        conn.execute("INSERT INTO odds_usage (source, period, spent, remaining) VALUES (?,?,?,?) "
                     "ON CONFLICT(source, period) DO UPDATE SET spent = spent + excluded.spent, remaining = COALESCE(excluded.remaining, remaining)",
                     (source, now.strftime("%Y-%m"), spent, remaining))


KIND = "odds:last"


def brief(out: dict, keep: int = 8) -> dict:
    """The result of a sync with long name lists cut to a count and a few examples, for logs and the console."""
    short = {}
    for k, v in out.items():
        short[k] = v if not isinstance(v, list) else {"count": len(v), "examples": v[:keep]}
    return short


def sync_odds(conn: sqlite3.Connection, *, source: Optional[OddsSource] = None, http: Optional[Http] = None, now: Optional[datetime] = None,
              force: bool = False, env: Optional[dict] = None) -> dict:
    """Fetch and store prop lines if a key is configured, the last fetch is old enough, and this month's budget allows it."""
    now = now or datetime.now(timezone.utc)
    source = source or build_source(env)
    if source is None:
        return {"skipped": "no odds API key set"}
    last = conn.execute("SELECT synced_at FROM sync WHERE player_id=0 AND kind=?", (KIND,)).fetchone()
    if last and not force and now - datetime.fromisoformat(last["synced_at"]) < min_age(env):
        return {"skipped": "fresh", "source": source.name}
    budget = monthly_budget(source.name, env) - spent_this_month(conn, source.name, now)
    if budget <= 0:
        return {"skipped": "monthly budget used up", "source": source.name}
    res = source.fetch(now, budget, http or http_get)
    res.lines = main_lines(res.lines)
    record_usage(conn, source.name, now, res.spent, res.remaining)
    stored = store_lines(conn, res.lines, now.isoformat(timespec="seconds"))
    with conn:
        conn.execute("INSERT OR REPLACE INTO sync VALUES (0, ?, ?)", (KIND, now.isoformat(timespec="seconds")))
    out = {"source": source.name, "events": res.events, "lines": len(res.lines), "spent": res.spent, "remaining": res.remaining, **stored}
    log.info("odds: %s", brief(out))
    return out


# ---------------------------------------------------------------- command line

def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="nbadash.odds", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["once", "show", "capture"])
    ap.add_argument("dir", nargs="?", help="capture: where to save the raw responses")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--db")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    conn = db.connect(args.db)
    if args.cmd == "show":
        rows = conn.execute("SELECT * FROM prop_lines WHERE id IN (SELECT MAX(id) FROM prop_lines GROUP BY source, event_id, player_name, market, book) "
                            "ORDER BY game_id, player_name, market, book").fetchall()
        for r in rows:
            print(f"{r['game_id'] or '?':12} {r['player_name'][:24]:24} {r['market']:5} {r['book']:12} {r['line']:5} o{r['over_price']} u{r['under_price']}  "
                  f"{'id ' + str(r['player_id']) if r['player_id'] else 'UNMATCHED'}")
        print(f"{len(rows)} current lines")
        return 0
    http: Http = http_get
    if args.cmd == "capture":
        if not args.dir:
            ap.error("capture needs a directory")
        out = Path(args.dir)
        out.mkdir(parents=True, exist_ok=True)
        n = [0]

        def recording(url: str, headers: dict, params: dict):
            status, body, hdrs = http_get(url, headers, params)
            n[0] += 1
            safe = {k: v for k, v in params.items() if k.lower() not in ("apikey", "api_key")}  # never write the key to disk
            (out / f"{n[0]:02d}.json").write_text(json.dumps({"url": url, "params": safe, "status": status, "headers": {k: v for k, v in hdrs.items() if k.startswith("x-")}, "body": body}, indent=1), encoding="utf-8")
            return status, body, hdrs
        http = recording
        args.force = True
    try:
        print(json.dumps(brief(sync_odds(conn, http=http, force=args.force)), ensure_ascii=True))
    except OddsError as e:
        print(f"odds: {e}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
