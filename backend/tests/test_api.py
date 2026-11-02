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


def test_meal_target_and_dated_plan_items(client):
    rid = client.post("/recipes", json=RECIPE).json()["id"]
    week = client.get("/plan/current-week").json()["week_start"]
    assert client.get(f"/plan/{week}").json()["meal_target"] is None
    assert client.put(f"/plan/{week}/target", json={"meal_target": 4}).json()["meal_target"] == 4
    assert client.put(f"/plan/{week}/target", json={"meal_target": 0}).status_code == 422

    from app import store
    thursday = store.week_days(week)[3]
    plan = client.post(f"/plan/{week}/items", json={"recipe_id": rid, "cook_date": thursday}).json()
    item = plan["items"][0]
    assert item["cook_date"] == thursday and item["servings"] == 2

    assert client.post(f"/plan/{week}/items", json={"recipe_id": rid, "cook_date": "2001-01-01"}).status_code == 422
    assert client.patch(f"/plan/items/{item['id']}", json={"cook_date": store.week_days(week)[5]}).status_code == 200
    assert client.patch(f"/plan/items/{item['id']}", json={"cook_date": "nope"}).status_code == 422
    assert client.patch("/plan/items/999", json={"servings": 2}).status_code == 404
    assert client.get(f"/plan/{week}").json()["items"][0]["cook_date"] == store.week_days(week)[5]


def test_chef_plan_context_and_tool(client):
    from app import chef, store
    rid = client.post("/recipes", json=RECIPE).json()["id"]
    week = store.planning_week_start()
    store.set_meal_target(week, 3)
    events = []
    day = store.week_days(week)[1]
    assert '"added": true' in chef.run_tool("add_to_plan", {"recipe_id": rid, "cook_date": day}, events)
    assert events[0]["cook_date"] == day
    assert "error" in chef.run_tool("add_to_plan", {"recipe_id": rid, "cook_date": "2001-01-01"}, events)
    ctx = chef.plan_context()
    assert "want to prep: 3" in ctx and "Pasta" in ctx and "open" in ctx


def test_cooked_log_updates_rating_and_taste(client):
    rid = client.post("/recipes", json=RECIPE).json()["id"]
    r = client.post(f"/recipes/{rid}/cooked", json={"rating": 5, "notes": "Needs more garlic"}).json()
    assert r["rating"] == 5
    assert client.post(f"/recipes/{rid}/cooked", json={"rating": 9}).status_code == 422
    assert client.post("/recipes/999/cooked", json={"rating": 3}).status_code == 404
    client.put("/taste", json={"preferences": "No cilantro"})
    taste = client.get("/taste").json()
    assert taste["loved"] == ["Pasta"] and taste["preferences"] == "No cilantro"
    assert taste["cook_notes"][0]["notes"] == "Needs more garlic"
    from app import chef
    ctx = chef.taste_context()
    assert "No cilantro" in ctx and "Loved" in ctx and "Needs more garlic" in ctx


def test_chef_revises_a_recipe_and_it_can_be_undone(client):
    from app import chef
    rid = client.post("/recipes", json=RECIPE).json()["id"]
    events = []
    out = chef.run_tool("revise_recipe", {"recipe_id": rid, "reason": "more garlic",
                        "ingredients": [{"quantity": 4, "unit": "clove", "name": "garlic"}]}, events)
    assert '"revised": true' in out and events[0]["type"] == "recipe_revised"
    now = client.get(f"/recipes/{rid}").json()
    assert [i["name"] for i in now["ingredients"]] == ["garlic"] and now["ingredients"][0]["category"] == "Produce"
    assert client.get(f"/recipes/{rid}/history").json()["revisions"][0]["reason"] == "more garlic"
    undone = client.post(f"/recipes/{rid}/undo-revision").json()
    assert [i["name"] for i in undone["ingredients"]] == ["spaghetti", "garlic"]
    assert client.post(f"/recipes/{rid}/undo-revision").status_code == 404
    assert '"saved": true' in chef.run_tool("remember_preference", {"note": "No cilantro"}, events)
    assert "No cilantro" in client.get("/taste").json()["preferences"]


def test_planning_week_rolls_forward_on_sunday(monkeypatch):
    from datetime import datetime
    from app import store

    class Fake(datetime):
        now_value = None

        @classmethod
        def now(cls, tz=None):
            return cls.now_value

    monkeypatch.setattr(store, "datetime", Fake)
    Fake.now_value = datetime(2026, 11, 1, 20, 0, tzinfo=store.TZ)  # Sunday evening
    assert store.planning_week_start() == "2026-11-02" and store.current_week_start() == "2026-10-26"
    Fake.now_value = datetime(2026, 11, 4, 9, 0, tzinfo=store.TZ)  # Wednesday
    assert store.planning_week_start() == "2026-11-02"
