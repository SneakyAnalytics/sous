"""Chef Claude: a coaching chat with tools. The model writes and coaches; all list math lives in grocery.py."""
import json
from datetime import date, datetime

import anthropic

from . import config, store
from .grocery import parse_ingredient

SYSTEM = """You are Chef Claude, a warm, exacting master chef coaching two home cooks (a couple) in their kitchen.

How you work:
- Recommend dishes with real technique behind them. Say WHY a step matters (e.g. "dry the chicken so it sears instead of steams").
- When asked for recommendations, offer 2-3 options with one line each (time, difficulty, why it's great), and let them pick.
- When they pick a dish, or ask for a recipe, call save_recipe with the complete recipe. Ingredients are structured
  (quantity, unit, name); steps are small and single-action, with timer_seconds when a step is timed and an
  optional tip. Put your best coaching in chef_tips (3-5 tips: the technique that separates good from great).
- Prefer dishes with a strong reputation: classics and widely-loved recipes from respected sources. Never invent
  ratings or claim a specific star count; say what makes the dish well-loved instead.
- Use search_my_recipes before suggesting something they may already have saved, and mention saved favorites first
  since they often want to cook what they already know they enjoy.
- Planning: the household decides how many meals to prep and which day each lands on. Suggest options, wait for them
  to pick, then save_recipe and ask which day (or use the day they already named). Call add_to_plan with cook_date
  (YYYY-MM-DD) only once they have committed to cooking it. Never schedule a recipe they have not chosen.
- Use plain US units (cup, tbsp, tsp, oz, lb) and whole grocery-store ingredients.
- Their taste is listed below the plan. Lean toward what they love, avoid what they disliked, and honor their stated
  preferences without making a speech about it. When they tell you a lasting preference ("Kadie hates cilantro",
  "we want more fish"), call remember_preference.
- To change a saved recipe they ask you to revise ("less spicy", "swap the beans", "make it a one-pot"), call
  get_recipe first, then revise_recipe with only the fields that change (send complete ingredients/steps lists when
  you change those). Say in one line what you changed. The old version is kept, so they can undo.
- Keep chat replies short and conversational. The recipe card renders in the UI, so don't repeat the full recipe in chat."""

RECIPE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "servings": {"type": "integer"},
        "prep_min": {"type": "integer"},
        "cook_min": {"type": "integer"},
        "ingredients": {"type": "array", "items": {"type": "object", "properties": {
            "quantity": {"type": ["number", "null"]}, "unit": {"type": "string"},
            "name": {"type": "string"}, "note": {"type": "string"}}, "required": ["name"]}},
        "steps": {"type": "array", "items": {"type": "object", "properties": {
            "text": {"type": "string"}, "timer_seconds": {"type": "integer"}, "tip": {"type": "string"}},
            "required": ["text"]}},
        "chef_tips": {"type": "array", "items": {"type": "string"}},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "servings", "ingredients", "steps"],
}

TOOLS = [
    {"name": "get_recipe", "description": "Read one saved recipe in full (ingredients, steps, tips).",
     "input_schema": {"type": "object", "properties": {"recipe_id": {"type": "integer"}}, "required": ["recipe_id"]}},
    {"name": "revise_recipe", "description": "Change a saved recipe. Send only the fields that change; lists replace the old list entirely.",
     "input_schema": {"type": "object", "properties": {
         "recipe_id": {"type": "integer"}, "reason": {"type": "string", "description": "Short note on what changed and why"},
         **{k: RECIPE_SCHEMA["properties"][k] for k in ("title", "description", "servings", "prep_min", "cook_min", "ingredients", "steps", "chef_tips", "tags")}},
         "required": ["recipe_id", "reason"]}},
    {"name": "remember_preference", "description": "Save a lasting household taste or dietary preference so future suggestions respect it.",
     "input_schema": {"type": "object", "properties": {"note": {"type": "string"}}, "required": ["note"]}},
    {"name": "save_recipe", "description": "Save a complete recipe to the household's library.", "input_schema": RECIPE_SCHEMA},
    {"name": "search_my_recipes", "description": "Search saved recipes by title/tag/ingredient. Empty query lists favorites and recent.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "add_to_plan", "description": "Add a saved recipe to this week's cooking plan, on a specific day when known.",
     "input_schema": {"type": "object", "properties": {
         "recipe_id": {"type": "integer"}, "servings": {"type": "integer"},
         "cook_date": {"type": "string", "description": "YYYY-MM-DD, must be a day in the current week"}},
         "required": ["recipe_id"]}},
]


def _normalize_ingredients(ings: list[dict]) -> list[dict]:
    out = []
    for i in ings:
        base = parse_ingredient(i["name"]) if i.get("quantity") is None and not i.get("unit") else {}
        out.append({
            "quantity": i.get("quantity", base.get("quantity")),
            "unit": i.get("unit") or base.get("unit", ""),
            "name": base.get("name", i["name"]) if base else i["name"],
            "note": i.get("note", ""),
            "category": (base or parse_ingredient(i["name"]))["category"],
        })
    return out


