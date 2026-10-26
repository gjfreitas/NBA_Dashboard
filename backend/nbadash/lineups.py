"""Daily starting lineups from the NBA (the file behind nba.com/players/todays-lineups).

  python -m nbadash.lineups once              fetch and store now
  python -m nbadash.lineups watch [--interval 60]   keep polling; prints every change and when it happened relative to tip-off
  python -m nbadash.lineups analyze           how long before tip-off do lineups first appear and become Confirmed?

One JSON file per slate date: stats.nba.com/js/data/leaders/00_daily_lineups_YYYYMMDD.json. A team's five starters are
"Expected" until the team confirms them. Every time a team's (status, starters) changes it is written to `lineup_events`
with the moment we saw it, which is how the Confirmed timing is measured.
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from . import db, webget

log = logging.getLogger("nbadash.lineups")
URL = "https://stats.nba.com/js/data/leaders/00_daily_lineups_{day}.json"
ET = ZoneInfo("America/New_York")


def et_today(now: Optional[datetime] = None) -> date:
    return (now or datetime.now(timezone.utc)).astimezone(ET).date()


def fetch_day(day: date, getter: Optional[Callable[[str], Optional[bytes]]] = None) -> Optional[dict]:
    """The lineup file for a slate date, or None when there isn't one (future dates are 404)."""
    body = (getter or webget.fetch)(URL.format(day=day.strftime("%Y%m%d")))
    return json.loads(body) if body else None


def is_starter(p: dict) -> bool:
    """Starters carry a court position; the file lists everyone else who played (after the game) with '-'."""
    return (p.get("position") or "-") not in ("", "-")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def store_lineups(conn: sqlite3.Connection, data: dict, observed_at: Optional[str] = None) -> list[dict]:
    """Replace each listed team's rows and return the changes seen (a team's status or starting five differing from last time)."""
    observed_at = observed_at or _now()
    changes = []
    with conn:
        for g in data.get("games", []):
            for side in ("homeTeam", "awayTeam"):
                t = g[side]
                players = t.get("players", [])
                starters = sorted(p["personId"] for p in players if is_starter(p))
                statuses = sorted({p.get("lineupStatus") or "" for p in players})
                status = statuses[0] if len(statuses) == 1 else "/".join(statuses)
                stamp = max((p.get("timestamp") or "" for p in players), default="")
                conn.execute("DELETE FROM lineups WHERE game_id=? AND team_id=?", (g["gameId"], t["teamId"]))
                for p in players:
                    conn.execute("INSERT OR REPLACE INTO lineups VALUES (?,?,?,?,?,?,?,?,?,?)",  # idempotent: the logger and the scheduled refresh both write, and a file may list a player twice
                                 (g["gameId"], t["teamId"], p["personId"], p.get("playerName"), p.get("position"),
                                  int(is_starter(p)), p.get("lineupStatus"), p.get("rosterStatus"), p.get("timestamp"), observed_at))
                last = conn.execute("SELECT status, starters FROM lineup_events WHERE game_id=? AND team_id=? ORDER BY id DESC LIMIT 1",
                                    (g["gameId"], t["teamId"])).fetchone()
                sig = json.dumps(starters)
                if players and (last is None or (last["status"], last["starters"]) != (status, sig)):
                    conn.execute("INSERT INTO lineup_events (game_id, team_id, status, starters, file_timestamp, observed_at) VALUES (?,?,?,?,?,?)",
                                 (g["gameId"], t["teamId"], status, sig, stamp, observed_at))
                    changes.append({"game_id": g["gameId"], "team": t["teamAbbreviation"], "status": status, "starters": starters,
                                    "previous": last["status"] if last else None, "file_timestamp": stamp})
    return changes


def poll(conn: sqlite3.Connection, now: Optional[datetime] = None, getter: Optional[Callable[[str], Optional[bytes]]] = None,
         days_back: int = 0) -> list[dict]:
    """Fetch today's and tomorrow's slate (and optionally earlier days) and store them. Returns the changes."""
    today = et_today(now)
    out = []
    for offset in range(-days_back, 2):
        data = fetch_day(today + timedelta(days=offset), getter)
        if data:
            out += store_lineups(conn, data, (now or datetime.now(timezone.utc)).isoformat(timespec="seconds"))
    return out


def tip_times(conn: sqlite3.Connection) -> dict[str, datetime]:
    return {r["game_id"]: datetime.fromisoformat(r["start_utc"].replace("Z", "+00:00"))
            for r in conn.execute("SELECT game_id, start_utc FROM schedule WHERE start_utc IS NOT NULL")}


def timing_report(conn: sqlite3.Connection) -> list[dict]:
    """Per game and team: when the lineup first appeared, when it became Confirmed, and whether the five changed in between."""
    tips = tip_times(conn)
    rows = conn.execute("SELECT e.*, t.abbr FROM lineup_events e LEFT JOIN teams t ON t.id = e.team_id ORDER BY e.game_id, e.team_id, e.id").fetchall()
    out: dict[tuple, dict] = {}
    for r in rows:
        key = (r["game_id"], r["team_id"])
        rec = out.setdefault(key, {"game_id": r["game_id"], "team": r["abbr"] or str(r["team_id"]), "tip": tips.get(r["game_id"]),
                                   "first_seen": r["observed_at"], "first_status": r["status"], "confirmed_at": None, "five_changed": False,
                                   "_first_five": r["starters"]})
        if r["status"] == "Confirmed" and rec["confirmed_at"] is None:
            rec["confirmed_at"] = r["observed_at"]
            rec["five_changed"] = r["starters"] != rec["_first_five"]
    for rec in out.values():
        tip = rec["tip"]
        rec.pop("_first_five")
        for k in ("first_seen", "confirmed_at"):
            if rec[k] and tip:
                rec[f"{k}_min_before_tip"] = round((tip - datetime.fromisoformat(rec[k])).total_seconds() / 60)
    return list(out.values())


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="nbadash.lineups", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["once", "watch", "analyze"])
    ap.add_argument("--interval", type=float, default=60, help="seconds between polls with watch (default 60)")
    ap.add_argument("--hours", type=float, help="with watch: stop after this many hours")
    ap.add_argument("--db")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    conn = db.connect(args.db)
    if args.cmd == "analyze":
        for r in timing_report(conn):
            print(f"{r['game_id']} {r['team']:4} tip {r['tip'] and r['tip'].strftime('%m-%d %H:%MZ')}  first seen {r['first_status']} {r.get('first_seen_min_before_tip')} min before tip"
                  f"  confirmed {r.get('confirmed_at_min_before_tip')} min before tip  five changed: {r['five_changed']}")
        return 0
    first = True
    deadline = time.monotonic() + args.hours * 3600 if args.hours else None
    while deadline is None or time.monotonic() < deadline:
        try:
            tips = tip_times(conn)
            for ch in poll(conn, days_back=1 if first else 0):
                tip = tips.get(ch["game_id"])
                mins = f"{round((tip - datetime.now(timezone.utc)).total_seconds() / 60)} min before tip" if tip else "tip unknown"
                log.info("%s %s: %s (was %s), starters %s [%s]", ch["game_id"], ch["team"], ch["status"], ch["previous"], ch["starters"], mins)
            first = False
        except (webget.FetchError, ValueError, sqlite3.Error) as e:  # a dropped request, a half-written file, a busy database: skip this tick, not the whole night
            log.warning("fetch failed: %s", e)
        if args.cmd == "once":
            return 0
        time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
