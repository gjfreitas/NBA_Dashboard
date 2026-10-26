"""Raw-JSON sources. The app only depends on the `Source` protocol, so a licensed
feed can replace the NBA CDN by implementing the same three methods."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Protocol

from curl_cffi import requests as cffi

CDN = "https://cdn.nba.com/static/json/liveData"
HEADERS = {"Referer": "https://www.nba.com/", "Origin": "https://www.nba.com"}


class NotAvailable(Exception):
    """Resource doesn't exist (yet), e.g. box score for a game that hasn't tipped off."""


class UpstreamError(Exception):
    """Network failure, timeout, or a block."""


class Source(Protocol):
    async def scoreboard(self) -> dict: ...
    async def boxscore(self, game_id: str) -> dict: ...
    async def playbyplay(self, game_id: str) -> dict: ...


class LiveSource:
    """cdn.nba.com via a browser-impersonating TLS client (plain requests/httpx get 403).

    A long-lived session can get stuck: during a real game this client was refused (403) on every request for ten minutes while a fresh
    connection from the same machine worked. So a refused or failed request renews the session (new connection, no stored cookies)
    and a refusal is retried once on the new one. Renewals are spaced at least RENEW_EVERY seconds apart."""

    RENEW_EVERY = 10.0

    def __init__(self, impersonate: str = "chrome", timeout: float = 8.0, session_factory=None):
        self._factory = session_factory or (lambda: cffi.AsyncSession(impersonate=impersonate, headers=HEADERS))
        self._session = self._factory()
        self._timeout = timeout
        self._renewed_at = 0.0
        self.renewals = 0

    async def _renew(self) -> bool:
        """Swap in a fresh session. False if one was made too recently."""
        now = time.monotonic()
        if now - self._renewed_at < self.RENEW_EVERY:
            return False
        old, self._session, self._renewed_at = self._session, self._factory(), now
        self.renewals += 1
        try:
            await old.close()
        except Exception:  # the old connection may already be dead
            pass
        return True

    async def _get(self, path: str) -> dict:
        for attempt in (0, 1):
            try:
                r = await self._session.get(f"{CDN}/{path}", timeout=self._timeout)
            except Exception as e:  # curl_cffi raises its own error hierarchy
                await self._renew()  # a connection that just failed is the first suspect
                raise UpstreamError(f"{path}: {type(e).__name__}: {e}") from e
            if r.status_code == 200:
                return r.json()
            if attempt == 0 and r.status_code in (403, 429) and await self._renew():
                continue  # maybe it was the session: ask again on a fresh one
            # The CDN answers 403 (not 404) for files that don't exist yet.
            if r.status_code in (403, 404) and not path.startswith("scoreboard/"):
                raise NotAvailable(path)
            raise UpstreamError(f"{path}: HTTP {r.status_code}")
        raise UpstreamError(f"{path}: no answer")  # unreachable

    async def scoreboard(self) -> dict:
        return await self._get("scoreboard/todaysScoreboard_00.json")

    async def boxscore(self, game_id: str) -> dict:
        return await self._get(f"boxscore/boxscore_{game_id}.json")

    async def playbyplay(self, game_id: str) -> dict:
        return await self._get(f"playbyplay/playbyplay_{game_id}.json")

    async def aclose(self) -> None:
        await self._session.close()


class ReplaySource:
    """Serves saved fixtures. With step > 0 the play-by-play grows by `step` actions
    per request, simulating a live game; step = 0 returns the full file."""

    def __init__(self, directory: Path, step: int = 0):
        self._dir = Path(directory)
        self._step = step
        self._served: dict[str, int] = {}

    def _load(self, name: str) -> dict:
        p = self._dir / name
        if not p.exists():
            raise NotAvailable(name)
        return json.loads(p.read_text(encoding="utf-8"))

    def _replay_ids(self) -> list[str]:
        return sorted(p.stem.removeprefix("boxscore_") for p in self._dir.glob("boxscore_*.json"))

    async def scoreboard(self) -> dict:
        raw = self._load("todaysScoreboard_00.json")
        games = raw["scoreboard"]["games"]
        known = {g["gameId"] for g in games}
        for gid in self._replay_ids():
            if gid in known:
                continue
            g = self._load(f"boxscore_{gid}.json")["game"]
            games.append({k: g[k] for k in ("gameId", "gameStatus", "gameStatusText", "period",
                                            "gameClock", "gameTimeUTC")} |
                         {"homeTeam": _slim(g["homeTeam"]), "awayTeam": _slim(g["awayTeam"])})
        return raw

    async def boxscore(self, game_id: str) -> dict:
        return self._load(f"boxscore_{game_id}.json")

    async def playbyplay(self, game_id: str) -> dict:
        raw = self._load(f"playbyplay_{game_id}.json")
        if self._step > 0:
            n = self._served.get(game_id, 0) + self._step
            self._served[game_id] = n
            raw["game"]["actions"] = raw["game"]["actions"][:n]
        return raw


def _slim(t: dict) -> dict:
    return {k: t.get(k) for k in ("teamId", "teamName", "teamCity", "teamTricode", "score", "periods")}
