"""Chef Claude: a coaching chat with tools. The model writes and coaches; all list math lives in grocery.py."""
import json
import logging
from datetime import date, datetime, timedelta

import anthropic

from . import config, gcal, store
from .grocery import parse_ingredient

log = logging.getLogger(__name__)
MAX_TOKENS = 16000  # two complete recipes in one reply need ~6k, and thinking shares the same budget

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
  You can schedule on any day shown in the plan (this week or next) or any later date. Never say the planner is limited to
  the current week. If they are planning next week, use next week's dates.
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
    {"name": "add_to_plan", "description": "Schedule a saved recipe on a day: this week, next week, or any day up to 8 weeks ahead. "
     "The right week is worked out from the date, so always give cook_date when they name a day.",
     "input_schema": {"type": "object", "properties": {
         "recipe_id": {"type": "integer"}, "servings": {"type": "integer"},
         "cook_date": {"type": "string", "description": "YYYY-MM-DD, today or later (use the dates in the plan below)"},
         "week_start": {"type": "string", "description": "Only if no day is chosen yet: the Monday (YYYY-MM-DD) of the week to hold it in"}},
         "required": ["recipe_id"]}},
]


def _normalize_ingredients(ings: list[dict]) -> list[dict]:
    out = []
    for i in ings:
        if not str(i.get("name", "")).strip():
            continue  # a nameless ingredient can't go on a grocery list
        base = parse_ingredient(i["name"]) if i.get("quantity") is None and not i.get("unit") else {}
        out.append({
            "quantity": i.get("quantity", base.get("quantity")),
            "unit": i.get("unit") or base.get("unit", ""),
            "name": base.get("name", i["name"]) if base else i["name"],
            "note": i.get("note", ""),
            "category": (base or parse_ingredient(i["name"]))["category"],
        })
    return out


TOOLS_BY_NAME = {t["name"]: t for t in TOOLS}


def run_tool(name: str, args: dict, events: list[dict]) -> str:
    """Run one tool call. A bad call becomes an error the chef can read and retry, never a crashed chat."""
    try:
        return _run_tool(name, args, events)
    except Exception as e:  # malformed arguments from the model, a missing field, a bad id
        log.warning("tool %s failed: %r", name, e)
        return json.dumps({"error": f"{name} failed: {type(e).__name__}: {e}. Check the arguments and try again."})


def _run_tool(name: str, args: dict, events: list[dict]) -> str:
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
        today = datetime.now(store.TZ).date()
        day = args.get("cook_date")
        try:
            if day:
                d = date.fromisoformat(day)
                if d < today:
                    return json.dumps({"error": f"{day} has already passed. Today is {today}."})
                if d > today + timedelta(days=store.PLAN_AHEAD_DAYS):
                    return json.dumps({"error": f"{day} is more than {store.PLAN_AHEAD_DAYS // 7} weeks away; pick an earlier day."})
                week = store.monday_of(day)
            else:
                week = args.get("week_start") or store.planning_week_start()
                if date.fromisoformat(week).weekday() != 0:
                    return json.dumps({"error": "week_start must be a Monday (YYYY-MM-DD)"})
        except ValueError:
            return json.dumps({"error": "dates must be YYYY-MM-DD"})
        store.add_plan_item(week, recipe["id"], args.get("servings") or recipe["servings"], day)
        events.append({"type": "added_to_plan", "recipe_id": recipe["id"], "title": recipe["title"], "cook_date": day, "week_start": week})
        return json.dumps({"added": True, "week_start": week})
    return json.dumps({"error": f"unknown tool {name}"})


def _week_block(week: str, heading: str) -> list[str]:
    target = store.get_meal_target(week)
    items = store.plan_items(week)
    by_day = {d: [i["recipe"]["title"] for i in items if i["cook_date"] == d] for d in store.week_days(week)}
    unscheduled = [i["recipe"]["title"] for i in items if not i["cook_date"]]
    lines = [f"\n{heading} (Monday {week}):",
             f"- Meals they want to prep: {target if target else 'not set yet (ask how many)'}; planned so far: {len(items)}"]
    for d, titles in by_day.items():
        lines.append(f"- {date.fromisoformat(d):%a %m-%d} ({d}): {', '.join(titles) if titles else 'open'}")
    try:  # busy times are a bonus; planning must work without the calendar
        busy = gcal.busy_by_day(week) if gcal.configured() else {}
    except Exception:
        busy = {}
    if any(busy.values()):
        lines.append("  Already on their calendars (quick meals on busy evenings, longer ones on free days):")
        for d, evs in busy.items():
            if evs:
                lines.append(f"  - {date.fromisoformat(d):%a %m-%d}: " + "; ".join(evs))
    if unscheduled:
        lines.append(f"- Planned but no day yet: {', '.join(unscheduled)}")
    return lines


