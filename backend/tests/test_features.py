import json
from types import SimpleNamespace as NS

from app import chef, store

SOUP = {"title": "Soup", "servings": 4, "prep_min": 15, "cook_min": 60, "tags": ["soup"], "steps": [{"text": "Simmer"}],
        "ingredients": [{"quantity": 2, "unit": "tbsp", "name": "olive oil"}, {"quantity": 1, "unit": "", "name": "onion"},
                        {"quantity": 1, "unit": "tsp", "name": "Salt"}]}


def week_with(client, recipe=SOUP, day_index=2):
    rid = client.post("/recipes", json=recipe).json()["id"]
    week = store.planning_week_start()
    client.post(f"/plan/{week}/items", json={"recipe_id": rid, "cook_date": store.week_days(week)[day_index]})
    return rid, week


# ---- pantry staples ----
def test_staples_default_to_have_but_this_weeks_answer_wins(client):
    rid, week = week_with(client)
    by = lambda: {i["name"]: i for i in client.get(f"/plan/{week}").json()["list"]}
    assert by()["salt"]["status"] is None and by()["salt"]["staple"] is False
    assert client.put("/pantry/salt", json={"staple": True}).json() == ["salt"]
    assert by()["salt"]["status"] == "have" and by()["salt"]["staple"] is True
    assert by()["onion"]["status"] is None
    key = by()["salt"]["key"]
    client.put(f"/plan/{week}/list/{key}", json={"status": "need"})  # ran out this week
    assert by()["salt"]["status"] == "need" and by()["salt"]["staple"] is True
    client.put(f"/plan/{week}/list/{key}", json={"status": None})
    assert client.put("/pantry/Salt", json={"staple": False}).json() == []  # names match however they're written
    assert by()["salt"]["status"] is None


def test_pantry_matches_plurals_and_units(client):
    store.set_staple("Olive oils", True)
    assert store.is_staple("olive oil") and not store.is_staple("olive")


# ---- start-by time ----
def test_start_by_is_dinner_time_minus_work_and_follows_the_default(client):
    rid, week = week_with(client)
    item = lambda: client.get(f"/plan/{week}").json()["items"][0]
    assert (item()["eat_time"], item()["start_by"]) == ("17:30", "16:15")  # 75 min of work
    assert client.put("/settings/dinner-time", json={"time": "19:00"}).json() == {"dinner_time": "19:00"}
    assert (item()["eat_time"], item()["start_by"]) == ("19:00", "17:45")
    client.patch(f"/plan/items/{item()['id']}", json={"cook_time": "18:20"})
    assert (item()["eat_time"], item()["start_by"]) == ("18:20", "17:05")  # rounded down to 5 minutes
    assert client.put("/settings/dinner-time", json={"time": "7pm"}).status_code == 422


def test_no_start_by_without_times_or_a_day(client):
    rid = client.post("/recipes", json={"title": "Toast", "ingredients": [], "steps": []}).json()["id"]
    week = store.planning_week_start()
    client.post(f"/plan/{week}/items", json={"recipe_id": rid, "cook_date": store.week_days(week)[0]})
    client.post(f"/plan/{week}/items", json={"recipe_id": rid})
    items = client.get(f"/plan/{week}").json()["items"]
    assert items[0]["start_by"] is None and items[0]["eat_time"] == "17:30"
    assert items[1]["eat_time"] is None


# ---- per-person ratings ----
def test_each_person_rates_and_the_chef_learns_both(client):
    a = client.post("/recipes", json={**SOUP, "title": "Soup"}).json()["id"]
    b = client.post("/recipes", json={**SOUP, "title": "Fish"}).json()["id"]
    assert client.get("/household").json() == {"members": ["Jake", "Kadie"]}
    r = client.post(f"/recipes/{a}/cooked", json={"ratings": {"Jake": 5, "Kadie": 4}, "notes": "great"}).json()
    assert r["rating"] == 5  # average 4.5 rounds up
    client.post(f"/recipes/{b}/cooked", json={"ratings": {"Jake": 4, "Kadie": 1}})
    assert client.post(f"/recipes/{a}/cooked", json={"ratings": {"Jake": 9}}).status_code == 422
    t = client.get("/taste").json()
    assert t["by_person"]["Jake"] == {"loved": ["Soup", "Fish"], "disliked": []}
    assert t["by_person"]["Kadie"] == {"loved": ["Soup"], "disliked": ["Fish"]}
    ctx = chef.taste_context()
    assert "Kadie did not enjoy: Fish" in ctx and "Jake loved:" in ctx
    assert client.get(f"/recipes/{a}/history").json()["cooks"][0]["ratings"] == {"Jake": 5, "Kadie": 4}
    # a person's newest rating replaces their older one
    client.post(f"/recipes/{b}/cooked", json={"ratings": {"Kadie": 5}})
    assert "Fish" in client.get("/taste").json()["by_person"]["Kadie"]["loved"]


