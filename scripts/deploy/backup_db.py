"""Consistent SQLite backup inside the container; keeps the newest 10."""
import datetime
import glob
import os
import sqlite3

SRC = "/app/data/recipes.db"
DIR = "/app/data/backups"
os.makedirs(DIR, exist_ok=True)
if not os.path.exists(SRC):
    print("no database yet; nothing to back up")
    raise SystemExit(0)
dest = os.path.join(DIR, f"recipes_{datetime.datetime.now():%Y%m%d_%H%M%S}.db")
target = sqlite3.connect(dest)
sqlite3.connect(SRC).backup(target)
target.close()
for old in sorted(glob.glob(os.path.join(DIR, "recipes_*.db")))[:-10]:
    os.remove(old)
print(f"backup ok: {dest}")
