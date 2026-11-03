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
