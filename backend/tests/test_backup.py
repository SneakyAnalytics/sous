import os
import sqlite3
import time

from app import backup, config


def test_backup_copies_data_and_keeps_only_the_newest(client):
    client.post("/recipes", json={"title": "Soup", "ingredients": [], "steps": []})
    first = backup.backup_now()
    assert sqlite3.connect(first).execute("select title from recipes").fetchone()[0] == "Soup"
    for n in range(20):
        (config.DATA_DIR / "backups" / f"recipes_2000010{n % 10}_0000{n:02d}.db").write_bytes(b"x")
    backup.backup_now()
    assert len(list((config.DATA_DIR / "backups").glob("recipes_*.db"))) == backup.KEEP


def test_backup_runs_only_when_a_day_has_passed(_isolated_db):
    assert backup.backup_if_due() is not None          # none yet
    assert backup.backup_if_due() is None              # fresh
    newest = max((config.DATA_DIR / "backups").glob("recipes_*.db"), key=os.path.getmtime)
    old = time.time() - 25 * 3600
    os.utime(newest, (old, old))
    assert backup.backup_if_due() is not None          # a day old


def test_database_uses_wal(client):
    from app.db import connect
    with connect() as c:
        assert c.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_a_corrupt_backup_is_discarded_not_kept(_isolated_db, monkeypatch):
    import pytest
    monkeypatch.setattr(backup, "_check", lambda path: "database disk image is malformed")
    with pytest.raises(RuntimeError, match="integrity"):
        backup.backup_now()
    assert not list((config.DATA_DIR / "backups").glob("recipes_*.db"))


def test_a_valid_but_foreign_database_fails_the_check(tmp_path):
    other = tmp_path / "other.db"
    conn = sqlite3.connect(other); conn.execute("create table x (a)"); conn.commit(); conn.close()
    assert "no such table" in backup._check(other)


def test_status_reports_local_and_offsite(client):
    import json
    from datetime import datetime, timedelta, timezone
    assert client.get("/backup/status").json()["offsite"] is None
    at = (datetime.now(timezone.utc) - timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    (config.DATA_DIR / "offsite_status.json").write_text(json.dumps({"ok": True, "at": at, "message": "ok", "images": 3}), encoding="utf-8-sig")
    got = client.get("/backup/status").json()
    assert got["offsite"]["ok"] is True and 4.9 <= got["offsite"]["age_hours"] <= 5.1 and got["offsite"]["images"] == 3
    assert got["local"]["age_hours"] is not None  # the app's own startup backup
    (config.DATA_DIR / "offsite_status.json").write_text("{not json")
    assert client.get("/backup/status").json()["offsite"] is None
