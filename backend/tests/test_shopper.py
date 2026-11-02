import asyncio
from types import SimpleNamespace as NS

from app import shopper


class FakeMessages:
    def __init__(self, script):
        self.script, self.calls = list(script), []

    async def create(self, **kw):
        self.calls.append({**kw, "messages": list(kw["messages"])})
        return self.script.pop(0)


def tool(id, name, **inp):
    return NS(type="tool_use", id=id, name=name, input=inp)


def resp(*blocks, stop="tool_use"):
    return NS(content=list(blocks), stop_reason=stop)


class FakeSafeway:
    async def search(self, q):
        return [{"id": "new-1", "name": f"Fresh {q}", "price": 2.5, "unit": "each", "in_stock": True}]


ITEMS = [{"key": "k-onion", "name": "onion", "display": "2", "recipes": ["Soup"]},
         {"key": "k-broth", "name": "chicken broth", "display": "4 cup", "recipes": ["Soup"]}]
CANDS = {"k-onion": [{"id": "o1", "name": "Yellow Onion", "price": 1.5, "unit": "lb"}],
         "k-broth": [{"id": "b1", "name": "Broth 32oz", "price": 2.0, "unit": "32 oz"}, {"id": "b2", "name": "Broth 8oz", "price": 1.0}]}


def run(script, selections=None, text="pick for me"):
    client = NS(messages=FakeMessages(script))
    out = asyncio.run(shopper.shop_chat(ITEMS, CANDS, selections or {}, [], text, client=client, safeway=FakeSafeway()))
    return out, client


def test_chef_picks_products_and_quantities():
    out, client = run([
        resp(tool("t1", "choose_product", key="k-onion", product_id="o1", quantity=2),
             tool("t2", "choose_product", key="k-broth", product_id="b1", quantity=1)),
        resp(NS(type="text", text="Done: 2 onions and one big carton of broth."), stop="end_turn"),
    ])
    assert out["selections"]["k-onion"] == {"include": True, "product_id": "o1", "quantity": 2}
    assert out["selections"]["k-broth"]["product_id"] == "b1"
    assert out["reply"].startswith("Done")
    # the current state travels with the message so the chef never works from stale picks
    assert "[k-broth] need 4 cup chicken broth" in client.messages.calls[0]["messages"][-1]["content"]


def test_unknown_products_and_keys_are_rejected_not_applied():
    out, _ = run([
        resp(tool("t1", "choose_product", key="k-onion", product_id="made-up", quantity=1),
             tool("t2", "choose_product", key="nope", product_id="o1", quantity=1)),
        resp(NS(type="text", text="ok"), stop="end_turn"),
    ])
    assert out["selections"] == {}


def test_search_replaces_candidates_and_skip_unselects():
    out, _ = run([
        resp(tool("t1", "search_safeway", key="k-onion", query="sweet onion")),
        resp(tool("t2", "choose_product", key="k-onion", product_id="new-1", quantity=1), tool("t3", "skip_item", key="k-broth")),
        resp(NS(type="text", text="Swapped the onion; skipping broth."), stop="end_turn"),
    ], selections={"k-broth": {"include": True, "product_id": "b1", "quantity": 1}})
    assert out["candidates"]["k-onion"][0]["id"] == "new-1"
    assert out["selections"]["k-onion"]["product_id"] == "new-1"
    assert out["selections"]["k-broth"]["include"] is False


def test_chat_endpoint_requires_a_key(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = client.post("/cart/chat", json={"items": [], "candidates": {}, "selections": {}, "text": "hi"})
    assert r.status_code == 503
