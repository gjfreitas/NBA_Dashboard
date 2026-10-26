"""Tonight's slate with every player's prop lines: the best price per market, and every book's line behind it.

Built from the stored snapshots (`nbadash.odds`); nothing here calls an odds provider.
"""
from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from . import db
from .availability_api import report_meta
from .injuries import latest_report

ET = ZoneInfo("America/New_York")
STALE_AFTER = timedelta(hours=36)
POSITION_SHORT = {"Guard": "G", "Forward": "F", "Center": "C"}


class BookLine(BaseModel):
    book: str
    line: float
    over_price: Optional[int]
    under_price: Optional[int]
    opening_line: float
    updated_at: Optional[str]


class Price(BaseModel):
    book: str
    price: int


class MarketLines(BaseModel):
    line: float  # the line most books agree on
    best_over: Optional[Price]  # best (highest) over price among the books at that line
    best_under: Optional[Price]
    books: list[BookLine]  # every book, nearest the consensus first


class SlateInjury(BaseModel):
    status: str
    reason: str


class SlatePlayer(BaseModel):
    player_id: Optional[int]
    name: str
    position: Optional[str]
    team_abbr: Optional[str]
    injury: Optional[SlateInjury]
    markets: dict[str, MarketLines]


class SlateTeam(BaseModel):
    id: int
    abbr: Optional[str]
    name: str


class SlateGame(BaseModel):
    game_id: str
    start_utc: Optional[str]
    status: int  # 1 not started, 2 live, 3 final
    away: SlateTeam
    home: SlateTeam
    players: list[SlatePlayer]


class Slate(BaseModel):
    date: str
    as_of: Optional[str]  # newest stored line
    games: list[SlateGame]


def short_position(pos: Optional[str]) -> Optional[str]:
    """'Guard-Forward' -> 'G-F'"""
    if not pos:
        return None
    return "-".join(POSITION_SHORT.get(p, p[:1]) for p in pos.split("-"))


