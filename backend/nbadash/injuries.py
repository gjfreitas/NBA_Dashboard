"""The NBA's official injury report.

The league publishes a PDF every 15 minutes (index: official.nba.com/nba-injury-report-<season>-season/). Each lists, per game
and team, the players who are Out / Doubtful / Questionable / Probable / Available and why; teams that haven't filed yet show
"NOT YET SUBMITTED". We parse the PDF by word POSITION (it is a fixed-column table), not by text lines:

  * columns: Game Date | Game Time | Matchup | Team | Player Name | Current Status | Reason
  * date, time, matchup and team are printed only on the first row they apply to, so they are forward-filled
  * a reason that wraps is vertically CENTRED on its player's row (lines about 7 pt above and below the name),
    so a reason line belongs to the nearest player row, not the one above it

  python -m nbadash.injuries once       fetch the newest report if we don't have it yet
  python -m nbadash.injuries show       print the stored current report
"""
from __future__ import annotations

import argparse
import io
import logging
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from . import db, webget
from .ingest import current_season, previous_season

log = logging.getLogger("nbadash.injuries")
ET = ZoneInfo("America/New_York")
INDEX_URL = "https://official.nba.com/nba-injury-report-{season}-season/"
STATUSES = {"Out", "Doubtful", "Questionable", "Probable", "Available"}
REPORT_RE = re.compile(r"https?://[^\"'\s]*/Injury-Report_(\d{4}-\d{2}-\d{2})_(\d{2})_(\d{2})(AM|PM)\.pdf")
TITLE_RE = re.compile(r"Injury\s*Report:\s*(\d{1,2}/\d{1,2}/\d{2,4})\s+(\d{1,2}:\d{2})\s*(AM|PM)", re.I)
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}

# word x-position -> column. Starts come from the header row; these are the fallback if it can't be read.
DEFAULT_STARTS = {"date": 23, "time": 120, "matchup": 200, "team": 264, "player": 425, "status": 586, "reason": 666}
COLS = list(DEFAULT_STARTS)


@dataclass
class Entry:
    game_date: Optional[str]  # ISO date of the game (Eastern)
    game_time: Optional[str]  # as printed, e.g. "04:00(ET)"
    matchup: Optional[str]  # "CHI@MIL" = away@home
    team_name: Optional[str]  # as printed, spaces removed by the PDF in some cases ("Chicago Bulls")
    player_name: str  # "Last, First"
    status: str
    reason: str


@dataclass
class Pending:
    game_date: Optional[str]
    matchup: Optional[str]
    team_name: Optional[str]


@dataclass
class Report:
    published_at: datetime  # Eastern wall clock, naive
    entries: list[Entry] = field(default_factory=list)
    pending: list[Pending] = field(default_factory=list)


# ------------------------------------------------------------------------ parsing

def _cluster(words: list[dict], tol: float = 2.5) -> list[list[dict]]:
    """Group words that share a text line (same column) by their vertical position."""
    out: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if out and abs(w["top"] - out[-1][0]["top"]) <= tol:
            out[-1].append(w)
        else:
            out.append([w])
    return out


def _text(ws: list[dict]) -> str:
    return " ".join(w["text"] for w in sorted(ws, key=lambda w: w["x0"]))


def _column_starts(words: list[dict]) -> dict[str, float]:
    """x of each column from the header row (Game Date, Game Time, Matchup, Team, Player Name, Current Status, Reason)."""
    header = [w for w in words if w["text"] in ("Matchup",)]
    if not header:
        return dict(DEFAULT_STARTS)
    y = header[0]["top"]
    row = sorted((w for w in words if abs(w["top"] - y) < 3), key=lambda w: w["x0"])
    first = lambda text, nth=0: [w["x0"] for w in row if w["text"] == text][nth]  # noqa: E731
    try:
        return {"date": first("Game", 0), "time": first("Game", 1), "matchup": first("Matchup"), "team": first("Team"),
                "player": first("Player"), "status": first("Current"), "reason": first("Reason")}
    except IndexError:
        return dict(DEFAULT_STARTS)


def _column(x: float, starts: dict[str, float]) -> str:
    chosen = COLS[0]
    for name in COLS:
        if starts[name] <= x + 3:
            chosen = name
    return chosen


def _parse_date(s: str) -> str:
    fmt = "%m/%d/%Y" if len(s.split("/")[-1]) == 4 else "%m/%d/%y"
    return datetime.strptime(s, fmt).date().isoformat()


