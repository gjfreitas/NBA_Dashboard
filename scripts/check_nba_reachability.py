"""Can this machine reach every outside source the dashboard reads?

Run it on the machine you are thinking of hosting on (a GitHub Actions runner, a cloud VM) before building anything there:

    pip install curl_cffi nba_api
    python scripts/check_nba_reachability.py

It prints one line per source, writes a markdown table to $GITHUB_STEP_SUMMARY when run in Actions, and always exits 0: it is a report, not a test.
The same calls and TLS fingerprint (curl_cffi, impersonate="chrome") are used as in backend/nbadash.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from curl_cffi import requests as cffi

ET = ZoneInfo("America/New_York")
TODAY = datetime.now(ET)
SEASON = f"{TODAY.year}-{str(TODAY.year + 1)[2:]}" if TODAY.month >= 9 else f"{TODAY.year - 1}-{str(TODAY.year)[2:]}"

#: name, what the dashboard uses it for, url
URLS = [
    ("cdn scoreboard", "live scores, today's games", "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json"),
    ("cdn schedule", "season schedule", "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json"),
    ("nba injury report page", "official injury report index", f"https://official.nba.com/nba-injury-report-{SEASON}-season/"),
    ("stats.nba.com lineups file", "projected / confirmed starters", f"https://stats.nba.com/js/data/leaders/00_daily_lineups_{TODAY:%Y%m%d}.json"),
    ("ESPN injuries", "second injury source", "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"),
    ("The Odds API (events, free)", "odds provider; no key, so 401 is the expected answer", "https://api.the-odds-api.com/v4/sports/basketball_nba/events"),
]


def fetch(url: str) -> tuple[str, str]:
    """('OK' | 'BLOCKED' | 'FAIL', detail), trying twice: the NBA's CDN answers 403 for a stuck first connection."""
    last = ""
    for attempt in (1, 2):
        t0 = time.time()
        try:
            r = cffi.get(url, impersonate="chrome", timeout=30, headers={"Accept": "application/json, text/plain, */*", "Referer": "https://www.nba.com/"})
            took = time.time() - t0
            last = f"HTTP {r.status_code}, {len(r.content):,} bytes, {took:.1f}s"
            if r.status_code == 200:
                return "OK", last
            if r.status_code in (401, 404) and "the-odds-api" in url:
                return "OK", last + " (reachable; no key)"
        except Exception as e:  # timeouts, resets, TLS errors
            last = f"{type(e).__name__}: {str(e)[:120]}"
        time.sleep(2)
    return ("BLOCKED" if "HTTP 403" in last or "HTTP 429" in last else "FAIL"), last


def stats_api() -> tuple[str, str]:
    """The heavy ingest goes through nba_api to stats.nba.com; this is the call most often refused from cloud addresses."""
    try:
        from nba_api.stats.endpoints import leaguedashteamstats
    except ImportError:
        return "SKIPPED", "nba_api is not installed"
    t0 = time.time()
    try:
        rows = leaguedashteamstats.LeagueDashTeamStats(season=SEASON, timeout=30).get_data_frames()[0]
        return "OK", f"{len(rows)} teams, {time.time() - t0:.1f}s"
    except Exception as e:
        return ("BLOCKED" if "timed out" in str(e).lower() or "Timeout" in type(e).__name__ else "FAIL"), f"{type(e).__name__}: {str(e)[:120]} after {time.time() - t0:.0f}s"


def main() -> int:
    results = [(name, use, *fetch(url)) for name, use, url in URLS]
    results.append(("stats.nba.com API (nba_api)", "player and team game logs, shot data (the big ingest)", *stats_api()))
    width = max(len(r[0]) for r in results)
    for name, use, verdict, detail in results:
        print(f"{verdict:8} {name:<{width}}  {detail}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"### NBA source reachability ({TODAY:%Y-%m-%d %H:%M} ET)\n\n| Result | Source | Used for | Detail |\n|---|---|---|---|\n")
            for name, use, verdict, detail in results:
                f.write(f"| {verdict} | {name} | {use} | {detail} |\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
