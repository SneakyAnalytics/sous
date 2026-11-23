import json
from types import SimpleNamespace as NS

from app import chef, gcal, store

SOUP = {"title": "Sausage Soup", "servings": 4, "prep_min": 15, "cook_min": 60, "tags": ["soup"],
        "steps": [{"text": "Brown the sausage", "timer_seconds": 420}, {"text": "Add the broth and simmer"}],
        "chef_tips": ["Salt at the end"],
        "ingredients": [{"quantity": 1.5, "unit": "lb", "name": "Italian sausage"}, {"quantity": 4, "unit": "cup", "name": "chicken broth"}]}
USAGE = NS(output_tokens=1)


def text(t):
    return NS(stop_reason="end_turn", usage=USAGE, content=[NS(type="text", text=t)])


def tools(*calls, say=None):
    blocks = ([NS(type="text", text=say)] if say else []) + [NS(type="tool_use", id=f"t{i}", name=n, input=a) for i, (n, a) in enumerate(calls)]
    return NS(stop_reason="tool_use", usage=USAGE, content=blocks)


class Model:
    """A scripted stand-in for the Anthropic client that records what the chef was sent."""
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []
        self.messages = NS(create=self._create)

    def _create(self, **kw):
        self.calls.append({"system": kw["system"], "tools": [t["name"] for t in kw["tools"]], "messages": [dict(m) for m in kw["messages"]]})
        return self.replies.pop(0)


def use(monkeypatch, model):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setattr(chef.anthropic, "Anthropic", lambda: model)


def cooked(client, ratings=None, notes=""):
    rid = client.post("/recipes", json=SOUP).json()["id"]
    client.post(f"/recipes/{rid}/cooked", json={"ratings": ratings or {"Jake": 3, "Kadie": 2.5}, "notes": notes})
    return rid


def test_the_chef_opens_by_reading_the_ratings_and_comments(client, monkeypatch):
    rid = cooked(client, notes="way too salty")
    m = Model(text("Jake gave it 3 and Kadie 2.5, and you said it was too salty. Was it the sausage or the broth?"))
    use(monkeypatch, m)
    r = client.post(f"/recipes/{rid}/debrief", json={}).json()
    assert r["reply"].startswith("Jake gave it 3") and r["events"] == []
    sent = m.calls[0]["messages"]
    assert len(sent) == 1 and sent[0]["role"] == "user"
    ctx = sent[0]["content"]
    assert "Sausage Soup" in ctx and "1.5 lb Italian sausage" in ctx and "Jake 3, Kadie 2.5" in ctx and 'said: "way too salty"' in ctx
    assert "Brown the sausage [7 min]" in ctx and "Start the debrief." in ctx
    assert m.calls[0]["tools"] == ["revise_recipe", "remember_preference", "add_recipe_note", "retire_recipe"]
    assert "never want to cook it again" in m.calls[0]["system"]


def test_the_conversation_is_sent_back_each_turn_in_order(client, monkeypatch):
    rid = cooked(client)
    m = Model(text("Got it."))
    use(monkeypatch, m)
    history = [{"role": "assistant", "text": "Was it the sausage or the broth?"}]
    client.post(f"/recipes/{rid}/debrief", json={"history": history, "text": "Both, honestly."})
    roles = [x["role"] for x in m.calls[0]["messages"]]
    assert roles == ["user", "assistant", "user"] and m.calls[0]["messages"][-1]["content"] == "Both, honestly."
    # a transcript that ends on the chef's turn gets a user turn appended (the API needs one last)
    m2 = Model(text("Ok."))
    use(monkeypatch, m2)
    client.post(f"/recipes/{rid}/debrief", json={"history": history})
    assert [x["role"] for x in m2.calls[0]["messages"]][-1] == "user"


