"""The database as a downloadable snapshot in S3-compatible storage (Cloudflare R2), so the site does not depend on one computer.

  python -m nbadash.snapshot push     upload this machine's database (a consistent copy, gzipped)
  python -m nbadash.snapshot pull     download the newest snapshot if it differs from the local one
  python -m nbadash.snapshot status   what is stored and what is local

Who writes, who reads:
  * GitHub Actions (`nbadash.cloud refresh`) pulls, refreshes injuries / lineups / odds, and pushes, every 15 minutes.
  * Your computer (`nbadash.cloud desktop`) pulls, runs the stats.nba.com ingest that cloud addresses cannot reach, and pushes.
  * The API (Cloud Run) only pulls: at start-up and then every few minutes.
Every writer pulls before it writes, so an update is built on the newest snapshot. A push that lands while another writer is mid-run can
overwrite that writer's last few minutes of rows; the next 15-minute pass restores them.

Configuration (environment): R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET. Without them everything here is a no-op.
Needs boto3 (`pip install -e "backend[cloud]"`).
"""
from __future__ import annotations

import argparse
import asyncio
import gzip
import hashlib
import json
import logging
import os
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Protocol

from . import db

log = logging.getLogger("nbadash.snapshot")

DB_KEY = "nba.db.gz"
MANIFEST_KEY = "snapshot.json"
CHECK_EVERY_SECONDS = 300


class Store(Protocol):
    """The three things we need from object storage."""

    def upload(self, path: Path, key: str) -> None: ...
    def download(self, key: str, path: Path) -> bool: ...  # False when the key does not exist


@dataclass
class R2Config:
    account_id: str
    access_key_id: str
    secret_access_key: str
    bucket: str


def config_from_env(env: Optional[dict] = None) -> Optional[R2Config]:
    env = env if env is not None else os.environ
    vals = [env.get(k, "").strip() for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")]
    return R2Config(*vals) if all(vals) else None


class R2Store:
    def __init__(self, cfg: R2Config):
        import boto3  # imported here so the API runs without it when snapshots are off
        self.bucket = cfg.bucket
        self.s3 = boto3.client("s3", endpoint_url=f"https://{cfg.account_id}.r2.cloudflarestorage.com", region_name="auto",
                               aws_access_key_id=cfg.access_key_id, aws_secret_access_key=cfg.secret_access_key)

    def upload(self, path: Path, key: str) -> None:
        self.s3.upload_file(str(path), self.bucket, key)

    def download(self, key: str, path: Path) -> bool:
        from botocore.exceptions import ClientError
        try:
            self.s3.download_file(self.bucket, key, str(path))
            return True
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise


def store_from_env(env: Optional[dict] = None) -> Optional[Store]:
    cfg = config_from_env(env)
    return R2Store(cfg) if cfg else None


# ---------------------------------------------------------------- publish and restore

def _version_file(db_path: Path) -> Path:
    return db_path.with_name(db_path.name + ".version")


def local_version(db_path: Path) -> Optional[str]:
    try:
        return _version_file(db_path).read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def read_manifest(store: Store, tmp: Path) -> Optional[dict]:
    p = tmp / "manifest.json"
    return json.loads(p.read_text(encoding="utf-8")) if store.download(MANIFEST_KEY, p) else None


def publish(db_path: Path, store: Store, now: Optional[datetime] = None) -> dict:
    """Upload a consistent copy of the database. The copy is made with SQLite's backup API, so a writer running meanwhile cannot tear it."""
    now = now or datetime.now(timezone.utc)
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        copy = tmp / "copy.db"
        src = sqlite3.connect(str(db_path), timeout=30)
        dst = sqlite3.connect(str(copy))
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        gz = tmp / DB_KEY
        h = hashlib.sha256()
        with open(copy, "rb") as f_in, gzip.open(gz, "wb", compresslevel=6) as f_out:
            for chunk in iter(lambda: f_in.read(1 << 20), b""):
                h.update(chunk)
                f_out.write(chunk)
        version = h.hexdigest()[:16]
        store.upload(gz, DB_KEY)  # the data first, then the manifest that points at it
        manifest = {"version": version, "published_at": now.isoformat(timespec="seconds"), "bytes_gz": gz.stat().st_size, "bytes": copy.stat().st_size}
        (tmp / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        store.upload(tmp / "manifest.json", MANIFEST_KEY)
    _version_file(db_path).write_text(version, encoding="utf-8")  # what we pushed is what we have
    log.info("snapshot pushed: %s", manifest)
    return manifest


def restore(db_path: Path, store: Store) -> dict:
    """Replace the local database with the stored snapshot when it differs. Returns {"status": "unchanged"|"restored"|"none", ...}."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=db_path.parent) as t:  # same filesystem as the target, so the final rename is atomic
        tmp = Path(t)
        manifest = read_manifest(store, tmp)
        if manifest is None:
            return {"status": "none"}
        if manifest["version"] == local_version(db_path) and db_path.exists():
            return {"status": "unchanged", "version": manifest["version"]}
        gz = tmp / DB_KEY
        if not store.download(DB_KEY, gz):
            return {"status": "none"}
        fresh = tmp / "fresh.db"
        with gzip.open(gz, "rb") as f_in, open(fresh, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out, 1 << 20)
        check = sqlite3.connect(str(fresh))
        try:
            ok = check.execute("PRAGMA quick_check").fetchone()[0]
        finally:
            check.close()
        if ok != "ok":
            raise RuntimeError(f"downloaded snapshot failed its integrity check: {ok}")
        for suffix in ("-wal", "-shm"):  # a leftover write-ahead log would be replayed onto the new file
            Path(str(db_path) + suffix).unlink(missing_ok=True)
        os.replace(fresh, db_path)
    _version_file(db_path).write_text(manifest["version"], encoding="utf-8")
    log.info("snapshot restored: %s", manifest)
    return {"status": "restored", **manifest}


async def keep_fresh(db_path: Path, store: Store, every: float = CHECK_EVERY_SECONDS) -> None:
    """For the API: look for a newer snapshot every few minutes. Failures are logged and retried; they never stop the site."""
    while True:
        await asyncio.sleep(every)
        try:
            out = await asyncio.to_thread(restore, db_path, store)
            if out["status"] == "restored":
                log.info("API data refreshed from snapshot %s", out.get("version"))
        except Exception as e:
            log.warning("snapshot check failed: %s: %s", type(e).__name__, e)


# ---------------------------------------------------------------- command line

def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="nbadash.snapshot", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["push", "pull", "status"])
    ap.add_argument("--db")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    store = store_from_env()
    if store is None:
        print("snapshot: R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY and R2_BUCKET are not all set")
        return 1
    path = Path(args.db) if args.db else db.default_path()
    if args.cmd == "push":
        print(json.dumps(publish(path, store)))
    elif args.cmd == "pull":
        print(json.dumps(restore(path, store)))
    else:
        with tempfile.TemporaryDirectory() as t:
            print(json.dumps({"remote": read_manifest(store, Path(t)), "local_version": local_version(path), "local_exists": path.exists()}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
