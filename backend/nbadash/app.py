"""FastAPI relay: cached, normalized NBA data + SSE live stream.

  NBA_SOURCE=live|replay   (default live)
  NBA_FIXTURES=<dir>       replay fixtures (default ../fixtures)
  NBA_REPLAY_STEP=<n>      actions revealed per PBP request in replay (0 = all)
  NBA_CORS_ORIGINS=a,b     allowed browser origins (default *)
  NBA_DB=<path>            SQLite file for player data (default backend/data/nba.db)
  NBA_SNAPSHOT=1           hosted mode: download the database from R2 at start-up and re-check every few minutes (see snapshot.py)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from . import db as dbmod, snapshot
from .cache import TTLCache
from .models import BoxScore, Game, Play
from .availability_api import make_router as availability_router
from .boost_api import make_router as boost_router
from .health import make_router as health_router
from .leaders_api import make_router as leaders_router
from .matchup_api import make_router as matchup_router
from .odds_api import make_router as odds_router
from .players_api import make_router as players_router
from .props_api import make_router as props_router
from .slate_api import make_router as slate_router
from .preview_api import make_router as preview_router
from .teams_api import make_router as teams_router
from .without_api import make_router as without_router
from .today_api import make_router as today_router
from .normalize import (normalize_boxscore, normalize_playbyplay,
                        normalize_scoreboard)
from .sources import LiveSource, NotAvailable, ReplaySource, Source, UpstreamError

LIVE_TTL = 2.0
SCOREBOARD_TTL = 5.0
FINAL_TTL = 3600.0
STREAM_INTERVAL = 2.0


def _box_ttl(raw: dict) -> float:
    return FINAL_TTL if raw["game"]["gameStatus"] == 3 else LIVE_TTL


def _pbp_ttl(raw: dict) -> float:
    actions = raw["game"]["actions"]
    ended = bool(actions) and actions[-1]["actionType"] == "game" and actions[-1]["subType"] == "end"
    return FINAL_TTL if ended else LIVE_TTL


def source_from_env() -> Source:
    if os.getenv("NBA_SOURCE", "live") == "replay":
        default = Path(__file__).resolve().parents[2] / "fixtures"
        return ReplaySource(Path(os.getenv("NBA_FIXTURES", default)),
                            step=int(os.getenv("NBA_REPLAY_STEP", "0")))
    return LiveSource()


def create_app(source: Optional[Source] = None, stream_interval: float = STREAM_INTERVAL,
               db_path: Optional[str] = None) -> FastAPI:
    src = source or source_from_env()
    cache = TTLCache()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        keeper = None
        store = snapshot.store_from_env() if os.getenv("NBA_SNAPSHOT") == "1" else None  # opt-in: a dev machine must never overwrite its own database
        if store is not None:
            path = Path(db_path) if db_path else dbmod.default_path()
            try:
                logging.getLogger("nbadash").info("snapshot at start-up: %s", await asyncio.to_thread(snapshot.restore, path, store))
            except Exception as e:  # serve what exists (or an empty database) rather than not start
                logging.getLogger("nbadash").warning("snapshot at start-up failed: %s: %s", type(e).__name__, e)
            keeper = asyncio.create_task(snapshot.keep_fresh(path, store))
        yield
        if keeper:
            keeper.cancel()
        close = getattr(src, "aclose", None)
        if close:
            await close()

    app = FastAPI(title="NBA Dashboard relay", version="0.1.0", lifespan=lifespan)
    origins = [o for o in os.getenv("NBA_CORS_ORIGINS", "*").split(",") if o]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET"])

    app.include_router(without_router(db_path))
    app.include_router(odds_router(db_path))  # before players: /api/players/{pid}/lines
    app.include_router(players_router(db_path))
    app.include_router(leaders_router(db_path))
    app.include_router(availability_router(db_path))
    app.include_router(health_router(db_path))
    app.include_router(slate_router(db_path))
    app.include_router(boost_router(db_path))
    app.include_router(today_router(db_path))
    app.include_router(props_router(db_path))
    app.include_router(matchup_router(db_path))
    app.include_router(preview_router(db_path))
    app.include_router(teams_router(db_path))

    @app.exception_handler(UpstreamError)
    async def _upstream(_: Request, exc: UpstreamError):
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "upstream unavailable", "error": str(exc)}, status_code=503)

    @app.exception_handler(NotAvailable)
    async def _na(_: Request, exc: NotAvailable):
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "not available yet"}, status_code=404)

    async def games() -> list[Game]:
        raw = await cache.get("scoreboard", src.scoreboard, lambda _: SCOREBOARD_TTL)
        out = []
        for g in normalize_scoreboard(raw):
            if g.state == "live":
                # The NBA's scoreboard file can run minutes behind the box score (seen in a real game: 8:03 left in Q1 while the box said 4:08),
                # so a live game takes its score and clock from the box score when that is further along.
                try:
                    fresh = (await box(g.id)).game
                    if fresh.state != "pre" and progress(fresh) >= progress(g):
                        g = fresh
                except (NotAvailable, UpstreamError):
                    pass
            out.append(g)
        return out

    async def box(game_id: str) -> BoxScore:
        raw = await cache.get(f"box:{game_id}", lambda: src.boxscore(game_id), _box_ttl)
        return normalize_boxscore(raw)

    async def plays(game_id: str) -> list[Play]:
        raw = await cache.get(f"pbp:{game_id}", lambda: src.playbyplay(game_id), _pbp_ttl)
        return normalize_playbyplay(raw)

    @app.get("/api/health")
    async def health():
        return {"ok": True, "source": type(src).__name__}

    @app.get("/api/scoreboard", response_model=list[Game])
    async def scoreboard():
        return await games()

    @app.get("/api/games/{game_id}/boxscore", response_model=BoxScore)
    async def boxscore(game_id: str):
        return await box(game_id)

    @app.get("/api/games/{game_id}/playbyplay", response_model=list[Play])
    async def playbyplay(game_id: str, after: int = Query(0, description="only plays with id > after"),
                         scoring_only: bool = False):
        out = [p for p in await plays(game_id) if p.id > after]
        return [p for p in out if p.points] if scoring_only else out

    @app.get("/api/games/{game_id}/stream")
    async def stream(game_id: str, request: Request, after: int = 0):
        """SSE. Events: `plays` (new or edited plays; upsert by id), `removed` (ids of plays the NBA deleted), `game` (score/clock), `end`."""

        async def gen() -> AsyncIterator[str]:
            seen: dict[int, Optional[str]] = {}
            last_game: Optional[str] = None
            floor = after
            while not await request.is_disconnected():
                try:
                    current = await plays(game_id)
                    fresh = [p for p in current if p.id > floor and p.id not in seen
                             or (p.id in seen and seen[p.id] != p.edited_utc)]
                    if fresh:
                        for p in fresh:
                            seen[p.id] = p.edited_utc
                        yield _sse("plays", [p.model_dump() for p in fresh])
                    # The NBA deletes plays after the fact (in a recorded game a made shot and a block-rebound sequence disappeared): tell the viewers
                    gone = sorted(set(seen) - {p.id for p in current})
                    if gone:
                        for i in gone:
                            del seen[i]
                        yield _sse("removed", gone)
                    g = next((g for g in await games() if g.id == game_id), None)
                    last = current[-1] if current else None
                    if g is None and last and last.type == "game" and last.subtype == "end" and not fresh:
                        yield _sse("end", {})  # finished game that is no longer on today's scoreboard
                        return
                    if g is not None:
                        payload = g.model_dump_json()
                        if payload != last_game:
                            last_game = payload
                            yield _sse("game", g.model_dump())
                        if g.state == "final" and not fresh:
                            yield _sse("end", {})
                            return
                except (NotAvailable, UpstreamError) as e:
                    yield _sse("status", {"available": False, "reason": type(e).__name__})
                await asyncio.sleep(stream_interval)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return app


def _secs(clock: str) -> int:
    m, _, sec = (clock or "0:00").partition(":")
    try:
        return int(m) * 60 + int(float(sec or 0))
    except ValueError:
        return 0


def progress(g: Game) -> int:
    """How far into the game, in seconds, a Game says it is (a finished game counts as the furthest)."""
    if g.state == "final":
        return 10 ** 9
    p = g.period or 0
    return (min(p, 4) * 720 + max(p - 4, 0) * 300) - _secs(g.clock) if p else 0


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


app = create_app() if os.getenv("NBA_AUTOCREATE", "1") == "1" else None
