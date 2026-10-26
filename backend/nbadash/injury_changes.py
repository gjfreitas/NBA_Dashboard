"""What changed between consecutive official injury reports (a player's status moved, was added, or was removed).

Only the NBA's own reports are compared. Two things are deliberately not reported as changes, because they are not news:
- a team's first filing for a game (its block went from "not yet submitted" to filled in), and
- anything on a game date the earlier report did not cover at all (a new game day appearing).
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

from .injuries import flip, norm_name

SEVERITY = {"Out": 0, "Doubtful": 1, "Questionable": 2, "Probable": 3, "Available": 4}


def _team_key(row) -> object:
    return row["team_id"] if row["team_id"] else row["team_name"]


def _snapshot(conn: sqlite3.Connection, report_id: str) -> dict:
    """{'rows': {(date, team, player): row}, 'pending': {(date, team)}, 'dates': {date}} for one report."""
    rows = {}
    dates = set()
    for r in conn.execute("SELECT * FROM injuries WHERE report_id=?", (report_id,)):
        dates.add(r["game_date"])
        who = r["player_id"] or norm_name(flip(r["player_name"]))
        rows[(r["game_date"], _team_key(r), who)] = r
    pending = set()
    for p in conn.execute("SELECT * FROM injury_pending WHERE report_id=?", (report_id,)):
        dates.add(p["game_date"])
        pending.add((p["game_date"], p["team_id"] or p["team_name"]))
    return {"rows": rows, "pending": pending, "dates": dates}


def _event(kind: str, rep, row, from_status: Optional[str], to_status: Optional[str]) -> dict:
    return {"report_id": rep["report_id"], "at": rep["published_at"], "at_utc": rep["published_utc"], "kind": kind,
            "player_id": row["player_id"], "player_name": row["player_name"], "team_id": row["team_id"], "team_abbr": row["team_abbr"],
            "matchup": row["matchup"], "game_id": row["game_id"], "game_date": row["game_date"],
            "from_status": from_status, "to_status": to_status, "reason": row["reason"] or ""}


def diff_reports(prev: dict, new: dict, new_rep) -> list[dict]:
    out = []
    for key, row in new["rows"].items():
        date, team, _ = key
        was = prev["rows"].get(key)
        if was is not None:
            if was["status"] != row["status"]:
                worse = SEVERITY.get(row["status"], 9) < SEVERITY.get(was["status"], 9)
                out.append(_event("worsened" if worse else "improved", new_rep, row, was["status"], row["status"]))
        elif date in prev["dates"] and (date, team) not in prev["pending"]:
            out.append(_event("added", new_rep, row, None, row["status"]))
    for key, was in prev["rows"].items():
        date, team, _ = key
        if key not in new["rows"] and date in new["dates"] and (date, team) not in new["pending"]:
            out.append(_event("removed", new_rep, was, was["status"], None))
    return out


def recent_changes(conn: sqlite3.Connection, hours: float = 36, now: Optional[datetime] = None) -> list[dict]:
    """Changes between consecutive stored reports, newest first. The report just before the window is the baseline."""
    cutoff = ((now or datetime.now(timezone.utc)) - timedelta(hours=hours)).isoformat(timespec="seconds")
    reps = conn.execute("SELECT * FROM injury_reports ORDER BY published_utc").fetchall()
    first = next((i for i, r in enumerate(reps) if r["published_utc"] >= cutoff), len(reps))
    reps = reps[max(0, first - 1):]
    events: list[dict] = []
    prev = _snapshot(conn, reps[0]["report_id"]) if reps else None
    for a, b in zip(reps, reps[1:]):
        cur = _snapshot(conn, b["report_id"])
        events.extend(diff_reports(prev, cur, b))
        prev = cur
    events.reverse()  # newest report first; the order inside one report is stable
    return sorted(events, key=lambda e: e["at_utc"], reverse=True)