def market_lines(rows: list[dict]) -> MarketLines:
    """Consensus line = the most common line (a tie goes to the one nearest the median); best prices are the highest at that line."""
    lines = sorted(r["line"] for r in rows)
    median = lines[len(lines) // 2] if len(lines) % 2 else (lines[len(lines) // 2 - 1] + lines[len(lines) // 2]) / 2
    counts = Counter(lines)
    top = max(counts.values())
    line = min((ln for ln, n in counts.items() if n == top), key=lambda ln: (abs(ln - median), ln))
    at = [r for r in rows if r["line"] == line]
    over = max((r for r in at if r["over_price"] is not None), key=lambda r: r["over_price"], default=None)
    under = max((r for r in at if r["under_price"] is not None), key=lambda r: r["under_price"], default=None)
    books = sorted(rows, key=lambda r: (abs(r["line"] - line), r["book"]))
    return MarketLines(line=line, best_over=Price(book=over["book"], price=over["over_price"]) if over else None,
                       best_under=Price(book=under["book"], price=under["under_price"]) if under else None,
                       books=[BookLine(book=r["book"], line=r["line"], over_price=r["over_price"], under_price=r["under_price"],
                                       opening_line=r["opening_line"], updated_at=r["updated_at"]) for r in books])


def build_slate(conn: sqlite3.Connection, day: str, now: Optional[datetime] = None) -> Slate:
    now = now or datetime.now(timezone.utc)
    cutoff = (now - STALE_AFTER).isoformat(timespec="seconds")
    games = conn.execute("SELECT * FROM schedule WHERE game_date=? ORDER BY start_utc, game_id", (day,)).fetchall()
    if not games:
        return Slate(date=day, as_of=None, games=[])
    gids = [g["game_id"] for g in games]
    ph = ",".join("?" * len(gids))
    latest = conn.execute(
        f"SELECT * FROM prop_lines WHERE id IN (SELECT MAX(id) FROM prop_lines WHERE game_id IN ({ph}) AND seen_at >= ? GROUP BY COALESCE(player_id, player_name), market, book, game_id)",  # one player, whichever way each provider spells the name
        [*gids, cutoff]).fetchall()
    opening = {(r["game_id"], r["who"], r["market"], r["book"]): r["line"] for r in conn.execute(
        f"SELECT game_id, COALESCE(player_id, player_name) AS who, market, book, line FROM prop_lines WHERE id IN (SELECT MIN(id) FROM prop_lines WHERE game_id IN ({ph}) "
        f"GROUP BY game_id, COALESCE(player_id, player_name), market, book)", gids)}
    ids = sorted({r["player_id"] for r in latest if r["player_id"]})
    info = {r["id"]: r for r in conn.execute(f"SELECT id, full_name, position, team_abbr FROM players WHERE id IN ({','.join('?' * len(ids))})", ids)} if ids else {}
    rep = latest_report(conn)
    hurt: dict[int, SlateInjury] = {}
    if rep is not None and not report_meta(rep, now).stale:
        for r in conn.execute("SELECT player_id, status, reason FROM injuries WHERE report_id=? AND player_id IS NOT NULL", (rep["report_id"],)):
            hurt[r["player_id"]] = SlateInjury(status=r["status"], reason=r["reason"] or "")

    out: list[SlateGame] = []
    for g in games:
        # (player key) -> market -> rows
        by_player: dict[tuple, dict[str, list[dict]]] = {}
        for r in (x for x in latest if x["game_id"] == g["game_id"]):
            key = (r["player_id"], r["player_id"] or r["player_name"])
            by_player.setdefault(key, {}).setdefault(r["market"], []).append({
                "book": r["book"], "line": r["line"], "over_price": r["over_price"], "under_price": r["under_price"],
                "opening_line": opening.get((r["game_id"], r["player_id"] or r["player_name"], r["market"], r["book"]), r["line"]), "updated_at": r["book_updated_at"] or r["seen_at"]})
        players = []
        for (pid, who), markets in by_player.items():
            name = who if isinstance(who, str) else None
            p = info.get(pid)
            team = p["team_abbr"] if p and p["team_abbr"] in (g["home_abbr"], g["away_abbr"]) else None
            players.append(SlatePlayer(player_id=pid, name=(p["full_name"] if p else name or str(pid)), position=short_position(p["position"]) if p else None,
                                       team_abbr=team, injury=hurt.get(pid) if pid else None, markets={m: market_lines(rs) for m, rs in markets.items()}))
        players.sort(key=lambda p: (-(p.markets["pts"].line if "pts" in p.markets else max(m.line for m in p.markets.values())), p.name))
        t = {tid: conn.execute("SELECT id, abbr, city, name FROM teams WHERE id=?", (tid,)).fetchone() for tid in (g["away_id"], g["home_id"])}
        team = lambda tid, ab: SlateTeam(id=tid, abbr=(t[tid]["abbr"] if t[tid] else ab), name=f"{t[tid]['city']} {t[tid]['name']}" if t[tid] else (ab or str(tid)))  # noqa: E731
        out.append(SlateGame(game_id=g["game_id"], start_utc=g["start_utc"], status=g["status"], away=team(g["away_id"], g["away_abbr"]),
                             home=team(g["home_id"], g["home_abbr"]), players=players))
    return Slate(date=day, as_of=max((r["seen_at"] for r in latest), default=None), games=out)


class GameProps(BaseModel):
    game: SlateGame
    avg_min: dict[int, float]  # minutes per game for the players on the list, from the newest season they have played in


def game_props(conn: sqlite3.Connection, game_id: str, now: Optional[datetime] = None) -> Optional[GameProps]:
    """One game's prop lines (the same shape as a slate game) plus each player's usual minutes, for the live tracker."""
    g = conn.execute("SELECT game_date FROM schedule WHERE game_id=?", (game_id,)).fetchone()
    if g is None:
        return None
    game = next((x for x in build_slate(conn, g["game_date"], now).games if x.game_id == game_id), None)
    if game is None:
        return None
    ids = sorted({p.player_id for p in game.players if p.player_id})
    mins: dict[int, float] = {}
    if ids:
        for r in conn.execute(f"SELECT player_id, min, gp, season FROM league_players WHERE player_id IN ({','.join('?' * len(ids))}) AND min IS NOT NULL ORDER BY season", ids):
            if (r["gp"] or 0) >= 5:  # a handful of games says little about usual minutes: keep the earlier season's figure until there are 5
                mins[r["player_id"]] = r["min"]
    return GameProps(game=game, avg_min=mins)


def make_router(db_path: Optional[str | Path] = None) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["slate"])

    def conn() -> Iterator[sqlite3.Connection]:
        c = db.connect(db_path)
        try:
            yield c
        finally:
            c.close()

    @router.get("/slate", response_model=Slate)
    def slate(date: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"), c: sqlite3.Connection = Depends(conn)):
        """The day's games (Eastern date, default today) with each player's sportsbook lines. Players without lines are not listed."""
        return build_slate(c, date or datetime.now(ET).date().isoformat())

    @router.get("/games/{game_id}/props", response_model=GameProps)
    def props(game_id: str, c: sqlite3.Connection = Depends(conn)):
        """The game's prop lines and the players' usual minutes. Empty `players` when no lines are stored."""
        gp = game_props(c, game_id)
        if gp is None:
            raise HTTPException(404, "game not in the schedule")
        return gp

    return router
