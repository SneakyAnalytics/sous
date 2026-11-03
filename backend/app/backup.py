"""Daily SQLite backup into the data volume (next to the database). Keeps the newest 14.

This protects against a bad edit or a corrupted file. It is not an off-machine copy: the volume lives on the same disk.
"""
import asyncio
import logging
import sqlite3
import time
from datetime import datetime

from . import config

log = logging.getLogger(__name__)
KEEP = 14
EVERY_SECONDS = 24 * 3600


def _dir():
    return config.DATA_DIR / "backups"


def newest_age_seconds() -> float | None:
    files = sorted(_dir().glob("recipes_*.db"))
    return time.time() - files[-1].stat().st_mtime if files else None


def backup_now() -> str | None:
    if not config.DB_PATH.exists():
        return None
    _dir().mkdir(parents=True, exist_ok=True)
    dest = _dir() / f"recipes_{datetime.now():%Y%m%d_%H%M%S}.db"
    target = sqlite3.connect(dest)
    try:
        src = sqlite3.connect(config.DB_PATH)
        try:
            src.backup(target)
        finally:
            src.close()
    finally:
        target.close()
    for old in sorted(_dir().glob("recipes_*.db"))[:-KEEP]:
        old.unlink()
    return str(dest)


def backup_if_due() -> str | None:
    age = newest_age_seconds()
    return backup_now() if age is None or age >= EVERY_SECONDS else None


async def backup_loop(check_every: int = 3600) -> None:
    """Checks hourly and backs up when the newest backup is a day old, so restarts never skip or double up."""
    while True:
        try:
            made = await asyncio.to_thread(backup_if_due)
            if made:
                log.info("database backup written: %s", made)
        except Exception:
            log.exception("database backup failed")
        await asyncio.sleep(check_every)
