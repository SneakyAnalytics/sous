import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    from app.main import app
    with TestClient(app) as c:
        yield c


RECIPE = {"title": "Pasta", "servings": 2, "ingredients": [
    {"quantity": 1, "unit": "lb", "name": "spaghetti"}, {"quantity": 2, "unit": "clove", "name": "garlic"}],
    "steps": [{"text": "Boil", "timer_seconds": 600}]}


def test_plan_list_have_need_and_cart(client):
    rid = client.post("/recipes", json=RECIPE).json()["id"]
    week = client.get("/plan/current-week").json()["week_start"]
    plan = client.post(f"/plan/{week}/items", json={"recipe_id": rid, "servings": 4}).json()
    by_name = {i["name"]: i for i in plan["list"]}
    assert by_name["spaghetti"]["display"] == "2 lb"
    assert by_name["garlic"]["category"] == "Produce"

    client.put(f"/plan/{week}/list/{by_name['garlic']['key']}", json={"status": "have"})
    client.put(f"/plan/{week}/list/{by_name['spaghetti']['key']}", json={"status": "need"})
    plan = client.get(f"/plan/{week}").json()
    assert {i["name"]: i["status"] for i in plan["list"]} == {"spaghetti": "need", "garlic": "have"}

    match = client.post("/cart/match", json={"names": ["spaghetti"]}).json()
    pid = match["spaghetti"]["candidates"][0]["id"]
    added = client.post("/cart/add", json={"lines": [{"key": "k", "product_id": pid}]}).json()
    assert added["results"] == [{"key": "k", "ok": True}]


def test_import_json_ld():
    from app.importer import parse_recipe_html
    page = '''<script type="application/ld+json">{"@graph":[{"@type":"Recipe","name":"Soup","recipeYield":"4 servings",
    "totalTime":"PT30M","cookTime":"PT20M","recipeIngredient":["2 cups broth","1 onion, diced"],
    "recipeInstructions":[{"@type":"HowToStep","text":"Simmer."}]}]}</script>'''
    r = parse_recipe_html(page, "http://x")
    assert r["servings"] == 4 and r["cook_min"] == 20 and r["ingredients"][1]["note"] == "diced"
    assert r["steps"] == [{"text": "Simmer."}]