def test_agreed_changes_update_the_recipe_and_can_be_undone(client, monkeypatch):
    rid = cooked(client, notes="too salty")
    new_ings = [{"quantity": 1.5, "unit": "lb", "name": "Italian sausage"}, {"quantity": 3, "unit": "cup", "name": "low-sodium chicken broth"}]
    m = Model(tools(("revise_recipe", {"recipe_id": rid, "reason": "less salty: low-sodium broth, 3 cups", "ingredients": new_ings})),
              text("Done: 3 cups of low-sodium broth now. You can undo that if you change your mind."))
    use(monkeypatch, m)
    r = client.post(f"/recipes/{rid}/debrief", json={"history": [{"role": "assistant", "text": "Cut the broth?"}], "text": "Yes, low sodium and less of it"}).json()
    assert [e["type"] for e in r["events"]] == ["recipe_revised"] and r["events"][0]["recipe_id"] == rid
    assert [(i["name"], i["quantity"]) for i in r["recipe"]["ingredients"]][1] == ("low-sodium chicken broth", 3)
    assert client.get(f"/recipes/{rid}/history").json()["revisions"][0]["reason"].startswith("less salty")
    undone = client.post(f"/recipes/{rid}/undo-revision").json()
    assert [i["name"] for i in undone["ingredients"]][1] == "chicken broth"


def test_lasting_tastes_and_notes_are_saved_in_the_same_turn(client, monkeypatch):
    rid = cooked(client)
    m = Model(tools(("remember_preference", {"note": "Kadie finds sausage soups too salty"}),
                    ("add_recipe_note", {"recipe_id": rid, "note": "Try half the sausage next time"})), text("Noted both."))
    use(monkeypatch, m)
    r = client.post(f"/recipes/{rid}/debrief", json={"text": "Kadie just doesn't love salty soups"}).json()
    assert [e["type"] for e in r["events"]] == ["preference_saved", "recipe_noted"]
    assert "Kadie finds sausage soups too salty" in client.get("/taste").json()["preferences"]
    assert client.get(f"/recipes/{rid}").json()["notes"] == "Try half the sausage next time"
    assert "Kadie finds sausage" in chef.taste_context()  # and the main chef sees it from now on


def test_retiring_a_recipe_moves_it_to_the_trash_and_off_the_plan(client, monkeypatch):
    rid = cooked(client, ratings={"Jake": 1, "Kadie": 1}, notes="never again")
    week = store.planning_week_start()
    client.post(f"/plan/{week}/items", json={"recipe_id": rid, "cook_date": store.week_days(week)[3]})
    synced = []
    monkeypatch.setattr(gcal, "configured", lambda: True)
    monkeypatch.setattr(gcal, "sync_week", lambda w, svc=None: synced.append(w) or {"created": 0, "updated": 0, "deleted": 1, "unchanged": 0})
    m = Model(tools(("retire_recipe", {"recipe_id": rid, "reason": "disliked"}), ("remember_preference", {"note": "Neither of us likes sausage soup"})),
              text("Removed it. You can restore it from Recipes for 30 days."))
    use(monkeypatch, m)
    r = client.post(f"/recipes/{rid}/debrief", json={"history": [{"role": "assistant", "text": "Take it out of the book?"}], "text": "Yes"}).json()
    assert [e["type"] for e in r["events"]] == ["recipe_retired", "preference_saved"]
    assert r["events"][0]["weeks"] == [week]
    assert client.get("/recipes").json() == [] and client.get("/recipes-trash").json()[0]["title"] == "Sausage Soup"
    assert client.get(f"/plan/{week}").json()["items"] == []
    assert synced == [week]  # its calendar event is removed too
    assert client.post(f"/recipes/{rid}/restore").json()["title"] == "Sausage Soup"  # and it is not gone for good


def test_a_conversation_can_continue_after_the_recipe_was_retired(client, monkeypatch):
    rid = cooked(client)
    client.delete(f"/recipes/{rid}")
    m = Model(text("Anything else?"))
    use(monkeypatch, m)
    assert client.post(f"/recipes/{rid}/debrief", json={"text": "thanks"}).status_code == 200
    assert "currently in the trash" in m.calls[0]["messages"][0]["content"]


