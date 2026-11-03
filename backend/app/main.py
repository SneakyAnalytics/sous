import asyncio
import os
from contextlib import asynccontextmanager
from typing import Literal

import anthropic
from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import backup, chef, gcal, grocery, importer, shopper, store
from .db import init_db
from .safeway import SafewayError, get_client


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    task = asyncio.create_task(backup.backup_loop())
    yield
    task.cancel()


app = FastAPI(title="Sous", lifespan=lifespan)


@app.get("/health")
def health():
    return {"ok": True}


def _api_error(e: anthropic.APIError) -> str:
    """What to tell the person when the model service has a problem (their message was not lost)."""
    if isinstance(e, anthropic.RateLimitError):
        return "The chef is a bit overwhelmed right now. Give it a minute and try again."
    if isinstance(e, anthropic.AuthenticationError):
        return "The chef can't sign in: check ANTHROPIC_API_KEY on the server."
    if isinstance(e, (anthropic.APIConnectionError, anthropic.APITimeoutError)):
        return "Couldn't reach the chef's service. Check the Beelink's internet and try again."
    return "The chef hit a snag. Try again in a moment."


# ---- chat ----
class ChatIn(BaseModel):
    text: str


@app.get("/chat")
def chat_history():
    return store.recent_messages(100)


@app.post("/chat")
def chat_send(body: ChatIn):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(503, "ANTHROPIC_API_KEY is not set")
    try:
        return chef.chat(body.text)
    except anthropic.APIError as e:
        raise HTTPException(502, _api_error(e))


@app.delete("/chat")
def chat_clear():
    store.clear_messages()


# ---- recipes ----
class RecipeIn(BaseModel):
    title: str
    description: str = ""
    servings: int = 4
    prep_min: int | None = None
    cook_min: int | None = None
    ingredients: list[dict] = []
    steps: list[dict] = []
    chef_tips: list[str] = []
    tags: list[str] = []
    source_url: str | None = None


class RecipePatch(BaseModel):
    title: str | None = None
    description: str | None = None
    servings: int | None = None
    ingredients: list[dict] | None = None
    steps: list[dict] | None = None
    chef_tips: list[str] | None = None
    tags: list[str] | None = None
    favorite: bool | None = None
    rating: int | None = None
    notes: str | None = None


class ImportIn(BaseModel):
    url: str


@app.get("/recipes")
def recipes(q: str = ""):
    return store.search_recipes(q)


@app.post("/recipes")
def recipe_create(body: RecipeIn):
    data = body.model_dump()
    data["ingredients"] = [
        i if "category" in i else {**i, "category": grocery.categorize(i.get("name", ""))} for i in data["ingredients"]
    ]
    return store.create_recipe(data)


@app.post("/recipes/import")
def recipe_import(body: ImportIn):
    try:
        return store.create_recipe(importer.import_from_url(body.url))
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(502, f"Couldn't fetch that page: {e}")


@app.get("/recipes/{rid}")
def recipe_get(rid: int):
    r = store.get_recipe(rid)
    if not r:
        raise HTTPException(404)
    return r


@app.patch("/recipes/{rid}")
def recipe_patch(rid: int, body: RecipePatch):
    if not store.get_recipe(rid):
        raise HTTPException(404)
    return store.update_recipe(rid, body.model_dump(exclude_unset=True))


@app.delete("/recipes/{rid}")
def recipe_delete(rid: int):
    store.delete_recipe(rid)


class CookedIn(BaseModel):
    rating: int | None = Field(default=None, ge=1, le=5)
    notes: str = ""


class ProfileIn(BaseModel):
    preferences: str


@app.post("/recipes/{rid}/cooked")
def recipe_cooked(rid: int, body: CookedIn):
    if not store.get_recipe(rid):
        raise HTTPException(404)
    return store.log_cook(rid, body.rating, body.notes)


@app.get("/recipes/{rid}/history")
def recipe_history(rid: int):
    return {"cooks": store.cook_history(rid), "revisions": store.list_revisions(rid)}


@app.post("/recipes/{rid}/undo-revision")
def recipe_undo(rid: int):
    restored = store.undo_revision(rid)
    if not restored:
        raise HTTPException(404, "nothing to undo")
    return restored


@app.get("/taste")
def taste_get():
    return store.taste_summary()


@app.put("/taste")
def taste_put(body: ProfileIn):
    store.set_profile(body.preferences)
    return store.taste_summary()


# ---- weekly plan + grocery list ----
class PlanAdd(BaseModel):
    recipe_id: int
    servings: int | None = None
    cook_date: str | None = None


class TargetIn(BaseModel):
    meal_target: int | None = Field(default=None, ge=1, le=14)


class PlanPatch(BaseModel):
    servings: int | None = None
    cook_date: str | None = None
    cook_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


class StatusIn(BaseModel):
    status: Literal["have", "need"] | None


def _week(week_start: str) -> str:
    try:
        return store.valid_week(week_start)
    except ValueError:
        raise HTTPException(422, "week_start must be YYYY-MM-DD")