def parse_report(pdf_bytes: bytes) -> Report:
    import pdfplumber

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        first_text = pdf.pages[0].extract_text() or ""
        m = TITLE_RE.search(first_text)
        if not m:
            raise ValueError("not an NBA injury report: no 'Injury Report: <date> <time>' title")
        published = datetime.strptime(f"{_parse_date(m[1])} {m[2]} {m[3].upper()}", "%Y-%m-%d %I:%M %p")
        starts = None
        rows: list[dict] = []  # player rows and pending rows, in reading order across pages

        for page in pdf.pages:
            words = page.extract_words(x_tolerance=1.5, y_tolerance=2)
            if starts is None:
                starts = _column_starts(words)
            body_top = max((w["bottom"] for w in words if w["text"] in ("Matchup", "Reason")), default=0)
            # keep the table body: below the title / header row (page 1 only) and above the "Page n of m" footer (~y 538)
            words = [w for w in words if max(body_top, 70) < w["top"] < 525]
            by_col: dict[str, list[dict]] = {c: [] for c in COLS}
            for w in words:
                by_col[_column(w["x0"], starts)].append(w)

            # --- anchors: one per player ("Last, First"); a continuation fragment without a comma extends the nearest name
            anchors: list[dict] = []
            for cl in _cluster(by_col["player"]):
                t = _text(cl)
                if "," in t:
                    anchors.append({"y": cl[0]["top"], "name": t, "status": None, "reason": [], "ctx": {}})
                elif anchors and abs(cl[0]["top"] - anchors[-1]["y"]) <= 12:
                    anchors[-1]["name"] += " " + t
            for cl in _cluster(by_col["status"]):
                t = _text(cl)
                near = min(anchors, key=lambda a: abs(a["y"] - cl[0]["top"]), default=None)
                if near is not None and abs(near["y"] - cl[0]["top"]) <= 5 and near["status"] is None:
                    near["status"] = t

            # --- reason fragments -> nearest player row; "NOT YET SUBMITTED" makes a pending row instead
            pendings: list[dict] = []
            for cl in _cluster(by_col["reason"], tol=2.0):
                t = _text(cl)
                y = cl[0]["top"]
                if re.sub(r"\s", "", t).upper() == "NOTYETSUBMITTED":
                    pendings.append({"y": y, "pending": True, "ctx": {}})
                    continue
                near = min(anchors, key=lambda a: abs(a["y"] - y), default=None)
                if near is not None and abs(near["y"] - y) <= 13:
                    near["reason"].append((y, t))
                elif rows and rows[-1].get("name"):  # a cell split across the page break continues the previous player
                    rows[-1]["reason"].append((y + 1e6, t))

            page_rows = sorted(anchors + pendings, key=lambda r: r["y"])
            # --- context cells (date, time, matchup, team) belong to the row at the same height
            for col in ("date", "time", "matchup", "team"):
                for cl in _cluster(by_col[col]):
                    t = _text(cl)
                    if page_rows:
                        near = min(page_rows, key=lambda r: abs(r["y"] - cl[0]["top"]))
                        near["ctx"][col] = t
            rows += page_rows

    # --- forward-fill the context, build the report
    ctx = {"date": None, "time": None, "matchup": None, "team": None}
    report = Report(published_at=published)
    for r in rows:
        for col, val in r["ctx"].items():
            ctx[col] = val
        game_date = _parse_date(ctx["date"]) if ctx["date"] else None
        if r.get("pending"):
            report.pending.append(Pending(game_date, ctx["matchup"], ctx["team"]))
            continue
        reason = " ".join(t for _, t in sorted(r["reason"])).strip()
        report.entries.append(Entry(game_date, ctx["time"], ctx["matchup"], ctx["team"], r["name"], r["status"] or "", reason))
    return report


# --------------------------------------------------------------------- matching