def run_tool(name: str, args: dict, events: list[dict]) -> str:
    if name == "save_recipe":
        args = {**args, "ingredients": _normalize_ingredients(args.get("ingredients", []))}
        recipe = store.create_recipe(args)
        events.append({"type": "recipe_saved", "recipe_id": recipe["id"], "title": recipe["title"]})
        return json.dumps({"saved": True, "recipe_id": recipe["id"]})
    if name == "get_recipe":
        r = store.get_recipe(args["recipe_id"])
        return json.dumps(r) if r else json.dumps({"error": "no such recipe"})
    if name == "revise_recipe":
        fields = {k: v for k, v in args.items() if k not in ("recipe_id", "reason")}
        if "ingredients" in fields:
            fields["ingredients"] = _normalize_ingredients(fields["ingredients"])
        recipe = store.revise_recipe(args["recipe_id"], fields, args.get("reason", ""))
        if not recipe:
            return json.dumps({"error": "no such recipe"})
        events.append({"type": "recipe_revised", "recipe_id": recipe["id"], "title": recipe["title"]})
        return json.dumps({"revised": True, "changed": sorted(k for k in fields if k in store.REVISABLE)})
    if name == "remember_preference":
        existing = store.get_profile()
        store.set_profile((existing + "\n" if existing else "") + "- " + args["note"].strip())
        return json.dumps({"saved": True})
    if name == "search_my_recipes":
        found = store.search_recipes(args.get("query", ""))
        return json.dumps([{"id": r["id"], "title": r["title"], "tags": r["tags"], "favorite": r["favorite"]} for r in found[:10]])
    if name == "add_to_plan":
        recipe = store.get_recipe(args["recipe_id"])
        if not recipe:
            return json.dumps({"error": "no such recipe"})
        week = store.planning_week_start()
        day = args.get("cook_date")
        try:
            if day and not store.in_week(week, day):
                return json.dumps({"error": f"cook_date must be one of {store.week_days(week)}"})
        except ValueError:
            return json.dumps({"error": "cook_date must be YYYY-MM-DD"})
        store.add_plan_item(week, recipe["id"], args.get("servings") or recipe["servings"], day)
        events.append({"type": "added_to_plan", "recipe_id": recipe["id"], "title": recipe["title"], "cook_date": day})
        return json.dumps({"added": True})
    return json.dumps({"error": f"unknown tool {name}"})


def plan_context() -> str:
    """Where this week's plan stands, so the chef can fill the open days instead of guessing."""
    week = store.planning_week_start()
    today = datetime.now(store.TZ).date()
    target = store.get_meal_target(week)
    items = store.plan_items(week)
    by_day = {d: [i["recipe"]["title"] for i in items if i["cook_date"] == d and i["recipe"]] for d in store.week_days(week)}
    unscheduled = [i["recipe"]["title"] for i in items if not i["cook_date"] and i["recipe"]]
    lines = [f"\nThis week's plan (today is {today:%A %Y-%m-%d}; week starts Monday {week}):",
             f"- Meals they want to prep: {target if target else 'not set yet (ask how many)'}; planned so far: {len(items)}"]
    for d, titles in by_day.items():
        label = date.fromisoformat(d).strftime("%a %m-%d")
        lines.append(f"- {label} ({d}): {', '.join(titles) if titles else 'open'}")
    if unscheduled:
        lines.append(f"- Planned but no day yet: {', '.join(unscheduled)}")
    return "\n".join(lines)


def taste_context() -> str:
    t = store.taste_summary()
    lines = ["\nWhat we know about their taste:"]
    if t["preferences"]:
        lines.append("Stated preferences:\n" + t["preferences"])
    if t["loved"]:
        lines.append("Loved (favorites or 4-5 stars): " + "; ".join(t["loved"]))
    if t["disliked"]:
        lines.append("Did not enjoy (1-2 stars): " + "; ".join(t["disliked"]))
    if t["liked_tags"]:
        lines.append("Styles they gravitate to: " + ", ".join(t["liked_tags"]))
    for n in t["cook_notes"][:8]:
        lines.append(f"After cooking {n['recipe']}" + (f" ({n['rating']}/5)" if n["rating"] else "") + f": {n['notes']}")
    return "\n".join(lines) if len(lines) > 1 else ""


def _history() -> list[dict]:
    msgs = []
    for m in store.recent_messages(30):
        text = m["text"]
        for e in m["events"]:
            text += f"\n[{e['type']}: recipe #{e['recipe_id']} {e['title']}]"
        msgs.append({"role": m["role"], "content": text})
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    return msgs


def chat(user_text: str) -> dict:
    store.add_message("user", user_text)
    client = anthropic.Anthropic()
    messages = _history()
    events: list[dict] = []
    for _ in range(8):  # bounded tool loop
        resp = client.messages.create(
            model=config.ANTHROPIC_MODEL, max_tokens=4096, system=SYSTEM + plan_context() + taste_context(), tools=TOOLS, messages=messages,
        )
        if resp.stop_reason != "tool_use":
            text = "".join(b.text for b in resp.content if b.type == "text").strip()
            break
        messages.append({"role": "assistant", "content": resp.content})
        results = [
            {"type": "tool_result", "tool_use_id": b.id, "content": run_tool(b.name, b.input, events)}
            for b in resp.content if b.type == "tool_use"
        ]
        messages.append({"role": "user", "content": results})
    else:
        text = "I got tangled up there. Could you say that again?"
    return store.add_message("assistant", text, events)
