# nbadash backend

Python relay: `curl_cffi` client for cdn.nba.com (browser TLS fingerprint required), normalizers to our own schema, TTL cache with single-flight + stale-if-error, FastAPI API with SSE, and fixture replay.

```bash
python -m pip install -e ".[dev]"
python -m pytest                                   # uses ../fixtures
NBA_SOURCE=live   python -m uvicorn nbadash.app:app --port 8000
NBA_SOURCE=replay NBA_REPLAY_STEP=10 python -m uvicorn nbadash.app:app --port 8000   # simulated live game
```

| Endpoint | Notes |
|---|---|
| `GET /api/scoreboard` | today's games (replay mode also lists fixture games) |
| `GET /api/games/{id}/boxscore` | 404 until the game has started |
| `GET /api/games/{id}/playbyplay?after=<id>&scoring_only=` | plays sorted by `id` |
| `GET /api/games/{id}/stream?after=<id>` | SSE: `plays` (upsert by id; includes edited plays), `game`, `status`, `end` |

Swap data providers by implementing `Source` (`sources.py`). Env vars are listed at the top of `app.py`.
