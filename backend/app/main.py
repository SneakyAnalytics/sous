import os
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import chef, grocery, importer, store
from .db import init_db
from .safeway import SafewayError, get_client


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Sous", lifespan=lifespan)


@app.get("/health")
def health():
    return {"ok": True}


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
    return chef.chat(body.text)


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


class StatusIn(BaseModel):
    status: Literal["have", "need"] | None


def _week(week_start: str) -> str:
    try:
        return store.valid_week(week_start)
    except ValueError:
        raise HTTPException(422, "week_start must be YYYY-MM-DD")


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
    return {"week_start": store.current_week_start()}


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
def plan_add(week_start: str, body: PlanAdd):
    recipe = store.get_recipe(body.recipe_id)
    if not recipe:
        raise HTTPException(404, "recipe not found")
    week_start = _week(week_start)
    _check_day(week_start, body.cook_date)
    store.add_plan_item(week_start, recipe["id"], body.servings or recipe["servings"], body.cook_date)
    return plan_get(week_start)


@app.patch("/plan/items/{item_id}")
def plan_patch(item_id: int, body: PlanPatch):
    fields = body.model_dump(exclude_unset=True)
    item = store.get_plan_item(item_id)
    if not item:
        raise HTTPException(404)
    _check_day(item["week_start"], fields.get("cook_date"))
    store.update_plan_item(item_id, fields)


@app.delete("/plan/items/{item_id}")
def plan_remove(item_id: int):
    store.remove_plan_item(item_id)


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
