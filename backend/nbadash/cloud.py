"""The two jobs that keep the hosted snapshot fresh (see snapshot.py for how the pieces fit).

  python -m nbadash.cloud refresh   GitHub Actions, every 15 minutes: pull, injuries + lineups + odds, push.
  python -m nbadash.cloud desktop   your computer, now and then: pull, the full stats refresh (stats.nba.com), push.

`refresh` leaves out the stats.nba.com ingest because that host does not answer GitHub's (or any cloud) addresses; `desktop` does it from yours.
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

from . import db, health, snapshot
from .refresh import refresh_availability, refresh_odds

log = logging.getLogger("nbadash.cloud")


def _store_and_path(db_arg: Optional[str]):
    store = snapshot.store_from_env()
    if store is None:
        raise SystemExit("cloud: R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY and R2_BUCKET must all be set")
    return store, (Path(db_arg) if db_arg else db.default_path())


def refresh_cloud(path: Path, store: snapshot.Store) -> dict:
    """The part of a refresh pass that works from a cloud address."""
    pulled = snapshot.restore(path, store)
    conn = db.connect(path)
    try:
        avail = refresh_availability(conn)
        health.record(conn, "pass")  # the scheduler is alive, whatever the sources did
        odds = refresh_odds(conn)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()
    pushed = snapshot.publish(path, store)
    return {"pulled": pulled["status"], "availability": avail, "odds": snapshot_brief(odds), "pushed": pushed["version"]}


def snapshot_brief(out: dict) -> dict:
    from .odds import brief
    return brief(out)


def desktop(path: Path, store: snapshot.Store) -> int:
    """Pull the newest snapshot, run the normal full refresh on top of it, and push the result."""
    log.info("pull: %s", snapshot.restore(path, store))
    code = subprocess.call([sys.executable, "-m", "nbadash.ingest", "--db", str(path), "refresh"])
    if code != 0:
        log.warning("the stats refresh exited with %s; pushing what exists anyway", code)
    log.info("push: %s", snapshot.publish(path, store))
    return code


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="nbadash.cloud", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["refresh", "desktop"])
    ap.add_argument("--db")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    store, path = _store_and_path(args.db)
    if args.cmd == "refresh":
        print(json.dumps(refresh_cloud(path, store), default=str)[:2000])
        return 0
    return desktop(path, store)


if __name__ == "__main__":
    raise SystemExit(main())
