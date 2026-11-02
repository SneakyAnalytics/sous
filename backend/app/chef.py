"""Chef Claude: a coaching chat with tools. The model writes and coaches; all list math lives in grocery.py."""
import json

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
- Use search_my_recipes before suggesting something they may already have saved. Use add_to_plan only when they
  say they want to cook it this week.
- Use plain US units (cup, tbsp, tsp, oz, lb) and whole grocery-store ingredients.
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
    {"name": "save_recipe", "description": "Save a complete recipe to the household's library.", "input_schema": RECIPE_SCHEMA},
    {"name": "search_my_recipes", "description": "Search saved recipes by title/tag/ingredient. Empty query lists favorites and recent.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "add_to_plan", "description": "Add a saved recipe to this week's cooking plan.",
     "input_schema": {"type": "object", "properties": {"recipe_id": {"type": "integer"}, "servings": {"type": "integer"}},
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
    if name == "search_my_recipes":
        found = store.search_recipes(args.get("query", ""))
        return json.dumps([{"id": r["id"], "title": r["title"], "tags": r["tags"], "favorite": r["favorite"]} for r in found[:10]])
    if name == "add_to_plan":
        recipe = store.get_recipe(args["recipe_id"])
        if not recipe:
            return json.dumps({"error": "no such recipe"})
        store.add_plan_item(store.current_week_start(), recipe["id"], args.get("servings") or recipe["servings"])
        events.append({"type": "added_to_plan", "recipe_id": recipe["id"], "title": recipe["title"]})
        return json.dumps({"added": True})
    return json.dumps({"error": f"unknown tool {name}"})


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
            model=config.ANTHROPIC_MODEL, max_tokens=4096, system=SYSTEM, tools=TOOLS, messages=messages,
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
