import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .db import connect, row_to_dict

TZ = ZoneInfo("America/Los_Angeles")  # "this week" is Pacific, not UTC


def current_week_start() -> str:
    today = datetime.now(TZ).date()
    return (today - timedelta(days=today.weekday())).isoformat()


def planning_week_start() -> str:
    """The week being planned: Sunday is when the household preps for the week ahead, so from Sunday it is next week."""
    today = datetime.now(TZ).date()
    monday = today - timedelta(days=today.weekday())
    return (monday + timedelta(days=7) if today.weekday() == 6 else monday).isoformat()


def valid_week(week_start: str) -> str:
    date.fromisoformat(week_start)
    return week_start


def in_week(week_start: str, day: str) -> bool:
    start = date.fromisoformat(week_start)
    return 0 <= (date.fromisoformat(day) - start).days < 7


def week_days(week_start: str) -> list[str]:
    start = date.fromisoformat(week_start)
    return [(start + timedelta(days=i)).isoformat() for i in range(7)]


# ---- recipes ----
def create_recipe(data: dict) -> dict:
    with connect() as c:
        cur = c.execute(
            "INSERT INTO recipes (title, description, servings, prep_min, cook_min, ingredients, steps, chef_tips, tags, source_url)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (data["title"], data.get("description", ""), data.get("servings") or 4, data.get("prep_min"), data.get("cook_min"),
             json.dumps(data.get("ingredients", [])), json.dumps(data.get("steps", [])),
             json.dumps(data.get("chef_tips", [])), json.dumps(data.get("tags", [])), data.get("source_url")),
        )
        rid = cur.lastrowid
    return get_recipe(rid)


def get_recipe(rid: int) -> dict | None:
    with connect() as c:
        row = c.execute("SELECT * FROM recipes WHERE id=?", (rid,)).fetchone()
    return row_to_dict(row) if row else None


def list_recipes() -> list[dict]:
    with connect() as c:
        rows = c.execute("SELECT * FROM recipes ORDER BY favorite DESC, created_at DESC, id DESC").fetchall()
    return [row_to_dict(r) for r in rows]


def search_recipes(query: str) -> list[dict]:
    q = query.strip().lower()
    recipes = list_recipes()
    if not q:
        return recipes
    return [r for r in recipes if q in r["title"].lower() or any(q in t.lower() for t in r["tags"])
            or any(q in i["name"].lower() for i in r["ingredients"])]


def update_recipe(rid: int, fields: dict) -> dict | None:
    allowed = {"title", "description", "servings", "prep_min", "cook_min", "ingredients", "steps", "chef_tips", "tags",
               "favorite", "rating", "notes"}
    sets, vals = [], []
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k}=?")
            vals.append(json.dumps(v) if isinstance(v, (list, dict)) else (int(v) if k == "favorite" else v))
    if sets:
        with connect() as c:
            c.execute(f"UPDATE recipes SET {', '.join(sets)} WHERE id=?", (*vals, rid))
    return get_recipe(rid)


def delete_recipe(rid: int) -> None:
    with connect() as c:
        c.execute("DELETE FROM recipes WHERE id=?", (rid,))


# ---- plan ----
def add_plan_item(week_start: str, recipe_id: int, servings: int, cook_date: str | None = None) -> None:
    with connect() as c:
        c.execute("INSERT INTO plan_items (week_start, recipe_id, servings, cook_date) VALUES (?,?,?,?)",
                  (valid_week(week_start), recipe_id, servings, cook_date))


def remove_plan_item(item_id: int) -> None:
    with connect() as c:
        c.execute("DELETE FROM plan_items WHERE id=?", (item_id,))


def get_plan_item(item_id: int) -> dict | None:
    with connect() as c:
        row = c.execute("SELECT * FROM plan_items WHERE id=?", (item_id,)).fetchone()
    return dict(row) if row else None


def update_plan_item(item_id: int, fields: dict) -> None:
    with connect() as c:
        for k in ("servings", "cook_date"):
            if k in fields:
                c.execute(f"UPDATE plan_items SET {k}=? WHERE id=?", (fields[k], item_id))


def plan_items(week_start: str) -> list[dict]:
    with connect() as c:
        rows = c.execute("SELECT * FROM plan_items WHERE week_start=? ORDER BY cook_date IS NULL, cook_date, id",
                         (week_start,)).fetchall()
    out = []
    for r in rows:
        item = dict(r)
        item["recipe"] = get_recipe(item["recipe_id"])
        out.append(item)
    return out


def get_meal_target(week_start: str) -> int | None:
    with connect() as c:
        row = c.execute("SELECT meal_target FROM week_settings WHERE week_start=?", (week_start,)).fetchone()
    return row["meal_target"] if row else None


def set_meal_target(week_start: str, target: int | None) -> None:
    with connect() as c:
        if target is None:
            c.execute("DELETE FROM week_settings WHERE week_start=?", (week_start,))
        else:
            c.execute("INSERT INTO week_settings (week_start, meal_target) VALUES (?,?)"
                      " ON CONFLICT(week_start) DO UPDATE SET meal_target=excluded.meal_target", (week_start, target))


