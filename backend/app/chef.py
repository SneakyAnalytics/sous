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
        name = base.get("name", i["name"]) if base else i["name"]
        note = i.get("note", "")
        if "," in name:  # the model sometimes writes "carrots, peeled and sliced": the part after the comma is the note
            name, _, extra = name.partition(",")
            note = note or extra.strip()
        out.append({
            "quantity": i.get("quantity", base.get("quantity")),
            "unit": i.get("unit") or base.get("unit", ""),
            "name": name.strip(),
            "note": note,
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
        changed = sorted(k for k in fields if k in store.REVISABLE)
        events.append({"type": "recipe_revised", "recipe_id": recipe["id"], "title": recipe["title"], "reason": args.get("reason", ""), "changed": changed})
        return json.dumps({"revised": True, "changed": changed})
    if name == "remember_preference":
        existing = store.get_profile()
        store.set_profile((existing + "\n" if existing else "") + "- " + args["note"].strip())
        events.append({"type": "preference_saved", "note": args["note"].strip()})
        return json.dumps({"saved": True})
    if name == "add_recipe_note":
        recipe = store.get_recipe(args["recipe_id"])
        if not recipe:
            return json.dumps({"error": "no such recipe"})
        notes = (recipe["notes"] + "\n" if recipe["notes"] else "") + args["note"].strip()
        store.update_recipe(recipe["id"], {"notes": notes})
        events.append({"type": "recipe_noted", "recipe_id": recipe["id"], "title": recipe["title"], "note": args["note"].strip()})
        return json.dumps({"noted": True})
    if name == "retire_recipe":
        recipe = store.get_recipe(args["recipe_id"])
        if not recipe:
            return json.dumps({"error": "no such recipe"})
        weeks = store.soft_delete_recipe(recipe["id"])  # to the trash: restorable for 30 days
        events.append({"type": "recipe_retired", "recipe_id": recipe["id"], "title": recipe["title"], "weeks": weeks})
        return json.dumps({"retired": True, "restorable_for_days": 30})
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


RETIRE_TOOL = {"name": "retire_recipe", "description": "Take a recipe out of the household's recipe book (it goes to the trash and can be "
               "restored for 30 days). Only after they have said they don't want to cook it again AND you have asked and they confirmed.",
               "input_schema": {"type": "object", "properties": {"recipe_id": {"type": "integer"}, "reason": {"type": "string"}},
                                "required": ["recipe_id"]}}
NOTE_TOOL = {"name": "add_recipe_note", "description": "Add a line to this recipe's 'Our notes' for next time, when it doesn't change the recipe itself "
             "(e.g. 'Kadie likes it with extra lemon').",
             "input_schema": {"type": "object", "properties": {"recipe_id": {"type": "integer"}, "note": {"type": "string"}},
                              "required": ["recipe_id", "note"]}}
DEBRIEF_TOOLS = [TOOLS_BY_NAME["revise_recipe"], TOOLS_BY_NAME["remember_preference"], NOTE_TOOL, RETIRE_TOOL]

DEBRIEF_SYSTEM = """You are Chef Claude, a warm, exacting master chef, talking with a couple right after they finished eating a dinner they cooked
from one of their saved recipes. You can see the recipe and how they rated it, per person, and what they wrote. Your job is to close the
loop: find out what to change, and change it while they are still at the table.

How it goes:
- First reply: one sentence that shows you read their ratings and comments, then the single most useful follow-up question. If their
  comment is already specific enough to act on ("needs more garlic"), skip the question and propose the change.
- Ask one question at a time, and no more than three in all. Prefer questions that pin down the fix ("Too salty: was it the sausage or the
  broth?") over open-ended ones.
- When you know what to change, call revise_recipe with exactly that change (send the complete ingredients or steps list when you change
  them, keeping everything else as it was). Do it when they ask for the change or agree to your suggestion; if you thought of a change they
  didn't mention, ask first. Afterwards say in one or two sentences what you changed. The old version is kept and they can undo it.
- A lasting taste ("Kadie doesn't like sausage soups") goes to remember_preference, naming who. A reminder for next time that does not change
  the recipe goes to add_recipe_note.
- If they say they never want to cook it again, ask once whether to take it out of their recipe book (it can be restored for 30 days). Call
  retire_recipe only after they say yes. If there is a lesson in why, also call remember_preference.
- Never change a different recipe, and don't repeat what a tool already did. Keep every reply short and conversational, in plain text.
- When the loop is closed, end with one warm line about next time."""


def _debrief_context(recipe: dict) -> str:
    def ing(i):
        qty = " ".join(str(x) for x in (i.get("quantity"), i.get("unit")) if x not in (None, ""))
        return "- " + " ".join(p for p in (qty, i["name"], f"({i['note']})" if i.get("note") else "") if p)
    steps = [f"{n}. {s['text']}" + (f" [{s['timer_seconds'] // 60} min]" if s.get("timer_seconds") else "") for n, s in enumerate(recipe["steps"], 1)]
    cooks = store.cook_history(recipe["id"])[:4]
    past = [f"- {c['cooked_on']}: " + (", ".join(f"{who} {n}" for who, n in c["ratings"].items()) or (f"{c['rating']}" if c["rating"] else "no stars"))
            + (f", said: \"{c['notes']}\"" if c["notes"] else "") for c in cooks]
    parts = [f"We just finished cooking and eating \"{recipe['title']}\" (recipe id {recipe['id']}, serves {recipe['servings']}). Here is the recipe "
             "as it is right now (including any changes you have already made in this conversation) and how it went.",
             "Ingredients:\n" + "\n".join(ing(i) for i in recipe["ingredients"]),
             "Method:\n" + "\n".join(steps),
             "Chef's tips: " + " | ".join(recipe["chef_tips"]) if recipe["chef_tips"] else "",
             "Cooked, newest first (the first line is tonight):\n" + ("\n".join(past) if past else "- no ratings recorded yet"),
             "Our notes on it: " + recipe["notes"] if recipe["notes"] else "",
             "(This recipe is currently in the trash.)" if recipe.get("deleted_at") else "",
             "Start the debrief."]
    return "\n\n".join(p for p in parts if p)


def _actions_taken(events: list[dict]) -> str:
    """What the chef did on an earlier turn, in words, so it remembers it did it (it only ever sees the text of past turns)."""
    said = []
    for e in events:
        kind = e.get("type")
        if kind == "recipe_revised":
            said.append("changed the recipe (" + (e.get("reason") or ", ".join(e.get("changed", [])) or "edited") + ")")
        elif kind == "recipe_retired":
            said.append("moved the recipe to the trash")
        elif kind == "preference_saved":
            said.append(f"saved a taste preference: {e.get('note', '')}")
        elif kind == "recipe_noted":
            said.append(f"added a note to the recipe: {e.get('note', '')}")
    return ("\n[Actions I took in that reply: " + "; ".join(said) + ". These are done.]") if said else ""


def debrief(recipe_id: int, history: list[dict], text: str | None) -> dict:
    """One turn of the after-dinner conversation about a recipe. The caller keeps the transcript and sends it back each turn."""
    recipe = store.get_recipe(recipe_id, include_deleted=True)
    if not recipe:
        raise LookupError("no such recipe")
    messages = [{"role": "user", "content": _debrief_context(recipe)}]
    messages += [{"role": h["role"], "content": h["text"] + (_actions_taken(h.get("events") or []) if h["role"] == "assistant" else "")}
                 for h in history[-20:]]
    if text and text.strip():
        messages.append({"role": "user", "content": text.strip()})
    elif messages[-1]["role"] == "assistant":
        messages.append({"role": "user", "content": "Go on."})  # the API needs a user turn last
    events: list[dict] = []
    reply = _converse(DEBRIEF_SYSTEM + taste_context(), DEBRIEF_TOOLS, messages, events, max_turns=6)
    return {"reply": reply, "events": events, "recipe": store.get_recipe(recipe_id, include_deleted=True)}


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
            text += f"\n[{e['type']}: " + (f"recipe #{e['recipe_id']} {e['title']}" if "recipe_id" in e else e.get("note", "")) + "]"
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


def _converse(system: str, tools: list[dict], messages: list[dict], events: list[dict], max_turns: int = 8) -> str:
    """Run the model until it stops calling tools, applying each tool call. Returns the final text.

    A reply that ran out of room (possibly halfway through a tool call) is discarded and retried in smaller pieces, never
    shown as the answer. `messages` is extended in place.
    """
    client = anthropic.Anthropic()
    cut_off = 0
    for _ in range(max_turns):
        resp = client.messages.create(model=config.ANTHROPIC_MODEL, max_tokens=MAX_TOKENS, system=system, tools=tools, messages=messages)
        log.info("chef reply: stop_reason=%s output_tokens=%s", resp.stop_reason, getattr(resp.usage, "output_tokens", "?"))
        if resp.stop_reason == "max_tokens":
            cut_off += 1
            if cut_off > 2:
                return "That was a lot to write in one go and I kept running out of room. Could we do one thing at a time?"
            messages.append({"role": "user", "content": "Your last reply was cut off before it finished, so nothing was saved. "
                             "Do it again, one step per reply (a single tool call), and keep going until it is done."})
            continue
        if resp.stop_reason != "tool_use":
            # a refusal or an empty turn has no text: say something rather than show a blank bubble
            return "".join(b.text for b in resp.content if b.type == "text").strip() or "Hmm, I'm not sure what to add there. Tell me more?"
        messages.append({"role": "assistant", "content": resp.content})
        results = [
            {"type": "tool_result", "tool_use_id": b.id, "content": run_tool(b.name, b.input, events)}
            for b in resp.content if b.type == "tool_use"
        ]
        messages.append({"role": "user", "content": results})
    return "I got tangled up there. Could you say that again?"


def _chat(user_text: str, sent: dict) -> dict:
    messages = _history()
    events: list[dict] = []
    system = SYSTEM + plan_context() + library_context() + taste_context()
    text = _converse(system, TOOLS, messages, events)
    return store.add_message("assistant", text, events)
