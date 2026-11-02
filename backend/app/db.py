import json
import sqlite3
from contextlib import contextmanager

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS recipes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    servings INTEGER NOT NULL DEFAULT 4,
    prep_min INTEGER,
    cook_min INTEGER,
    ingredients TEXT NOT NULL DEFAULT '[]',
    steps TEXT NOT NULL DEFAULT '[]',
    chef_tips TEXT NOT NULL DEFAULT '[]',
    tags TEXT NOT NULL DEFAULT '[]',
    source_url TEXT,
    favorite INTEGER NOT NULL DEFAULT 0,
    rating INTEGER,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS plan_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start TEXT NOT NULL,
    recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    servings INTEGER NOT NULL,
    cook_date TEXT
);
-- The household's answer to "do you have this?" for one ingredient in one week.
CREATE TABLE IF NOT EXISTS list_status (
    week_start TEXT NOT NULL,
    key TEXT NOT NULL,
    status TEXT NOT NULL,            -- have | need
    PRIMARY KEY (week_start, key)
);
-- How many meals the household intends to prep this week.
CREATE TABLE IF NOT EXISTS week_settings (
    week_start TEXT PRIMARY KEY,
    meal_target INTEGER NOT NULL
);
-- One row each time a recipe is cooked: how it went, and what to change next time.
CREATE TABLE IF NOT EXISTS cook_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    cooked_on TEXT NOT NULL,
    rating INTEGER,
    notes TEXT NOT NULL DEFAULT ''
);
-- The previous version of a recipe, kept whenever the chef or a person revises it.
CREATE TABLE IF NOT EXISTS recipe_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    snapshot TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
-- Free-text household preferences the chef should always respect ("no cilantro", "Kadie likes spicy").
CREATE TABLE IF NOT EXISTS profile (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,
    text TEXT NOT NULL,
    events TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

JSON_COLS = ("ingredients", "steps", "chef_tips", "tags", "events")


def init_db() -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(plan_items)")}
        if "cook_time" not in cols:  # added after the first deploy
            conn.execute("ALTER TABLE plan_items ADD COLUMN cook_time TEXT")


@contextmanager
def connect():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for col in JSON_COLS:
        if col in d:
            d[col] = json.loads(d[col])
    if "favorite" in d:
        d["favorite"] = bool(d["favorite"])
    return d
