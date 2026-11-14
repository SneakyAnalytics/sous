import json
import os
import sqlite3
import time

from app import backup, config, offsite


def make_snapshot(data_dir, name="recipes_20261110_030000.db"):
    (data_dir / "backups").mkdir(parents=True, exist_ok=True)
    path = data_dir / "backups" / name
    conn = sqlite3.connect(path)
    conn.execute("create table recipes (id integer primary key, title text)")
    conn.execute("insert into recipes (title) values ('Soup')")
    conn.commit(); conn.close()
    return path


def only_snapshot(data_dir, name):
    """The app writes its own snapshot at startup; start from exactly the one this test makes."""
    for f in (data_dir / "backups").glob("*.db"):
        f.unlink()
    return make_snapshot(data_dir, name)


def photo(data_dir, name, content=b"jpegbytes"):
    (data_dir / "images").mkdir(parents=True, exist_ok=True)
    (data_dir / "images" / name).write_bytes(content)


def test_copies_snapshots_and_photos_and_reports_to_the_app(client, tmp_path):
    data, drive = config.DATA_DIR, tmp_path / "drive"
    drive.mkdir()
    make_snapshot(data); photo(data, "2.webp")
    s = offsite.sync_once(data, drive)
    assert s["ok"] and s["images"] == 1 and s["copied"] >= 2 and "ok:" in s["message"]
    assert (drive / "images" / "2.webp").read_bytes() == b"jpegbytes"
    assert any((drive / "db").glob("recipes_20261110_030000.db"))
    # and the app's own status endpoint now shows it
    got = client.get("/backup/status").json()["offsite"]
    assert got["ok"] is True and got["images"] == 1 and got["age_hours"] < 0.1


def test_second_pass_copies_nothing_but_still_proves_the_drive_works(client, tmp_path):
    data, drive = config.DATA_DIR, tmp_path / "drive"; drive.mkdir()
    make_snapshot(data); photo(data, "2.webp")
    offsite.sync_once(data, drive)
    again = offsite.sync_once(data, drive)
    assert again["ok"] and again["copied"] == 0
    assert (data / "offsite_status.json").exists()


def test_a_changed_photo_is_replaced_and_a_deleted_one_is_kept(client, tmp_path):
    data, drive = config.DATA_DIR, tmp_path / "drive"; drive.mkdir()
    make_snapshot(data); photo(data, "2.webp", b"v1")
    offsite.sync_once(data, drive)
    photo(data, "2.webp", b"version-two")          # the cover photo was changed
    assert offsite.sync_once(data, drive)["copied"] == 1
    assert (drive / "images" / "2.webp").read_bytes() == b"version-two"
    (data / "images" / "2.webp").unlink()           # ...then deleted in the app
    offsite.sync_once(data, drive)
    assert (drive / "images" / "2.webp").exists()    # a backup keeps it


def test_other_files_on_the_drive_are_never_touched(client, tmp_path):
    data, drive = config.DATA_DIR, tmp_path / "drive"; drive.mkdir()
    (drive / "setup.exe").write_bytes(b"installer"); (drive / "boot").mkdir(); (drive / "boot" / "bcd").write_bytes(b"x")
    make_snapshot(data)
    offsite.sync_once(data, drive)
    assert (drive / "setup.exe").read_bytes() == b"installer" and (drive / "boot" / "bcd").exists()


def test_a_missing_drive_is_reported_not_raised(client, tmp_path):
    data = config.DATA_DIR
    make_snapshot(data)
    s = offsite.sync_once(data, tmp_path / "not-plugged-in")
    assert s["ok"] is False and "isn't connected" in s["message"]
    assert client.get("/backup/status").json()["offsite"]["ok"] is False  # the app shows the failure


def test_a_damaged_snapshot_on_the_drive_is_flagged(client, tmp_path):
    data, drive = config.DATA_DIR, tmp_path / "drive"; (drive / "db").mkdir(parents=True)
    make_snapshot(data)
    (drive / "db" / "recipes_29990101_000000.db").write_bytes(b"not a database at all")  # newest by name
    s = offsite.sync_once(data, drive)
    assert s["ok"] is False and "damaged" in s["message"]


def test_nothing_to_back_up_yet_is_an_honest_failure(client, tmp_path):
    (tmp_path / "drive").mkdir()
    # no snapshots exist: the app's own startup backup is removed so the case is real
    for f in (config.DATA_DIR / "backups").glob("*.db"):
        f.unlink()
    s = offsite.sync_once(config.DATA_DIR, tmp_path / "drive")
    assert s["ok"] is False and "no database snapshot" in s["message"]


def test_old_snapshots_are_pruned_but_never_the_newest_ten_or_anything_recent(client, tmp_path):
    data, drive = config.DATA_DIR, tmp_path / "drive"; (drive / "db").mkdir(parents=True)
    now = time.time()
    only_snapshot(data, "recipes_20261110_030000.db")                      # the live one, newest by name
    for n in range(12):                                                    # 12 old snapshots, 100 days old
        p = drive / "db" / f"recipes_202601{n + 1:02d}_000000.db"
        p.write_bytes(b"x"); os.utime(p, (now - 100 * 86400,) * 2)
    for n in range(3):                                                     # 3 recent ones
        p = drive / "db" / f"recipes_20261105_00000{n}.db"
        p.write_bytes(b"x"); os.utime(p, (now - 2 * 86400,) * 2)
    assert offsite.sync_once(data, drive, now=now)["ok"]
    names = sorted(p.name for p in (drive / "db").glob("recipes_*.db"))
    assert len(names) == 10                                                # 16 files: the oldest 6 (old AND outside the newest 10) go
    assert names[0] == "recipes_20260107_000000.db"
    assert {"recipes_20261105_000000.db", "recipes_20261105_000002.db", "recipes_20261110_030000.db"} <= set(names)


def test_recent_snapshots_are_kept_even_beyond_ten(client, tmp_path):
    data, drive = config.DATA_DIR, tmp_path / "drive"; (drive / "db").mkdir(parents=True)
    now = time.time()
    only_snapshot(data, "recipes_20261110_030000.db")
    for n in range(14):                                                    # 14 snapshots, all only 3 days old
        p = drive / "db" / f"recipes_202611{n + 1:02d}_000000.db"
        p.write_bytes(b"x"); os.utime(p, (now - 3 * 86400,) * 2)
    offsite.sync_once(data, drive, now=now)
    assert len(list((drive / "db").glob("recipes_*.db"))) == 15            # nothing under 60 days old is removed


def test_the_heartbeat_tells_the_healthcheck_the_loop_is_alive(tmp_path, monkeypatch):
    beat = tmp_path / "alive"
    monkeypatch.setattr(offsite, "HEARTBEAT", beat)
    assert offsite.healthy() is False
    beat.touch()
    assert offsite.healthy() is True
    os.utime(beat, (time.time() - 3600,) * 2)
    assert offsite.healthy() is False
