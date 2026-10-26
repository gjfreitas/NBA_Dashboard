"""Snapshot publish / restore with an in-memory store (no network, no boto3)."""
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from nbadash import cloud, db, snapshot


class MemStore:
    def __init__(self):
        self.files: dict[str, bytes] = {}

    def upload(self, path: Path, key: str) -> None:
        self.files[key] = Path(path).read_bytes()

    def download(self, key: str, path: Path) -> bool:
        if key not in self.files:
            return False
        Path(path).write_bytes(self.files[key])
        return True


def make_db(path: Path, name: str) -> Path:
    c = db.connect(path)
    with c:
        c.execute("INSERT INTO players (id, full_name, is_active) VALUES (1, ?, 1)", (name,))
    c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    c.close()
    return path


def names(path: Path) -> list[str]:
    c = sqlite3.connect(path)
    try:
        return [r[0] for r in c.execute("SELECT full_name FROM players")]
    finally:
        c.close()


def test_push_then_pull_on_another_machine(tmp_path):
    store = MemStore()
    a = make_db(tmp_path / "a" / "nba.db", "Nikola Jokic")
    manifest = snapshot.publish(a, store)
    assert set(store.files) == {snapshot.DB_KEY, snapshot.MANIFEST_KEY}
    assert json.loads(store.files[snapshot.MANIFEST_KEY])["version"] == manifest["version"]
    b = tmp_path / "b" / "nba.db"
    out = snapshot.restore(b, store)
    assert out["status"] == "restored" and names(b) == ["Nikola Jokic"]
    assert snapshot.restore(b, store)["status"] == "unchanged"  # nothing new: no download, no replace


def test_a_newer_snapshot_replaces_the_local_database_and_its_wal(tmp_path):
    store = MemStore()
    a = make_db(tmp_path / "a" / "nba.db", "Old")
    snapshot.publish(a, store)
    b = tmp_path / "b" / "nba.db"
    snapshot.restore(b, store)
    c = db.connect(a)
    with c:
        c.execute("UPDATE players SET full_name='New' WHERE id=1")
    c.close()
    snapshot.publish(a, store)
    Path(str(b) + "-wal").write_bytes(b"stale")  # must not be replayed onto the new file
    assert snapshot.restore(b, store)["status"] == "restored"
    assert names(b) == ["New"] and not Path(str(b) + "-wal").exists()


def test_restore_with_nothing_stored_changes_nothing(tmp_path):
    p = make_db(tmp_path / "nba.db", "Keep")
    assert snapshot.restore(p, MemStore())["status"] == "none"
    assert names(p) == ["Keep"]


def test_a_corrupt_download_is_refused(tmp_path):
    store = MemStore()
    snapshot.publish(make_db(tmp_path / "a.db", "X"), store)
    import gzip
    store.files[snapshot.DB_KEY] = gzip.compress(b"this is not a database" * 100)
    p = make_db(tmp_path / "keep" / "nba.db", "Keep")
    with pytest.raises(Exception):
        snapshot.restore(p, store)
    assert names(p) == ["Keep"]


def test_config_needs_all_four_variables():
    full = {"R2_ACCOUNT_ID": "a", "R2_ACCESS_KEY_ID": "b", "R2_SECRET_ACCESS_KEY": "c", "R2_BUCKET": "d"}
    assert snapshot.config_from_env(full) is not None
    assert snapshot.config_from_env({**full, "R2_BUCKET": ""}) is None
    assert snapshot.config_from_env({}) is None


def test_the_cloud_refresh_pulls_refreshes_and_pushes(tmp_path, monkeypatch):
    store = MemStore()
    snapshot.publish(make_db(tmp_path / "seed.db", "Seed"), store)
    monkeypatch.setattr(cloud, "refresh_availability", lambda conn: {"injuries": {"new": 0}})
    monkeypatch.setattr(cloud, "refresh_odds", lambda conn: {"skipped": "no odds API key set"})
    path = tmp_path / "work" / "nba.db"
    out = cloud.refresh_cloud(path, store)
    assert out["pulled"] == "restored" and out["pushed"]
    other = tmp_path / "api" / "nba.db"
    assert snapshot.restore(other, store)["status"] == "restored"
    c = sqlite3.connect(other)
    assert c.execute("SELECT COUNT(*) FROM source_checks").fetchone()[0] >= 1  # the pass was recorded before pushing
    c.close()
