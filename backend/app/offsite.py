"""Copies Sous's database snapshots and recipe photos to an external drive, from a small container beside the app.

The drive is bind-mounted at OFFSITE_DIR. Every few minutes this checks for new or changed files, copies them, verifies the
copy, and writes what happened to <data>/offsite_status.json, which the app shows on the Recipes page.

It only ever ADDS to the drive. A photo deleted in the app stays in the backup, and nothing else on the drive is touched.
Old database snapshots are pruned (the newest 10, plus anything under 60 days old).

If the drive is unplugged or unwritable, the failure is reported in the app and retried on the next pass.
"""
import hashlib
import json
import logging
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import backup

log = logging.getLogger("offsite")
CHECK_EVERY = 600  # seconds
KEEP_NEWEST = 10
KEEP_DAYS = 60
HEARTBEAT = Path(os.environ.get("OFFSITE_HEARTBEAT", "/tmp/offsite_alive"))


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _copy_if_needed(src: Path, dest: Path) -> bool:
    """Copy src to dest unless an identical file is already there. The copy is verified before it replaces anything."""
    if dest.exists() and dest.stat().st_size == src.stat().st_size and _sha(dest) == _sha(src):
        return False
    tmp = dest.with_name(dest.name + ".part")
    shutil.copyfile(src, tmp)
    if _sha(tmp) != _sha(src):
        tmp.unlink(missing_ok=True)
        raise OSError(f"the copy of {src.name} didn't match the original")
    os.replace(tmp, dest)
    return True


def sync_once(data_dir: Path, offsite_dir: Path, now: float | None = None) -> dict:
    """One pass. Always returns a status dict; never raises (a backup problem must not crash the loop)."""
    now = now or time.time()
    status = {"ok": False, "at": datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "dest": str(offsite_dir)}
    try:
        if not offsite_dir.is_dir():
            raise OSError("the backup drive isn't connected (or its folder is missing)")
        (offsite_dir / "db").mkdir(exist_ok=True)
        (offsite_dir / "images").mkdir(exist_ok=True)

        copied = 0
        snapshots = sorted((data_dir / "backups").glob("recipes_*.db"))
        for snap in snapshots:
            copied += _copy_if_needed(snap, offsite_dir / "db" / snap.name)
        for photo in sorted((data_dir / "images").glob("*.webp")):
            copied += _copy_if_needed(photo, offsite_dir / "images" / photo.name)

        # the newest copy on the drive must open as a healthy Sous database
        on_drive = sorted((offsite_dir / "db").glob("recipes_*.db"))
        if on_drive:
            problem = backup._check(on_drive[-1])
            if problem:
                raise OSError(f"the newest snapshot on the drive is damaged: {problem}")

        cutoff = now - KEEP_DAYS * 86400
        for old in on_drive[:-KEEP_NEWEST]:
            if old.stat().st_mtime < cutoff:
                old.unlink()
        on_drive = sorted((offsite_dir / "db").glob("recipes_*.db"))
        photos = list((offsite_dir / "images").glob("*.webp"))
        free_gb = round(shutil.disk_usage(offsite_dir).free / 1e9)
        if not snapshots and not on_drive:
            raise OSError("there is no database snapshot to back up yet")
        status.update(ok=True, db_files=len(on_drive), images=len(photos), free_gb=free_gb, copied=copied,
                      message=f"ok: {len(on_drive)} database snapshots, {len(photos)} photos, {free_gb} GB free")
        if free_gb < 5:
            status["message"] += " (running low on space)"
    except Exception as e:
        status["message"] = str(e) or type(e).__name__
        log.warning("offsite backup failed: %s", status["message"])
    try:
        out = data_dir / "offsite_status.json"
        tmp = out.with_suffix(".tmp")
        tmp.write_text(json.dumps(status), encoding="utf-8")
        os.replace(tmp, out)
    except OSError as e:
        log.warning("couldn't write the status file: %s", e)
    return status


def healthy(max_age: int = 1800) -> bool:
    """Is the loop alive? (The drive being unplugged is reported through the app, not by killing the container.)"""
    try:
        return time.time() - HEARTBEAT.stat().st_mtime < max_age
    except OSError:
        return False


def main() -> None:
    from . import config
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    offsite = os.environ.get("OFFSITE_DIR")
    if not offsite:
        log.info("OFFSITE_DIR isn't set; nothing to do")
        while True:
            time.sleep(3600)
    log.info("copying %s to %s every %ds", config.DATA_DIR, offsite, CHECK_EVERY)
    last = None
    while True:
        status = sync_once(config.DATA_DIR, Path(offsite))
        if status.get("copied") or status["ok"] != (last or {}).get("ok"):
            log.info("%s", status["message"])
        last = status
        HEARTBEAT.touch()
        time.sleep(CHECK_EVERY)


if __name__ == "__main__":
    if "--healthcheck" in sys.argv:
        sys.exit(0 if healthy() else 1)
    main()
