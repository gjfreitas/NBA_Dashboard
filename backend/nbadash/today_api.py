"""The morning briefing: today's games with rest, key absences and lineup status, plus the biggest prop-line moves."""
from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import date as Date, datetime, timezone
from pathlib import Path
from typing import Iterator, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from . import db
from .availability_api import KeyAbsence, summaries_for
from .preview_api import build_context
from .slate_api import build_slate

ET = ZoneInfo("America/New_York")


class LineMove(BaseModel):
    player_id: Optional[int]
    name: str
    team_abbr: Optional[str]
    game_id: str
    market: str
    opening: float  # the line most books opened at
    now: float  # the line most books show now
    move: float
    books: int
    injury: Optional[str]  # official status, if the player is on the report


class TodayTeam(BaseModel):
    id: int
    abbr: Optional[str]
    name: str
    record: Optional[str]
    days_rest: Optional[int]
    back_to_back: bool
    streak: Optional[str]
    lineup_status: Optional[str]
    key_out: list[KeyAbsence]
    others_out: int


class TodayGame(BaseModel):
    game_id: str
    start_utc: Optional[str]
    status: int
    away: TodayTeam
    home: TodayTeam
    players_with_lines: int


class Today(BaseModel):
    date: str
    games: list[TodayGame]
    moves: list[LineMove]


def _mode(xs: list[float]) -> float:
    c = Counter(xs)
    top = max(c.values())
    srt = sorted(xs)
    median = srt[len(srt) // 2] if len(srt) % 2 else (srt[len(srt) // 2 - 1] + srt[len(srt) // 2]) / 2
    return min((x for x, n in c.items() if n == top), key=lambda x: (abs(x - median), x))


def line_moves(conn: sqlite3.Connection, day: str, min_move: float = 1.0, now: Optional[datetime] = None) -> list[LineMove]:
    """Players whose consensus line moved at least `min_move` since the books opened it, biggest first."""
    slate = build_slate(conn, day, now)
    out: list[LineMove] = []
    for g in slate.games:
        if g.status != 1:
            continue  # a game under way or finished: the pre-game line is no longer news
        for p in g.players:
            for market, m in p.markets.items():
                opened = _mode([b.opening_line for b in m.books])
                if abs(m.line - opened) >= min_move:
                    out.append(LineMove(player_id=p.player_id, name=p.name, team_abbr=p.team_abbr, game_id=g.game_id, market=market, opening=opened, now=m.line,
                                        move=round(m.line - opened, 2), books=len(m.books), injury=p.injury.status if p.injury else None))
    out.sort(key=lambda x: (-abs(x.move), x.name))
    return out


def build_today(conn: sqlite3.Connection, day: str, now: Optional[datetime] = None, moves_limit: int = 12) -> Today:
    games = conn.execute("SELECT * FROM schedule WHERE game_date=? ORDER BY start_utc, game_id", (day,)).fetchall()
    newest = conn.execute("SELECT MAX(season) FROM team_season").fetchone()[0]
    on = Date.fromisoformat(day)
    sums = {s.game_id: s for s in summaries_for(conn, [g["game_id"] for g in games])}
    lines_by_game = {r["game_id"]: r["n"] for r in conn.execute(
        "SELECT game_id, COUNT(DISTINCT COALESCE(player_id, player_name)) AS n FROM prop_lines WHERE game_id IN (SELECT game_id FROM schedule WHERE game_date=?) GROUP BY game_id", (day,))}

    def team(tid: int, abbr: Optional[str], summary) -> TodayTeam:
        t = conn.execute("SELECT city, name, abbr FROM teams WHERE id=?", (tid,)).fetchone()
        ts = conn.execute("SELECT w, l FROM team_season WHERE team_id=? AND season=?", (tid, newest)).fetchone() if newest else None
        ctx = build_context(conn, tid, newest, on) if newest else None
        return TodayTeam(id=tid, abbr=t["abbr"] if t else abbr, name=f"{t['city']} {t['name']}" if t else (abbr or str(tid)), record=f"{ts['w']}-{ts['l']}" if ts else None,
                         days_rest=ctx.days_rest if ctx else None, back_to_back=bool(ctx and ctx.back_to_back), streak=ctx.streak if ctx else None,
                         lineup_status=summary.lineup_status, key_out=[k for k in summary.key_players if k.status in ("Out", "Doubtful")], others_out=summary.others_out)

    out = []
    for g in games:
        s = sums.get(g["game_id"])
        if s is None:
            continue
        out.append(TodayGame(game_id=g["game_id"], start_utc=g["start_utc"], status=g["status"], away=team(g["away_id"], g["away_abbr"], s.away),
                             home=team(g["home_id"], g["home_abbr"], s.home), players_with_lines=lines_by_game.get(g["game_id"], 0)))
    return Today(date=day, games=out, moves=line_moves(conn, day, 1.0, now)[:moves_limit])


def make_router(db_path: Optional[str | Path] = None) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["today"])

    def conn() -> Iterator[sqlite3.Connection]:
        c = db.connect(db_path)
        try:
            yield c
        finally:
            c.close()

    def day_of(date: Optional[str]) -> str:
        return date or datetime.now(ET).date().isoformat()

    @router.get("/today", response_model=Today)
    def today(date: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"), c: sqlite3.Connection = Depends(conn)):
        """Today's games with rest and key absences, and the biggest line moves."""
        return build_today(c, day_of(date))

    @router.get("/lines/moves", response_model=list[LineMove])
    def moves(date: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"), min_move: float = Query(1.0, ge=0.5, le=20), limit: int = Query(50, ge=1, le=200),
              c: sqlite3.Connection = Depends(conn)):
        """Prop lines that moved at least `min_move` since opening, for the day's games that haven't started."""
        return line_moves(c, day_of(date), min_move)[:limit]

    return router
