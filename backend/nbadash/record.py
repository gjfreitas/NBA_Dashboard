"""Record and analyze real live play-by-play polling.

  python -m nbadash.record record [--game ID] [--interval 3] [--max-minutes 200]
      waits for a live game (or the given one), polls its play-by-play and writes
      fixtures/live/<game>/{first.json, last.json, deltas.jsonl}
  python -m nbadash.record analyze fixtures/live/<game>      # polling cadence + edit behaviour
  python -m nbadash.record snapshot fixtures/playbyplay_X.json   # edit stats from one finished-game file
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .sources import LiveSource, NotAvailable, UpstreamError

DEFAULT_OUT = Path(__file__).resolve().parents[2] / "fixtures" / "live"


def _ts(s: Optional[str]) -> Optional[float]:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() if s else None


def diff_actions(prev: dict[int, dict], cur: list[dict]) -> tuple[list[dict], list[dict], list[int]]:
    """(new, changed, removed_ids). `changed` = same actionNumber whose content differs."""
    seen = {a["actionNumber"]: a for a in cur}
    new = [a for n, a in seen.items() if n not in prev]
    changed = [a for n, a in seen.items() if n in prev and prev[n] != a]
    removed = [n for n in prev if n not in seen]
    return new, changed, removed


# ------------------------------------------------------------------ record ----

_sleep = asyncio.sleep  # a module-level name so tests can make waiting instant

async def record(game_id: Optional[str], interval: float, max_minutes: float, out_dir: Path, src=None) -> None:
    src = src or LiveSource()
    try:
        # 1) wait for a live game
        while game_id is None:
            try:
                sb = await src.scoreboard()
            except UpstreamError as e:  # the wait can last a day: one dropped request must not end the recording
                print(f"{datetime.now():%H:%M:%S} scoreboard unavailable ({str(e)[:80]}); retrying", flush=True)
                await _sleep(60)
                continue
            live = [g for g in sb["scoreboard"]["games"] if g["gameStatus"] == 2]
            if live:
                game_id = live[0]["gameId"]
                print(f"live game: {game_id} {live[0]['awayTeam']['teamTricode']} @ {live[0]['homeTeam']['teamTricode']}", flush=True)
            else:
                nxt = min((g["gameTimeUTC"] for g in sb["scoreboard"]["games"] if g["gameStatus"] == 1), default="none today")
                print(f"{datetime.now():%H:%M:%S} no live game; next tip-off {nxt}", flush=True)
                await _sleep(60)
        out = out_dir / game_id
        out.mkdir(parents=True, exist_ok=True)
        deltas = (out / "deltas.jsonl").open("a", encoding="utf-8")

        prev: dict[int, dict] = {}
        deadline = time.monotonic() + max_minutes * 60
        first_saved = False
        raw: dict[str, Any] = {}
        polls = 0
        fails = 0
        while time.monotonic() < deadline:
            t0 = time.time()
            rec: dict[str, Any] = {"t": t0, "poll": polls}
            try:
                raw = await src.playbyplay(game_id)
                actions = raw["game"]["actions"]
                new, changed, removed = diff_actions(prev, actions)
                rec.update(ok=True, ms=round((time.time() - t0) * 1000), n=len(actions),
                           new=new, changed=changed, removed=removed)
                prev = {a["actionNumber"]: a for a in actions}
                if not first_saved:
                    (out / "first.json").write_text(json.dumps(raw), encoding="utf-8")
                    first_saved = True
            except NotAvailable:
                rec.update(ok=False, error="not_available")
            except UpstreamError as e:
                rec.update(ok=False, error=str(e)[:200])
            # scoreboard row gives game status + clock (separate file on the CDN)
            try:
                g = next((g for g in (await src.scoreboard())["scoreboard"]["games"] if g["gameId"] == game_id), None)
                if g:
                    rec["board"] = {k: g[k] for k in ("gameStatus", "period", "gameClock")} | {
                        "home": g["homeTeam"]["score"], "away": g["awayTeam"]["score"]}
            except UpstreamError:
                pass
            deltas.write(json.dumps(rec) + "\n"); deltas.flush()
            polls += 1
            if polls % 20 == 0:
                print(f"{datetime.now():%H:%M:%S} polls={polls} actions={rec.get('n')} board={rec.get('board')}", flush=True)
            if rec.get("board", {}).get("gameStatus") == 3:
                print("game final; stopping", flush=True)
                break
            fails = 0 if rec.get("ok", True) else fails + 1
            # a file that keeps failing is not helped by asking every few seconds (a real game lost its play-by-play for ten minutes): ease off, keep trying
            wait = interval if fails < 5 else min(30.0, interval * (1 + fails // 5))
            await _sleep(max(0.0, wait - (time.time() - t0)))
        if raw:
            (out / "last.json").write_text(json.dumps(raw), encoding="utf-8")
        deltas.close()
        print(f"recorded {polls} polls -> {out}", flush=True)
    finally:
        close = getattr(src, "aclose", None)
        if close:
            await close()


# ----------------------------------------------------------------- analyze ----

def _q(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))]


def snapshot_stats(actions: list[dict]) -> dict:
    """Edit behaviour visible in one finished game's play-by-play."""
    lags, by_type = [], {}
    for a in actions:
        t0, t1 = _ts(a.get("timeActual")), _ts(a.get("edited"))
        if t0 is not None and t1 is not None:
            lag = t1 - t0
            lags.append(lag)
            by_type.setdefault(a["actionType"], []).append(lag)
    nums = [a["actionNumber"] for a in actions]
    orders = [a["orderNumber"] for a in actions]
    order_by_num = [a["orderNumber"] for a in sorted(actions, key=lambda a: a["actionNumber"])]
    out = {
        "actions": len(actions),
        "with_edited_ts": len(lags),
        "edited_after_creation(>2s)": sum(l > 2 for l in lags),
        "edit_lag_s": {"median": round(statistics.median(lags), 1), "p90": round(_q(lags, .9), 1),
                       "p99": round(_q(lags, .99), 1), "max": round(max(lags), 1)} if lags else None,
        "action_number_gaps": max(nums) - min(nums) + 1 - len(set(nums)),
        "order_number_monotonic_in_action_number": order_by_num == sorted(order_by_num),
        "array_sorted_by_action_number": nums == sorted(nums),
        "edited_by_type_over_2s": {t: sum(l > 2 for l in v) for t, v in sorted(by_type.items()) if any(l > 2 for l in v)},
    }
    return out