# ---- browsing data ----
def test_recipes_list_carries_cook_count_and_last_cooked(client):
    rid = client.post("/recipes", json=SOUP).json()["id"]
    client.post(f"/recipes/{rid}/cooked", json={"rating": 4})
    client.post(f"/recipes/{rid}/cooked", json={"rating": 5})
    r = client.get("/recipes").json()[0]
    assert r["cook_count"] == 2 and r["last_cooked"]
    other = client.post("/recipes", json={**SOUP, "title": "New"}).json()["id"]
    assert next(x for x in client.get("/recipes").json() if x["id"] == other)["cook_count"] == 0


# ---- hand edits ----
def test_editing_by_hand_is_undoable_and_recategorizes(client):
    rid = client.post("/recipes", json=SOUP).json()["id"]
    r = client.patch(f"/recipes/{rid}", json={"title": "Better Soup", "ingredients": [
        {"quantity": 3, "unit": "", "name": "carrots"}, {"quantity": 1, "name": "  "}], "favorite": True}).json()
    assert r["title"] == "Better Soup" and r["favorite"] is True
    assert [(i["name"], i["category"]) for i in r["ingredients"]] == [("carrots", "Produce")]  # blank row dropped
    assert client.get(f"/recipes/{rid}/history").json()["revisions"][0]["reason"] == "edited by hand"
    undone = client.post(f"/recipes/{rid}/undo-revision").json()
    assert undone["title"] == "Soup" and len(undone["ingredients"]) == 3
    client.patch(f"/recipes/{rid}", json={"notes": "just notes"})  # non-content edits don't create revisions
    assert client.get(f"/recipes/{rid}/history").json()["revisions"] == []


# ---- trash ----
def test_delete_is_a_trash_you_can_restore_from(client):
    rid, week = week_with(client)
    assert client.delete(f"/recipes/{rid}").status_code == 200
    assert client.get(f"/recipes/{rid}").status_code == 404 and client.get("/recipes").json() == []
    assert client.get(f"/plan/{week}").json()["items"] == []  # off the plan, so no ghost meals
    assert client.get("/recipes-trash").json()[0]["title"] == "Soup"
    assert client.delete(f"/recipes/{rid}").status_code == 404
    assert client.post(f"/recipes/{rid}/restore").json()["title"] == "Soup"
    assert [r["title"] for r in client.get("/recipes").json()] == ["Soup"]
    assert client.get("/recipes-trash").json() == []
    assert client.post("/recipes/999/restore").status_code == 404


def test_trash_is_purged_after_30_days_only(client):
    rid = client.post("/recipes", json=SOUP).json()["id"]
    client.delete(f"/recipes/{rid}")
    assert store.purge_deleted(30) == 0
    from app.db import connect
    with connect() as c:
        c.execute("UPDATE recipes SET deleted_at=datetime('now','-31 days') WHERE id=?", (rid,))
    assert store.purge_deleted(30) == 1 and client.get("/recipes-trash").json() == []


# ---- paste a recipe ----
def fake_client(blocks):
    return lambda: NS(messages=NS(create=lambda **kw: NS(content=blocks, stop_reason="end_turn")))


def test_paste_a_recipe_saves_the_structured_version(client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    call = NS(type="tool_use", id="t", name="save_recipe", input={
        "title": "Chili Mac", "servings": 4, "ingredients": [{"name": "elbow macaroni", "quantity": 8, "unit": "oz"}, {"quantity": 1}],
        "steps": [{"text": "Brown the beef", "timer_seconds": 480}], "tags": ["pasta"]})
    monkeypatch.setattr(chef.anthropic, "Anthropic", fake_client([call]))
    r = client.post("/recipes/parse", json={"text": "Chili Mac: brown the beef, add pasta... " * 3})
    assert r.status_code == 200 and r.json()["title"] == "Chili Mac"
    assert [i["name"] for i in r.json()["ingredients"]] == ["elbow macaroni"]
    assert r.json()["steps"][0]["timer_seconds"] == 480


def test_paste_rejects_non_recipes_and_short_text(client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setattr(chef.anthropic, "Anthropic", fake_client([NS(type="text", text="That's not a recipe")]))
    r = client.post("/recipes/parse", json={"text": "What a lovely day it is today, isn't it?"})
    assert r.status_code == 422 and "doesn't look like a recipe" in r.json()["detail"]
    assert client.post("/recipes/parse", json={"text": "hi"}).status_code == 422
    assert client.get("/recipes").json() == []
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert client.post("/recipes/parse", json={"text": "x" * 40}).status_code == 503
