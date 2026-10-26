import asyncio
import json

import httpx
import pytest

from nbadash.app import create_app
from nbadash.cache import TTLCache
from nbadash.sources import NotAvailable, ReplaySource, UpstreamError

GAME = "0022600001"


@pytest.fixture
def client_factory(fixtures_dir):
    def make(step=0):
        app = create_app(ReplaySource(fixtures_dir, step=step), stream_interval=0.01)
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    return make


async def test_endpoints(client_factory):
    async with client_factory() as c:
        games = (await c.get("/api/scoreboard")).json()
        assert {g["id"] for g in games} >= {GAME, "0022600006"}
        box = (await c.get(f"/api/games/{GAME}/boxscore")).json()
        assert box["game"]["state"] == "final"
        allp = (await c.get(f"/api/games/{GAME}/playbyplay")).json()
        floor = allp[len(allp) // 2]["id"]
        tail = (await c.get(f"/api/games/{GAME}/playbyplay", params={"after": floor})).json()
        assert {p["id"] for p in tail} == {p["id"] for p in allp if p["id"] > floor}  # `after` filters by id
        scoring = (await c.get(f"/api/games/{GAME}/playbyplay", params={"scoring_only": True})).json()
        assert scoring and all(p["points"] > 0 for p in scoring)


async def test_missing_game_is_404(client_factory):
    async with client_factory() as c:
        assert (await c.get("/api/games/0029999999/boxscore")).status_code == 404


async def test_stream_replays_whole_game_then_ends(client_factory):
    async with client_factory(step=150) as c:
        events, seen = [], set()
        async with c.stream("GET", f"/api/games/{GAME}/stream") as r:
            assert r.headers["content-type"].startswith("text/event-stream")
            ev = None
            async for line in r.aiter_lines():
                if line.startswith("event: "):
                    ev = line[7:]
                elif line.startswith("data: "):
                    data = json.loads(line[6:])
                    events.append(ev)
                    if ev == "plays":
                        seen.update(p["id"] for p in data)
        full = (await c.get(f"/api/games/{GAME}/playbyplay")).json()
        assert events[-1] == "end" and "game" in events
        assert seen == {p["id"] for p in full}


async def test_cache_single_flight_and_stale():
    now = [0.0]
    cache = TTLCache(clock=lambda: now[0])
    calls = 0

    async def fetch():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return calls

    results = await asyncio.gather(*[cache.get("k", fetch, lambda _: 2) for _ in range(20)])
    assert calls == 1 and set(results) == {1}
    now[0] = 3.0

    async def broken():
        raise UpstreamError("boom")

    assert await cache.get("k", broken, lambda _: 2) == 1  # stale served
    with pytest.raises(UpstreamError):
        await cache.get("fresh", broken, lambda _: 2)
    with pytest.raises(NotAvailable):
        async def na():
            raise NotAvailable("x")
        await cache.get("na", na, lambda _: 2)


# ---------------------------------------------- a stale NBA scoreboard must not hold a live game back

class LagSource(ReplaySource):
    """The scoreboard says Q1 8:03 (6-13); the box score is further on: Q1 4:08 (11-24). Optionally the box score is unavailable or behind."""

    def __init__(self, fixtures_dir, box_state=(1, "PT04M08.00S", 11, 24), box_fails=False):
        super().__init__(fixtures_dir)
        self.box_state, self.box_fails = box_state, box_fails

    async def scoreboard(self):
        raw = json.loads(json.dumps(await super().scoreboard()))
        g = next(x for x in raw["scoreboard"]["games"] if x["gameId"] == GAME)
        g.update(gameStatus=2, period=1, gameClock="PT08M03.00S")
        g["awayTeam"]["score"], g["homeTeam"]["score"] = 6, 13
        return raw

    async def boxscore(self, game_id):
        if self.box_fails:
            raise UpstreamError("box score down")
        raw = json.loads(json.dumps(await super().boxscore(game_id)))
        period, clock, away, home = self.box_state
        raw["game"].update(gameStatus=2, period=period, gameClock=clock)
        raw["game"]["awayTeam"]["score"], raw["game"]["homeTeam"]["score"] = away, home
        return raw


async def live_game(src):
    app = create_app(src, stream_interval=0.01)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        return next(g for g in (await c.get("/api/scoreboard")).json() if g["id"] == GAME)


async def test_a_live_game_takes_the_further_along_box_score(fixtures_dir):
    g = await live_game(LagSource(fixtures_dir))
    assert (g["period"], g["clock"], g["away"]["score"], g["home"]["score"], g["state"]) == (1, "4:08", 11, 24, "live")


async def test_the_scoreboard_stays_when_it_is_ahead_or_the_box_score_is_down(fixtures_dir):
    behind = await live_game(LagSource(fixtures_dir, box_state=(1, "PT10M00.00S", 2, 4)))  # the box score is older than the board
    assert (behind["clock"], behind["home"]["score"]) == ("8:03", 13)
    down = await live_game(LagSource(fixtures_dir, box_fails=True))
    assert (down["clock"], down["home"]["score"]) == ("8:03", 13)  # no box score: the scoreboard is better than nothing
    later_period = await live_game(LagSource(fixtures_dir, box_state=(2, "PT11M00.00S", 30, 40)))
    assert (later_period["period"], later_period["clock"]) == (2, "11:00")


def test_progress_orders_periods_clocks_and_overtime():
    import types
    from nbadash.app import progress

    def g(period, clock, state="live"):
        return types.SimpleNamespace(period=period, clock=clock, state=state)
    assert progress(g(1, "8:03")) < progress(g(1, "4:08")) < progress(g(2, "11:59")) < progress(g(4, "0:01")) < progress(g(5, "4:00")) < progress(g(6, "5:00"))
    assert progress(g(0, "")) == 0 and progress(g(4, "0:00", "final")) > progress(g(7, "0:01"))


# ---------------------------------------------- a refused session is replaced, not kept

class FakeResp:
    def __init__(self, status, body=None):
        self.status_code, self._body = status, body or {}

    def json(self):
        return self._body


class FakeSession:
    """`ok` sessions answer 200; the others answer `status` (a poisoned session)."""

    def __init__(self, ok, status=403):
        self.ok, self.status, self.closed, self.calls = ok, status, False, 0

    async def get(self, url, timeout=None):
        self.calls += 1
        return FakeResp(200, {"url": url}) if self.ok else FakeResp(self.status)

    async def close(self):
        self.closed = True


async def test_a_refused_session_is_renewed_and_the_request_retried():
    from nbadash.sources import LiveSource
    made = []

    def factory():
        made.append(FakeSession(ok=len(made) > 0))  # the first session is poisoned, every later one works
        return made[-1]
    src = LiveSource(session_factory=factory)
    out = await src.playbyplay("0022600099")
    assert out["url"].endswith("playbyplay/playbyplay_0022600099.json")
    assert (len(made), made[0].closed, made[0].calls, made[1].calls, src.renewals) == (2, True, 1, 1, 1)


async def test_renewals_are_spaced_and_a_missing_file_is_still_not_available(monkeypatch):
    from nbadash import sources
    from nbadash.sources import LiveSource
    clock = [100.0]
    monkeypatch.setattr(sources.time, "monotonic", lambda: clock[0])
    made = []

    def factory():
        made.append(FakeSession(ok=False, status=403))  # a file that really doesn't exist: every session gets 403
        return made[-1]
    src = LiveSource(session_factory=factory)
    with pytest.raises(NotAvailable):
        await src.playbyplay("G")
    assert src.renewals == 1 and sum(m.calls for m in made) == 2  # asked once, renewed, asked once more, then gave up
    with pytest.raises(NotAvailable):
        await src.playbyplay("G")  # 0 seconds later: no second renewal, no retry
    assert src.renewals == 1 and sum(m.calls for m in made) == 3
    clock[0] += 11
    with pytest.raises(NotAvailable):
        await src.playbyplay("G")
    assert src.renewals == 2


async def test_a_network_error_renews_the_session_and_is_reported():
    from nbadash.sources import LiveSource

    class Boom(FakeSession):
        async def get(self, url, timeout=None):
            raise OSError("connection reset")
    made = []

    def factory():
        made.append(Boom(ok=False))
        return made[-1]
    src = LiveSource(session_factory=factory)
    with pytest.raises(UpstreamError, match="connection reset"):
        await src.scoreboard()
    assert src.renewals == 1 and len(made) == 2


# ---------------------------------------------- plays the NBA deletes must disappear from viewers

class ShrinkingFeed(ReplaySource):
    """The first answer has ten plays; later answers lack the fourth (as a real game's feed did when the NBA removed plays)."""

    def __init__(self, fixtures_dir):
        super().__init__(fixtures_dir)
        self.calls = 0

    async def playbyplay(self, game_id):
        raw = json.loads(json.dumps(await super().playbyplay(game_id)))
        acts = raw["game"]["actions"][:10]
        self.calls += 1
        self.dropped = acts[3]["actionNumber"]
        if self.calls > 1:
            acts = acts[:3] + acts[4:]
        raw["game"]["actions"] = acts
        return raw


async def test_stream_announces_plays_the_nba_removed(fixtures_dir, monkeypatch):
    from nbadash import app as app_mod
    monkeypatch.setattr(app_mod, "LIVE_TTL", 0.0)  # fetch the play-by-play on every pass
    src = ShrinkingFeed(fixtures_dir)
    app = create_app(src, stream_interval=0.01)
    events = []
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        async with c.stream("GET", f"/api/games/{GAME}/stream") as r:
            ev = None
            async for line in r.aiter_lines():
                if line.startswith("event: "):
                    ev = line[7:]
                elif line.startswith("data: "):
                    events.append((ev, json.loads(line[6:])))
    sent = [i for e, d in events if e == "plays" for i in (p["id"] for p in d)]
    removed = [d for e, d in events if e == "removed"]
    assert src.dropped in sent  # it was shown ...
    assert removed == [[src.dropped]]  # ... and then taken back, once
    assert [e for e, _ in events].index("removed") > [e for e, _ in events].index("plays")