def analyze_deltas(path: Path) -> dict:
    recs = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    ok = [r for r in recs if r.get("ok")]
    lat = [r["ms"] for r in ok]
    gaps, last_change = [], None
    max_id = -1
    out_of_order = 0
    edit_lags = []
    for r in ok:
        if r["new"] or r["changed"]:
            if last_change is not None:
                gaps.append(r["t"] - last_change)
            last_change = r["t"]
        before = max_id  # compare against ids from EARLIER polls only (the first poll is a bulk snapshot)
        for a in r["new"]:
            if a["actionNumber"] < before:
                out_of_order += 1
            max_id = max(max_id, a["actionNumber"])
        for a in r["changed"]:
            et = _ts(a.get("edited"))
            if et is not None:
                edit_lags.append(r["t"] - et)  # how stale our copy was when we noticed the edit
    return {
        "polls": len(recs), "ok": len(ok), "errors": len(recs) - len(ok),
        "latency_ms": {"median": statistics.median(lat), "p95": _q(lat, .95), "max": max(lat)} if lat else None,
        "polls_with_new_or_changed": sum(bool(r["new"] or r["changed"]) for r in ok),
        "seconds_between_updates": {"median": round(statistics.median(gaps), 1), "p90": round(_q(gaps, .9), 1)} if gaps else None,
        "new_actions": sum(len(r["new"]) for r in ok),
        "edited_actions_seen": sum(len(r["changed"]) for r in ok),
        "removed_actions": sum(len(r["removed"]) for r in ok),
        "new_action_with_lower_id_than_seen": out_of_order,
        "edit_detect_delay_s": {"median": round(statistics.median(edit_lags), 1), "max": round(max(edit_lags), 1)} if edit_lags else None,
    }


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="nbadash.record", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record")
    r.add_argument("--game"); r.add_argument("--interval", type=float, default=3.0)
    r.add_argument("--max-minutes", type=float, default=200.0); r.add_argument("--out", type=Path, default=DEFAULT_OUT)
    a = sub.add_parser("analyze"); a.add_argument("dir", type=Path)
    s = sub.add_parser("snapshot"); s.add_argument("file", type=Path)
    args = ap.parse_args(argv)
    if args.cmd == "record":
        asyncio.run(record(args.game, args.interval, args.max_minutes, args.out))
    elif args.cmd == "analyze":
        print(json.dumps(analyze_deltas(args.dir / "deltas.jsonl"), indent=2))
    else:
        print(json.dumps(snapshot_stats(json.loads(args.file.read_text(encoding="utf-8"))["game"]["actions"]), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