def norm_name(s: str) -> str:
    """'Lively II, Dereck' / 'Dereck Lively II' / 'DERECK  LIVELY' -> 'dereck lively' (no accents, punctuation or Jr./II/III)."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    tokens = [re.sub(r"[^a-z0-9]", "", t) for t in re.split(r"[\s]+", s)]
    return " ".join(t for t in tokens if t and t not in SUFFIXES)


def flip(name: str) -> str:
    """'Last, First' -> 'First Last'; other shapes unchanged."""
    if "," in name:
        last, first = name.split(",", 1)
        return f"{first.strip()} {last.strip()}"
    return name


def _team_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def find_player(conn: sqlite3.Connection, full_name: str, team_abbr: Optional[str]) -> Optional[int]:
    """Our player id for a "First Last" name. The team (if known) breaks ties between namesakes; a unique league-wide
    match still counts (recent trade, stale roster); father and son (Jr./Sr. are not part of the match) are told apart by who is
    active; any other ambiguity is never guessed."""
    want = norm_name(full_name)
    cands = [r for r in conn.execute("SELECT id, full_name, team_abbr, is_active FROM players") if norm_name(r["full_name"]) == want]
    mine = [r for r in cands if team_abbr and r["team_abbr"] == team_abbr]
    active = [r for r in cands if r["is_active"]]
    pick = mine or (cands if len(cands) == 1 else []) or (active if len(active) == 1 else [])
    return pick[0]["id"] if len(pick) == 1 else None


def resolve(conn: sqlite3.Connection, e) -> dict:
    """Find team id/abbr (from the matchup + printed team name), game id and player id for one report entry."""
    out = {"team_id": None, "team_abbr": None, "game_id": None, "player_id": None}
    teams = {r["abbr"]: r for r in conn.execute("SELECT * FROM teams WHERE abbr IS NOT NULL")}
    away_home = (e.matchup or "").split("@")
    team = None
    for ab in away_home:
        t = teams.get(ab)
        if t and e.team_name and _team_key(e.team_name).endswith(_team_key(t["name"])):
            team = t
    if team is None and e.team_name:  # no matchup: match on the whole name
        key = _team_key(e.team_name)
        team = next((t for t in teams.values() if _team_key(t["city"] + t["name"]) == key), None)
    if team:
        out["team_id"], out["team_abbr"] = team["id"], team["abbr"]
    if len(away_home) == 2 and e.game_date:
        g = conn.execute("SELECT game_id FROM schedule WHERE game_date=? AND away_abbr=? AND home_abbr=?",
                         (e.game_date, away_home[0], away_home[1])).fetchone()
        out["game_id"] = g["game_id"] if g else None
    if getattr(e, "player_name", None):
        out["player_id"] = find_player(conn, flip(e.player_name), out["team_abbr"])
    return out


# ------------------------------------------------------------------------ storage

def list_reports(index_html: str) -> list[tuple[str, str, datetime]]:
    """(report_id, url, published ET) for every PDF on the index page, oldest first."""
    seen = {}
    for m in REPORT_RE.finditer(index_html):
        when = datetime.strptime(f"{m[1]} {m[2]}:{m[3]} {m[4]}", "%Y-%m-%d %I:%M %p")
        seen[f"{m[1]}_{m[2]}_{m[3]}{m[4]}"] = (m.group(0), when)
    return sorted(((rid, url, when) for rid, (url, when) in seen.items()), key=lambda t: t[2])


def store_report(conn: sqlite3.Connection, report_id: str, report: Report, fetched_at: Optional[str] = None,
                 published_at: Optional[datetime] = None) -> int:
    """published_at (Eastern, naive) is the time in the file name; it decides which report is the newest. The PDF's own title
    should agree, and a warning is logged if it doesn't."""
    if published_at is not None:
        if abs(published_at - report.published_at) > timedelta(minutes=30):
            log.warning("report %s: file name says %s but the PDF title says %s", report_id, published_at, report.published_at)
        report.published_at = published_at
    published_utc = report.published_at.replace(tzinfo=ET).astimezone(timezone.utc).isoformat(timespec="seconds")
    with conn:
        conn.execute("DELETE FROM injuries WHERE report_id=?", (report_id,))
        conn.execute("DELETE FROM injury_pending WHERE report_id=?", (report_id,))
        conn.execute("INSERT OR REPLACE INTO injury_reports VALUES (?,?,?,?,?,?)",
                     (report_id, report.published_at.isoformat(timespec="minutes"), published_utc,
                      fetched_at or datetime.now(timezone.utc).isoformat(timespec="seconds"), len(report.entries), len(report.pending)))
        for i, e in enumerate(report.entries):
            m = resolve(conn, e)
            conn.execute("INSERT INTO injuries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (report_id, i, e.game_date, e.game_time, e.matchup, m["game_id"], e.team_name, m["team_id"], m["team_abbr"],
                          e.player_name, m["player_id"], e.status, e.reason))
        for p in report.pending:
            m = resolve(conn, p)
            conn.execute("INSERT OR REPLACE INTO injury_pending VALUES (?,?,?,?,?)", (report_id, p.game_date, p.matchup, p.team_name, m["team_id"]))
    return len(report.entries)