def list_statuses(week_start: str) -> dict[str, str]:
    with connect() as c:
        rows = c.execute("SELECT key, status FROM list_status WHERE week_start=?", (week_start,)).fetchall()
    return {r["key"]: r["status"] for r in rows}


def set_status(week_start: str, key: str, status: str | None) -> None:
    with connect() as c:
        if status is None:
            c.execute("DELETE FROM list_status WHERE week_start=? AND key=?", (week_start, key))
        else:
            c.execute("INSERT INTO list_status (week_start, key, status) VALUES (?,?,?)"
                      " ON CONFLICT(week_start, key) DO UPDATE SET status=excluded.status", (week_start, key, status))


# ---- chat ----
def add_message(role: str, text: str, events: list | None = None) -> dict:
    with connect() as c:
        cur = c.execute("INSERT INTO chat_messages (role, text, events) VALUES (?,?,?)", (role, text, json.dumps(events or [])))
        row = c.execute("SELECT * FROM chat_messages WHERE id=?", (cur.lastrowid,)).fetchone()
    return row_to_dict(row)


def recent_messages(limit: int) -> list[dict]:
    with connect() as c:
        rows = c.execute("SELECT * FROM (SELECT * FROM chat_messages ORDER BY id DESC LIMIT ?) ORDER BY id", (limit,)).fetchall()
    return [row_to_dict(r) for r in rows]


def clear_messages() -> None:
    with connect() as c:
        c.execute("DELETE FROM chat_messages")


# ---- cooking history, revisions, taste ----
REVISABLE = ("title", "description", "servings", "prep_min", "cook_min", "ingredients", "steps", "chef_tips", "tags")


def log_cook(recipe_id: int, rating: int | None, notes: str, cooked_on: str | None = None) -> dict:
    day = cooked_on or datetime.now(TZ).date().isoformat()
    with connect() as c:
        c.execute("INSERT INTO cook_log (recipe_id, cooked_on, rating, notes) VALUES (?,?,?,?)", (recipe_id, day, rating, notes.strip()))
        if rating:
            c.execute("UPDATE recipes SET rating=? WHERE id=?", (rating, recipe_id))
    return get_recipe(recipe_id)


def cook_history(recipe_id: int) -> list[dict]:
    with connect() as c:
        rows = c.execute("SELECT * FROM cook_log WHERE recipe_id=? ORDER BY cooked_on DESC, id DESC", (recipe_id,)).fetchall()
    return [dict(r) for r in rows]


def revise_recipe(rid: int, fields: dict, reason: str = "") -> dict | None:
    """Apply changes, first saving the old version so a revision can be undone."""
    current = get_recipe(rid)
    if not current:
        return None
    changes = {k: v for k, v in fields.items() if k in REVISABLE and v is not None}
    if changes:
        with connect() as c:
            c.execute("INSERT INTO recipe_revisions (recipe_id, snapshot, reason) VALUES (?,?,?)",
                      (rid, json.dumps({k: current[k] for k in REVISABLE}), reason))
    return update_recipe(rid, changes)


def list_revisions(rid: int) -> list[dict]:
    with connect() as c:
        rows = c.execute("SELECT id, reason, created_at FROM recipe_revisions WHERE recipe_id=? ORDER BY id DESC", (rid,)).fetchall()
    return [dict(r) for r in rows]


def undo_revision(rid: int) -> dict | None:
    with connect() as c:
        row = c.execute("SELECT * FROM recipe_revisions WHERE recipe_id=? ORDER BY id DESC LIMIT 1", (rid,)).fetchone()
        if not row:
            return None
        c.execute("DELETE FROM recipe_revisions WHERE id=?", (row["id"],))
    return update_recipe(rid, json.loads(row["snapshot"]))


def get_profile() -> str:
    with connect() as c:
        row = c.execute("SELECT value FROM profile WHERE key='preferences'").fetchone()
    return row["value"] if row else ""


def set_profile(text: str) -> None:
    with connect() as c:
        c.execute("INSERT INTO profile (key, value) VALUES ('preferences', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (text.strip(),))


def taste_summary() -> dict:
    """What the household has told us, computed from ratings, favorites and cook notes."""
    recipes = list_recipes()
    with connect() as c:
        notes = c.execute("SELECT recipe_id, rating, notes, cooked_on FROM cook_log WHERE notes != '' ORDER BY cooked_on DESC, id DESC LIMIT 20").fetchall()
    titles = {r["id"]: r["title"] for r in recipes}
    tag_counts: dict[str, int] = {}
    for r in recipes:
        if r["favorite"] or (r["rating"] or 0) >= 4:
            for t in r["tags"]:
                tag_counts[t] = tag_counts.get(t, 0) + 1
    return {
        "preferences": get_profile(),
        "loved": [r["title"] for r in recipes if r["favorite"] or (r["rating"] or 0) >= 4],
        "disliked": [r["title"] for r in recipes if r["rating"] and r["rating"] <= 2],
        "liked_tags": [t for t, _ in sorted(tag_counts.items(), key=lambda kv: -kv[1])[:6]],
        "cook_notes": [{"recipe": titles.get(n["recipe_id"], "?"), "rating": n["rating"], "notes": n["notes"], "cooked_on": n["cooked_on"]} for n in notes],
    }