_last_sync: dict = {}


def _calendar_sync(week_start: str) -> dict:
    """Push the week to Google Calendar. Never raises: a calendar problem must not break planning."""
    try:
        counts = gcal.sync_week(week_start)
        _last_sync.update(week_start=week_start, ok=True, counts=counts, error=None)
    except Exception as e:
        _last_sync.update(week_start=week_start, ok=False, counts=None, error=str(e))
    return dict(_last_sync)


def _sync_soon(background: BackgroundTasks, week_start: str) -> None:
    if gcal.configured():
        background.add_task(_calendar_sync, week_start)


def _check_day(week_start: str, day: str | None) -> None:
    if day is None:
        return
    try:
        ok = store.in_week(week_start, day)
    except ValueError:
        ok = False
    if not ok:
        raise HTTPException(422, "cook_date must be a YYYY-MM-DD day inside that week")


@app.get("/plan/current-week")
def current_week():
    return {"week_start": store.planning_week_start()}


@app.get("/plan/{week_start}")
def plan_get(week_start: str):
    week_start = _week(week_start)
    items = store.plan_items(week_start)
    statuses = store.list_statuses(week_start)
    shopping = grocery.build_list([i for i in items if i["recipe"]])
    for s in shopping:
        s["status"] = statuses.get(s["key"])
    return {"week_start": week_start, "meal_target": store.get_meal_target(week_start), "items": items, "list": shopping}


@app.put("/plan/{week_start}/target")
def plan_target(week_start: str, body: TargetIn):
    store.set_meal_target(_week(week_start), body.meal_target)
    return plan_get(week_start)


@app.post("/plan/{week_start}/items")
def plan_add(week_start: str, body: PlanAdd, background: BackgroundTasks):
    recipe = store.get_recipe(body.recipe_id)
    if not recipe:
        raise HTTPException(404, "recipe not found")
    week_start = _week(week_start)
    _check_day(week_start, body.cook_date)
    store.add_plan_item(week_start, recipe["id"], body.servings or recipe["servings"], body.cook_date)
    _sync_soon(background, week_start)
    return plan_get(week_start)


@app.patch("/plan/items/{item_id}")
def plan_patch(item_id: int, body: PlanPatch, background: BackgroundTasks):
    fields = body.model_dump(exclude_unset=True)
    item = store.get_plan_item(item_id)
    if not item:
        raise HTTPException(404)
    _check_day(item["week_start"], fields.get("cook_date"))
    store.update_plan_item(item_id, fields)
    _sync_soon(background, item["week_start"])


@app.delete("/plan/items/{item_id}")
def plan_remove(item_id: int, background: BackgroundTasks):
    item = store.get_plan_item(item_id)
    store.remove_plan_item(item_id)
    if item:
        _sync_soon(background, item["week_start"])


@app.get("/calendar/status")
def calendar_status():
    return {"configured": gcal.configured(), "dinner_time": gcal.dinner_time(), "last_sync": _last_sync or None}


@app.post("/plan/{week_start}/calendar-sync")
def calendar_sync(week_start: str):
    if not gcal.configured():
        raise HTTPException(503, "Google Calendar is not set up on this server")
    result = _calendar_sync(_week(week_start))
    if not result["ok"]:
        raise HTTPException(502, result["error"])
    return result


@app.put("/plan/{week_start}/list/{key:path}")
def list_status(week_start: str, key: str, body: StatusIn):
    store.set_status(_week(week_start), key, body.status)


# ---- Safeway cart (add only; never checks out) ----
class MatchIn(BaseModel):
    names: list[str]


class CartLine(BaseModel):
    key: str
    product_id: str
    quantity: int = 1


class CartIn(BaseModel):
    lines: list[CartLine]


@app.post("/cart/match")
async def cart_match(body: MatchIn):
    """For each needed ingredient, find candidate Safeway products. The user reviews before anything is added."""
    client = get_client()
    out = {}
    for name in body.names:
        try:
            out[name] = {"candidates": await client.search(name)}
        except SafewayError as e:
            out[name] = {"candidates": [], "error": str(e)}
        except Exception as e:  # browser automation can fail in many ways; report per item
            out[name] = {"candidates": [], "error": f"Safeway lookup failed: {e}"}
    return out


class ShopChatIn(BaseModel):
    items: list[dict]
    candidates: dict
    selections: dict
    history: list[dict] = []
    text: str


@app.post("/cart/chat")
async def cart_chat(body: ShopChatIn):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(503, "ANTHROPIC_API_KEY is not set")
    try:
        return await shopper.shop_chat(body.items, body.candidates, body.selections, body.history, body.text)
    except anthropic.APIError as e:
        raise HTTPException(502, _api_error(e))


@app.post("/cart/add")
async def cart_add(body: CartIn):
    client = get_client()
    results = []
    for line in body.lines:
        try:
            await client.add_to_cart(line.product_id, line.quantity)
            results.append({"key": line.key, "ok": True})
        except Exception as e:
            results.append({"key": line.key, "ok": False, "error": str(e)})
    return {"results": results}
