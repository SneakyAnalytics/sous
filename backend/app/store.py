import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .db import connect, row_to_dict

TZ = ZoneInfo("America/Los_Angeles")  # "this week" is Pacific, not UTC


def current_week_start() -> str:
    today = datetime.now(TZ).date()
    return (today - timedelta(days=today.weekday())).isoformat()


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