def test_bad_tool_calls_become_errors_the_chef_can_read(client, monkeypatch):
    rid = cooked(client)
    m = Model(tools(("retire_recipe", {"recipe_id": 99999})), text("Hm, I couldn't find that one."))
    use(monkeypatch, m)
    r = client.post(f"/recipes/{rid}/debrief", json={"text": "remove it"}).json()
    assert r["events"] == [] and client.get("/recipes").json()  # nothing was removed
    assert "no such recipe" in json.dumps(m.calls[1]["messages"][-1]["content"])


def test_debrief_errors_are_friendly(client, monkeypatch):
    import anthropic
    import httpx
    rid = cooked(client)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert client.post(f"/recipes/{rid}/debrief", json={}).status_code == 503
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    assert client.post("/recipes/999/debrief", json={}).status_code == 404

    def boom(**kw):
        raise anthropic.APIConnectionError(request=httpx.Request("POST", "http://x"))
    monkeypatch.setattr(chef.anthropic, "Anthropic", lambda: NS(messages=NS(create=boom)))
    r = client.post(f"/recipes/{rid}/debrief", json={})
    assert r.status_code == 502 and "Beelink's internet" in r.json()["detail"]
    assert client.post(f"/recipes/{rid}/debrief", json={"history": [{"role": "system", "text": "x"}]}).status_code == 422


def test_main_chat_history_copes_with_preference_events(client, monkeypatch):
    """Regression guard: events without a recipe id (a saved preference) must not break the chat history."""
    store.add_message("user", "Kadie hates cilantro")
    store.add_message("assistant", "Noted.", [{"type": "preference_saved", "note": "Kadie hates cilantro"}])
    store.add_message("user", "ok")
    assert "preference_saved" in chef._history()[1]["content"]


def test_the_chef_remembers_what_it_already_did_earlier_in_the_conversation(client, monkeypatch):
    """Regression (seen live): after revising the recipe the chef later said 'I never actually changed the recipe', because it
    only saw the text of its earlier turns, not its actions, and the recipe it was shown was already edited."""
    rid = cooked(client)
    m = Model(text("Anything else?"))
    use(monkeypatch, m)
    history = [{"role": "assistant", "text": "Was it the broth?"},
               {"role": "user", "text": "Yes, cut it to 3 cups and low sodium"},
               {"role": "assistant", "text": "Done, 3 cups of low-sodium broth.",
                "events": [{"type": "recipe_revised", "recipe_id": rid, "title": "Sausage Soup", "reason": "3 cups of low-sodium broth", "changed": ["ingredients"]},
                           {"type": "preference_saved", "note": "Kadie dislikes salty soups"}]}]
    client.post(f"/recipes/{rid}/debrief", json={"history": history, "text": "great"})
    sent = m.calls[0]["messages"]
    assert "right now (including any changes you have already made" in sent[0]["content"]
    said = sent[3]["content"]
    assert said.startswith("Done, 3 cups of low-sodium broth.")
    assert "changed the recipe (3 cups of low-sodium broth)" in said and "saved a taste preference: Kadie dislikes salty soups" in said
    assert "These are done" in said
    assert "[Actions" not in sent[1]["content"] and "[Actions" not in sent[2]["content"]  # only on the turns that took actions


def test_revision_events_say_why_and_what_changed(client, monkeypatch):
    rid = cooked(client)
    m = Model(tools(("revise_recipe", {"recipe_id": rid, "reason": "less salt", "chef_tips": ["Taste before salting"]})), text("Done."))
    use(monkeypatch, m)
    e = client.post(f"/recipes/{rid}/debrief", json={"text": "yes"}).json()["events"][0]
    assert e["reason"] == "less salt" and e["changed"] == ["chef_tips"]
