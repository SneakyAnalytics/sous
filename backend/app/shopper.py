"""Shopping chat: the chef helps pick Safeway products for the items marked Need.

The server holds no state. The client sends the items, the candidates found so far, the current picks and the chat so
far; the chef answers and may change the picks. Only the user's button press ever adds anything to the cart.
"""
import json

import anthropic

from . import config, store
from .safeway import SafewayError, get_client

SYSTEM = """You are Chef Claude helping a couple pick groceries from Safeway's online catalog for the ingredients they need.

- You get each needed ingredient (with how much the recipes call for), the Safeway products found for it, and the picks so far.
- Choose the product that best fits: right kind of item, a size that covers the amount needed (set quantity to the number
  of packages to buy, e.g. 2 cans when the recipes need 2 cans; a bunch of herbs is 1), in stock, and a fair price.
  Prefer plain store-brand staples unless they asked otherwise.
- If the best option is truly ambiguous (organic or not, hot or mild, fresh or frozen), ask one short question instead of guessing.
- If candidates are poor or missing, call search_safeway with a better query before giving up. If nothing fits, call skip_item.
- Use choose_product to set or change a pick. You can change several in one turn.
- Respect their stated taste and preferences below. Keep replies short. You only choose products: the person reviews
  everything and presses the button themselves, and you never check out."""

TOOLS = [
    {"name": "choose_product", "description": "Pick the Safeway product (and how many) for one needed ingredient.",
     "input_schema": {"type": "object", "properties": {
         "key": {"type": "string", "description": "the ingredient key from the list"},
         "product_id": {"type": "string"}, "quantity": {"type": "integer", "minimum": 1}},
         "required": ["key", "product_id", "quantity"]}},
    {"name": "skip_item", "description": "Do not buy this ingredient from Safeway (they will handle it another way).",
     "input_schema": {"type": "object", "properties": {"key": {"type": "string"}, "reason": {"type": "string"}}, "required": ["key"]}},
    {"name": "search_safeway", "description": "Search Safeway again for an ingredient with a better query.",
     "input_schema": {"type": "object", "properties": {"key": {"type": "string"}, "query": {"type": "string"}}, "required": ["key", "query"]}},
]


def _state_text(items: list[dict], candidates: dict, selections: dict) -> str:
    lines = ["Needed ingredients, Safeway candidates and current picks:"]
    for it in items:
        key = it["key"]
        cands = candidates.get(key, [])
        sel = selections.get(key) or {}
        pick = "no pick" if not sel.get("include") or not sel.get("product_id") else f"picked {sel['product_id']} x{sel.get('quantity', 1)}"
        lines.append(f"\n[{key}] need {it.get('display') or ''} {it['name']} (for {', '.join(it.get('recipes', []))}) - {pick}")
        for c in cands:
            price = f"${c['price']:.2f}" if isinstance(c.get("price"), (int, float)) else "price ?"
            stock = "" if c.get("in_stock", True) else " OUT OF STOCK"
            lines.append(f"   - {c['id']}: {c.get('brand') or ''} {c['name']} ({c.get('unit') or ''}, {price}){stock}")
        if not cands:
            lines.append("   (no candidates)")
    return "\n".join(lines)


async def shop_chat(items: list[dict], candidates: dict, selections: dict, history: list[dict], text: str,
                    client=None, safeway=None) -> dict:
    """Run one user turn. Returns the reply plus the updated picks and candidates."""
    client = client or anthropic.AsyncAnthropic()
    safeway = safeway or get_client()
    candidates = {k: list(v) for k, v in candidates.items()}
    selections = {k: dict(v) for k, v in selections.items()}
    keys = {i["key"] for i in items}
    taste = store.get_profile()
    system = SYSTEM + (f"\n\nTheir preferences:\n{taste}" if taste else "")
    messages = [{"role": h["role"], "content": h["text"]} for h in history[-12:]]
    # The current state goes with the new message so it is never stale, even after many turns.
    messages.append({"role": "user", "content": f"{_state_text(items, candidates, selections)}\n\nThem: {text}"})

    def run(name: str, args: dict) -> str:
        key = args.get("key")
        if key not in keys:
            return json.dumps({"error": f"unknown key {key}"})
        if name == "choose_product":
            ids = {c["id"] for c in candidates.get(key, [])}
            if args["product_id"] not in ids:
                return json.dumps({"error": "that product is not one of the candidates for this item"})
            selections[key] = {"include": True, "product_id": args["product_id"], "quantity": max(1, int(args.get("quantity") or 1))}
            return json.dumps({"ok": True})
        if name == "skip_item":
            selections[key] = {"include": False, "product_id": (selections.get(key) or {}).get("product_id", ""), "quantity": 1}
            return json.dumps({"ok": True})
        return "{}"

    reply = ""
    for _ in range(6):
        resp = await client.messages.create(model=config.ANTHROPIC_MODEL, max_tokens=2048, system=system, tools=TOOLS, messages=messages)
        if resp.stop_reason != "tool_use":
            reply = "".join(b.text for b in resp.content if b.type == "text").strip()
            break
        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for b in (b for b in resp.content if b.type == "tool_use"):
            if b.name == "search_safeway":
                try:
                    found = await safeway.search(b.input["query"])
                    if b.input.get("key") in keys:
                        candidates[b.input["key"]] = found
                    out = json.dumps(found)
                except (SafewayError, Exception) as e:  # browser automation fails in many ways; tell the chef, not the user
                    out = json.dumps({"error": f"search failed: {e}"})
            else:
                out = run(b.name, b.input)
            results.append({"type": "tool_result", "tool_use_id": b.id, "content": out})
        messages.append({"role": "user", "content": results})
    else:
        reply = "I got tangled up there. Could you say that again?"
    return {"reply": reply, "selections": selections, "candidates": candidates}
