"""Stored prop lines over HTTP (filled by `nbadash.odds`)."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from . import db

STALE_AFTER = timedelta(hours=36)  # lines older than this are not "the line" any more


class BookLine(BaseModel):
    book: str
    line: float
    over_price: Optional[int]
    under_price: Optional[int]
    opening_line: float
    updated_at: Optional[str]  # the book's own timestamp when the provider gave one, else when we saw it


class PlayerLines(BaseModel):
    game_id: Optional[str]
    source: Optional[str]
    as_of: Optional[str]  # when we last stored a change for this player
    markets: dict[str, list[BookLine]]  # our market key (pts, reb, ast, ...) -> one line per book


def player_lines(conn: sqlite3.Connection, player_id: int, now: Optional[datetime] = None) -> PlayerLines:
    """The player's newest line per book for his next game that has any (a game not yet started, lines seen recently)."""
    now = now or datetime.now(timezone.utc)
    cutoff = (now - STALE_AFTER).isoformat(timespec="seconds")
    game = conn.execute(
        "SELECT p.game_id FROM prop_lines p JOIN schedule s ON s.game_id = p.game_id WHERE p.player_id=? AND s.status=1 AND p.seen_at >= ? "
        "ORDER BY s.game_date, s.start_utc LIMIT 1", (player_id, cutoff)).fetchone()
    if game is None:
        return PlayerLines(game_id=None, source=None, as_of=None, markets={})
    rows = conn.execute(
        "SELECT * FROM prop_lines WHERE id IN (SELECT MAX(id) FROM prop_lines WHERE player_id=? AND game_id=? GROUP BY market, book) "  # the newest, whichever provider
        "ORDER BY market, book", (player_id, game["game_id"])).fetchall()
    out: dict[str, list[BookLine]] = {}
    for r in rows:
        first = conn.execute("SELECT line FROM prop_lines WHERE source=? AND event_id=? AND player_name=? AND market=? AND book=? ORDER BY id LIMIT 1",
                             (r["source"], r["event_id"], r["player_name"], r["market"], r["book"])).fetchone()
        out.setdefault(r["market"], []).append(BookLine(book=r["book"], line=r["line"], over_price=r["over_price"], under_price=r["under_price"],
                                                        opening_line=first["line"], updated_at=r["book_updated_at"] or r["seen_at"]))
    return PlayerLines(game_id=game["game_id"], source="+".join(sorted({r["source"] for r in rows})) or None, as_of=max((r["seen_at"] for r in rows), default=None), markets=out)


def make_router(db_path: Optional[str | Path] = None) -> APIRouter:
    router = APIRouter(prefix="/api/players", tags=["odds"])

    def conn() -> Iterator[sqlite3.Connection]:
        c = db.connect(db_path)
        try:
            yield c
        finally:
            c.close()

    @router.get("/{pid}/lines", response_model=PlayerLines)
    def lines(pid: int, c: sqlite3.Connection = Depends(conn)):
        """Sportsbook prop lines for the player's next game, one per book and market. Empty when no odds API is configured or none are posted yet."""
        return player_lines(c, pid)

    return router