def _listed(getter) -> list:
    """Reports on the NBA's index page for the current season (or the previous one in the off-season), oldest first."""
    for season in (current_season(), previous_season(current_season())):
        body = getter(INDEX_URL.format(season=season))
        reports = list_reports(body.decode("utf-8", "replace")) if body else []
        if reports:
            return reports
    return []


def _store_missing(conn: sqlite3.Connection, reports: list, getter, hours: float, newest: datetime) -> dict:
    """Store the listed reports from the `hours` before `newest` that we don't have. One request per missing PDF."""
    horizon = newest - timedelta(hours=hours)
    stored = skipped = 0
    for report_id, url, when in reports:
        if when < horizon or conn.execute("SELECT 1 FROM injury_reports WHERE report_id=?", (report_id,)).fetchone():
            continue
        pdf = getter(url)
        if pdf is None:
            skipped += 1
            continue
        try:
            store_report(conn, report_id, parse_report(pdf), published_at=when)
            stored += 1
        except ValueError as e:  # a PDF that isn't a report: skip it, keep going
            log.warning("report %s skipped: %s", report_id, e)
            skipped += 1
    return {"stored": stored, "skipped": skipped}


def sync_injuries(conn: sqlite3.Connection, getter: Optional[Callable[[str], Optional[bytes]]] = None, catch_up_hours: float = 0) -> dict:
    """Store the newest published report if we don't have it. Cheap when nothing is new: one small page fetch.
    With `catch_up_hours`, a new report also pulls in the reports we missed in that window (the machine was asleep), so the
    changes feed has no holes."""
    getter = getter or webget.fetch
    reports = _listed(getter)
    if not reports:
        return {"new": 0, "reason": "no reports listed"}
    report_id, url, when = reports[-1]
    if conn.execute("SELECT 1 FROM injury_reports WHERE report_id=?", (report_id,)).fetchone():
        return {"new": 0, "latest": report_id}
    pdf = getter(url)
    if pdf is None:
        return {"new": 0, "reason": f"{report_id} listed but not downloadable yet"}
    parsed = parse_report(pdf)
    n = store_report(conn, report_id, parsed, published_at=when)
    log.info("stored injury report %s: %d players, %d teams not yet submitted", report_id, n, len(parsed.pending))
    out = {"new": 1, "latest": report_id, "entries": n, "pending": len(parsed.pending)}
    if catch_up_hours:
        out["caught_up"] = _store_missing(conn, reports[:-1], getter, catch_up_hours, when)["stored"]
    return out


def backfill_injuries(conn: sqlite3.Connection, getter: Optional[Callable[[str], Optional[bytes]]] = None, hours: float = 24) -> dict:
    """Store every listed report from the last `hours` (back from the newest listed) that we don't have yet."""
    getter = getter or webget.fetch
    reports = _listed(getter)
    if not reports:
        return {"stored": 0, "reason": "no reports listed"}
    return _store_missing(conn, reports, getter, hours, reports[-1][2])


def latest_report(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM injury_reports ORDER BY published_utc DESC LIMIT 1").fetchone()


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="nbadash.injuries", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["once", "show", "backfill"])
    ap.add_argument("--db")
    ap.add_argument("--hours", type=float, default=24, help="backfill: how far back from the newest listed report")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    conn = db.connect(args.db)
    if args.cmd == "once":
        print(sync_injuries(conn))
        return 0
    if args.cmd == "backfill":
        print(backfill_injuries(conn, hours=args.hours))
        return 0
    rep = latest_report(conn)
    if not rep:
        print("no report stored")
        return 1
    print(f"report {rep['report_id']} ({rep['published_at']} ET): {rep['entries']} players, {rep['pending']} teams not yet submitted")
    for r in conn.execute("SELECT * FROM injuries WHERE report_id=? ORDER BY seq", (rep["report_id"],)):
        print(f"  {r['matchup'] or '':8} {r['team_abbr'] or '??':4} {r['player_name']:26} {r['status']:13} {r['reason']}  [{'id ' + str(r['player_id']) if r['player_id'] else 'UNMATCHED'}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