def plan_context() -> str:
    """The plan for this week and next, so the chef can fill open days on either instead of guessing or refusing."""
    today = datetime.now(store.TZ).date()
    this_week = (today - timedelta(days=today.weekday())).isoformat()
    next_week = (date.fromisoformat(this_week) + timedelta(days=7)).isoformat()
    focus = store.planning_week_start()
    lines = [f"\nToday is {today:%A %Y-%m-%d}. You can schedule a meal on ANY day below (this week or next), or any later day with add_to_plan.",
             f"They are mainly planning {'NEXT week' if focus == next_week else 'THIS week'} (starting {focus}); "
             "when they say \"next week\" use next week's dates."]
    lines += _week_block(this_week, "This week")
    lines += _week_block(next_week, "Next week")
    return "\n".join(lines)


PARSE_SYSTEM = """You turn a pasted recipe (from a chat, a website, an email, a recipe card) into a structured recipe by calling save_recipe.

- Keep the author's quantities, ingredients and technique exactly. Do not invent or change amounts.
- Quantities are numbers (1.5, not "1 1/2"); when the text gives a range, use the upper end and put the range in the ingredient's note.
- Split the method into small, single-action steps in order. Set timer_seconds on any step with a stated time (use the middle of a range).
- Put the author's own tips, warnings and "why" explanations on the step they belong to. Put the best 3-5 general tips in chef_tips.
- Add 2-5 short tags (dish type, main protein, method such as "dutch oven", "one pot", "weeknight").
- prep_min and cook_min: use the text; if it only gives a total, split sensibly. Servings default to 4 if unstated.
- If the text is not a recipe, do not call the tool."""


def parse_recipe_text(text: str) -> dict:
    """Structure pasted recipe text with the model and save it. Raises ValueError if it isn't a recipe."""
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=config.ANTHROPIC_MODEL, max_tokens=MAX_TOKENS, system=PARSE_SYSTEM,
        tools=[TOOLS_BY_NAME["save_recipe"]], tool_choice={"type": "auto"},
        messages=[{"role": "user", "content": f"Save this recipe:\n\n{text}"}],
    )
    call = next((b for b in resp.content if b.type == "tool_use" and b.name == "save_recipe"), None)
    if not call:
        raise ValueError("That doesn't look like a recipe I can save. Paste the ingredients and steps.")
    events: list[dict] = []
    out = json.loads(run_tool("save_recipe", call.input, events))
    if "error" in out or not events:
        raise ValueError("I couldn't make a recipe from that text. Check it has ingredients and steps.")
    return store.get_recipe(events[0]["recipe_id"])


def library_context() -> str:
    """The saved recipes by name, so the chef doesn't guess what is (or isn't) in the library."""
    recipes = store.list_recipes()
    if not recipes:
        return "\nTheir recipe library is empty."
    lines = ["\nTheir saved recipes (this is the complete library; use search_my_recipes for details):"]
    for r in recipes[:60]:
        bits = [f"id {r['id']}"]
        if r.get("rating"):
            bits.append(f"{r['rating']}/5")
        if r.get("cook_count"):
            bits.append(f"cooked {r['cook_count']}x")
        if r.get("favorite"):
            bits.append("favorite")
        lines.append(f"- {r['title']} ({', '.join(bits)})")
    if len(recipes) > 60:
        lines.append(f"- ...and {len(recipes) - 60} more")
    return "\n".join(lines)


def taste_context() -> str:
    t = store.taste_summary()
    lines = ["\nWhat we know about their taste:"]
    if t["preferences"]:
        lines.append("Stated preferences:\n" + t["preferences"])
    for person, p in t.get("by_person", {}).items():
        if p["loved"]:
            lines.append(f"{person} loved: " + "; ".join(p["loved"]))
        if p["disliked"]:
            lines.append(f"{person} did not enjoy: " + "; ".join(p["disliked"]))
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
    sent = store.add_message("user", user_text)
    try:
        return _chat(user_text, sent)
    except Exception:
        store.delete_message(sent["id"])  # so a retry doesn't leave two unanswered messages in the history
        raise


def _chat(user_text: str, sent: dict) -> dict:
    client = anthropic.Anthropic()
    messages = _history()
    events: list[dict] = []
    system = SYSTEM + plan_context() + library_context() + taste_context()
    cut_off = 0
    for _ in range(8):  # bounded tool loop
        resp = client.messages.create(model=config.ANTHROPIC_MODEL, max_tokens=MAX_TOKENS, system=system, tools=TOOLS, messages=messages)
        log.info("chef reply: stop_reason=%s output_tokens=%s", resp.stop_reason, getattr(resp.usage, "output_tokens", "?"))
        if resp.stop_reason == "max_tokens":
            # The reply ran out of room, possibly halfway through saving a recipe. A half-written tool call can't be used,
            # so discard it and ask for the work in smaller pieces instead of presenting the stub as the answer.
            cut_off += 1
            if cut_off > 2:
                text = "That was a lot to write in one go and I kept running out of room. Could we do one recipe at a time?"
                break
            messages.append({"role": "user", "content": "Your last reply was cut off before it finished, so nothing was saved. "
                             "Do it again, one recipe per reply (a single tool call), and keep going until each is saved."})
            continue
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
