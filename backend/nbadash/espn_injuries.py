"""ESPN's injury list, as a clearly-labelled SECONDARY source next to the official NBA report.

It adds what the NBA report doesn't have: an estimated return date, and injured players for teams the report doesn't cover yet
(teams without a game in its window, or that haven't filed). ESPN's own vocabulary is kept as it is: "Out" and "Day-To-Day"
(which lumps the NBA's Questionable / Probable / Doubtful together). Unofficial and undocumented.

We store only facts (who, team, status, injury, return date, when ESPN updated it). ESPN's written comments are third-party
editorial text, so they are neither stored nor shown.

  python -m nbadash.espn_injuries once     fetch now (unless fetched in the last hour)
  python -m nbadash.espn_injuries show
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from . import db, webget
from .injuries import _team_key, find_player

log = logging.getLogger("nbadash.espn")
URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
KIND = "espn_injuries"
VAGUE = {"not specified", "unspecified", "unknown", ""}


@dataclass
class EspnEntry:
    espn_id: str
    player_name: str
    team_name: str
    status: str  # "Out" | "Day-To-Day"
    injury: str  # "Left Foot Fracture"
    return_date: Optional[str]  # ISO date, ESPN's estimate
    updated_at: Optional[str]  # when ESPN last changed this entry (UTC ISO)


def injury_text(details: Optional[dict]) -> str:
    """{side: Left, type: Foot, detail: Fracture} -> 'Left Foot Fracture'; 'Not Specified' parts are dropped."""
    parts: list[str] = []
    for key in ("side", "type", "detail"):
        v = ((details or {}).get(key) or "").strip()
        if v.lower() not in VAGUE and v.lower() not in {p.lower() for p in parts}:
            parts.append(v)
    return " ".join(parts) or "Undisclosed"


def parse(data: dict) -> tuple[list[EspnEntry], Optional[str]]:
    """(entries, ESPN's own timestamp for the whole list)."""
    out = []
    for team in data.get("injuries", []):
        for e in team.get("injuries", []):
            a = e.get("athlete") or {}
            name = a.get("displayName") or f"{a.get('firstName', '')} {a.get('lastName', '')}".strip()
            if not name or not e.get("status"):
                continue
            rd = ((e.get("details") or {}).get("returnDate") or "")[:10] or None
            out.append(EspnEntry(espn_id=str(e.get("id")), player_name=name, team_name=team.get("displayName") or "", status=e["status"],
                                 injury=injury_text(e.get("details")), return_date=rd, updated_at=e.get("date")))
    return out, data.get("timestamp")


def resolve_team(conn: sqlite3.Connection, team_name: str) -> tuple[Optional[int], Optional[str]]:
    """ESPN names teams in full ('LA Clippers'); its abbreviations (GS, NO, NY...) differ from the NBA's, so use the name."""
    key = _team_key(team_name)
    for t in conn.execute("SELECT id, abbr, city, name FROM teams"):
        if _team_key(t["city"] + t["name"]) == key:
            return t["id"], t["abbr"]
    for t in conn.execute("SELECT id, abbr, name FROM teams"):  # 'Los Angeles Clippers' vs 'LA Clippers'
        if key.endswith(_team_key(t["name"])) and len([x for x in conn.execute("SELECT 1 FROM teams WHERE name=?", (t["name"],))]) == 1:
            return t["id"], t["abbr"]
    return None, None


def store(conn: sqlite3.Connection, entries: list[EspnEntry], snapshot_at: Optional[str], fetched_at: Optional[str] = None) -> int:
    """Replace the whole list: ESPN's page is a snapshot, so a player who is gone from it has recovered."""
    fetched = fetched_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    with conn:
        conn.execute("DELETE FROM espn_injuries")
        for e in entries:
            team_id, abbr = resolve_team(conn, e.team_name)
            pid = find_player(conn, e.player_name, abbr)
            conn.execute("INSERT OR REPLACE INTO espn_injuries VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                         (e.espn_id, e.player_name, pid, e.team_name, team_id, abbr, e.status, e.injury, e.return_date, e.updated_at, snapshot_at or fetched))
        conn.execute("INSERT OR REPLACE INTO sync VALUES (0, ?, ?)", (KIND, fetched))
    return len(entries)


def sync_espn(conn: sqlite3.Connection, getter: Optional[Callable[[str], Optional[bytes]]] = None, max_age: timedelta = timedelta(minutes=55),
              now: Optional[datetime] = None) -> dict:
    """Fetch ESPN's list at most once per max_age (the response is ~900 KB and ESPN changes it slowly)."""
    now = now or datetime.now(timezone.utc)
    last = conn.execute("SELECT synced_at FROM sync WHERE player_id=0 AND kind=?", (KIND,)).fetchone()
    if last and now - datetime.fromisoformat(last["synced_at"]) < max_age:
        return {"new": 0, "reason": "fresh"}
    body = (getter or webget.fetch)(URL)
    if body is None:
        return {"new": 0, "reason": "unavailable"}
    entries, snapshot = parse(json.loads(body))
    if not entries and conn.execute("SELECT COUNT(*) c FROM espn_injuries").fetchone()["c"]:
        return {"new": 0, "reason": "empty response; keeping the previous list"}  # never wipe good data on a blank answer
    n = store(conn, entries, snapshot, now.isoformat(timespec="seconds"))
    log.info("stored ESPN injuries: %d players (%d matched to our players)", n,
             conn.execute("SELECT COUNT(*) c FROM espn_injuries WHERE player_id IS NOT NULL").fetchone()["c"])
    return {"new": 1, "entries": n}


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="nbadash.espn_injuries", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["once", "show"])
    ap.add_argument("--db")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    conn = db.connect(args.db)
    if args.cmd == "once":
        print(sync_espn(conn))
        return 0
    for r in conn.execute("SELECT * FROM espn_injuries ORDER BY team_name, status, player_name"):
        print(f"  {r['team_abbr'] or '??':4} {r['player_name']:24} {r['status']:11} {r['injury']:28} back {r['return_date']}  [{'id ' + str(r['player_id']) if r['player_id'] else 'UNMATCHED'}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
