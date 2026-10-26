import json

from nbadash.record import analyze_deltas, diff_actions, snapshot_stats


def act(n, text="x", edited=None, order=None):
    return {"actionNumber": n, "orderNumber": order or n, "description": text, "edited": edited,
            "timeActual": "2026-10-22T20:00:00.000Z", "actionType": "2pt"}


def test_diff_new_changed_removed():
    prev = {1: act(1), 2: act(2), 3: act(3)}
    cur = [act(1), act(2, text="assist added", edited="2026-10-22T20:00:09.000Z"), act(4)]
    new, changed, removed = diff_actions(prev, cur)
    assert [a["actionNumber"] for a in new] == [4]
    assert [a["actionNumber"] for a in changed] == [2]
    assert removed == [3]


def test_snapshot_stats_edit_lag():
    acts = [act(1, edited="2026-10-22T20:00:10.000Z"), act(2, edited="2026-10-22T20:10:00.000Z"), act(4, edited=None)]
    s = snapshot_stats(acts)
    assert s["with_edited_ts"] == 2 and s["edited_after_creation(>2s)"] == 2
    assert s["edit_lag_s"]["max"] == 600 and s["action_number_gaps"] == 1


def test_analyze_deltas(tmp_path):
    recs = [
        {"t": 100.0, "poll": 0, "ok": True, "ms": 200, "n": 2, "new": [act(1), act(2)], "changed": [], "removed": []},
        {"t": 103.0, "poll": 1, "ok": True, "ms": 180, "n": 2, "new": [], "changed": [], "removed": []},
        {"t": 106.0, "poll": 2, "ok": True, "ms": 220, "n": 3, "new": [act(3, order=1)],
         "changed": [act(2, edited="1970-01-01T00:01:42.000Z")], "removed": []},
        {"t": 109.0, "poll": 3, "ok": False, "error": "timeout"},
    ]
    f = tmp_path / "deltas.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in recs), encoding="utf-8")
    r = analyze_deltas(f)
    assert (r["polls"], r["ok"], r["errors"]) == (4, 3, 1)
    assert r["new_actions"] == 3 and r["edited_actions_seen"] == 1
    assert r["seconds_between_updates"]["median"] == 6.0
    assert r["edit_detect_delay_s"]["median"] == 4.0  # edit stamped t=102, noticed at t=106


# ------------------------------------------------- the recorder must survive network blips while it waits

import asyncio  # noqa: E402

from nbadash import record as record_mod  # noqa: E402
from nbadash.sources import UpstreamError  # noqa: E402


class FakeSource:
    """Scoreboard: fails once, then 'no live game', then a live game, then final. Play-by-play: one small payload."""

    def __init__(self):
        self.board_calls = 0
        self.closed = False

    async def scoreboard(self):
        self.board_calls += 1
        if self.board_calls == 1:
            raise UpstreamError("scoreboard: Timeout")
        status = {2: 1, 3: 2}.get(self.board_calls, 3)  # call 2: pregame, 3: live, then final
        return {"scoreboard": {"games": [{"gameId": "0022600123", "gameStatus": status, "gameTimeUTC": "2026-10-24T01:00:00Z", "period": 1,
                                          "gameClock": "PT11M00.00S", "homeTeam": {"teamTricode": "HOM", "score": 2}, "awayTeam": {"teamTricode": "AWY", "score": 0}}]}}

    async def playbyplay(self, game_id):
        return {"game": {"actions": [act(1), act(2)]}}

    async def aclose(self):
        self.closed = True


def test_recorder_survives_a_scoreboard_timeout_while_waiting(tmp_path, monkeypatch):
    slept = []

    async def no_wait(seconds):
        slept.append(seconds)

    monkeypatch.setattr(record_mod, "_sleep", no_wait)
    src = FakeSource()
    asyncio.run(record_mod.record(None, interval=3, max_minutes=5, out_dir=tmp_path, src=src))
    assert src.board_calls >= 4 and src.closed  # it retried after the failure, waited, found the game, and recorded it
    assert slept[:2] == [60, 60]  # one retry sleep after the failure, one for "no live game yet"
    lines = (tmp_path / "0022600123" / "deltas.jsonl").read_text(encoding="utf-8").splitlines()
    assert lines and json.loads(lines[0])["n"] == 2 and len(json.loads(lines[0])["new"]) == 2


class DeadFeed(FakeSource):
    """A live game whose play-by-play file has gone missing (as a real one did for ten minutes)."""

    async def scoreboard(self):
        self.board_calls += 1
        status = 2 if self.board_calls <= 13 else 3
        return {"scoreboard": {"games": [{"gameId": "0022600123", "gameStatus": status, "gameTimeUTC": "2026-10-24T01:00:00Z", "period": 1, "gameClock": "PT11M00.00S",
                                          "homeTeam": {"teamTricode": "HOM", "score": 2}, "awayTeam": {"teamTricode": "AWY", "score": 0}}]}}

    async def playbyplay(self, game_id):
        from nbadash.sources import NotAvailable
        raise NotAvailable("gone")


def test_recorder_eases_off_when_the_feed_keeps_failing(tmp_path, monkeypatch):
    slept = []

    async def no_wait(seconds):
        slept.append(round(seconds))

    monkeypatch.setattr(record_mod, "_sleep", no_wait)
    asyncio.run(record_mod.record("0022600123", interval=3, max_minutes=5, out_dir=tmp_path, src=DeadFeed()))
    assert slept[:4] == [3, 3, 3, 3]  # the first failures are retried at the normal pace
    assert max(slept) > 3 and slept == sorted(slept)  # then it waits longer and longer, never shorter, while the file stays down
    assert max(slept) <= 30
    lines = (tmp_path / "0022600123" / "deltas.jsonl").read_text(encoding="utf-8").splitlines()
    assert all(json.loads(x)["error"] == "not_available" for x in lines)  # every outage poll is still logged
