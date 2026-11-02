"""Import a recipe from a URL via its schema.org/Recipe JSON-LD (what most recipe sites publish)."""
import html
import json
import re

import httpx

from .grocery import parse_ingredient

_LD = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I)


def _find_recipe(node):
    if isinstance(node, list):
        for n in node:
            if (r := _find_recipe(n)):
                return r
    elif isinstance(node, dict):
        t = node.get("@type")
        if t == "Recipe" or (isinstance(t, list) and "Recipe" in t):
            return node
        return _find_recipe(node.get("@graph", []))
    return None


def _minutes(iso: str | None) -> int | None:
    m = re.fullmatch(r"P(?:\d+D)?T?(?:(\d+)H)?(?:(\d+)M)?", iso or "")
    return (int(m.group(1) or 0) * 60 + int(m.group(2) or 0)) or None if m else None


def _steps(instr) -> list[dict]:
    out = []
    if isinstance(instr, str):
        instr = [s for s in re.split(r"\n+", instr) if s.strip()]
    for s in instr or []:
        if isinstance(s, dict) and s.get("itemListElement"):
            out += _steps(s["itemListElement"])
        elif isinstance(s, dict):
            out.append({"text": html.unescape(s.get("text", "")).strip()})
        else:
            out.append({"text": html.unescape(str(s)).strip()})
    return [s for s in out if s["text"]]


def parse_recipe_html(page: str, url: str) -> dict:
    for block in _LD.findall(page):
        try:
            found = _find_recipe(json.loads(block))
        except json.JSONDecodeError:
            continue
        if found:
            servings = re.search(r"\d+", str(found.get("recipeYield", "")))
            keywords = found.get("keywords") or ""
            tags = keywords if isinstance(keywords, list) else [k.strip() for k in keywords.split(",") if k.strip()]
            return {
                "title": html.unescape(found.get("name", "Untitled recipe")),
                "description": html.unescape(re.sub(r"<[^>]+>", "", found.get("description", "") or "")),
                "servings": int(servings.group()) if servings else 4,
                "prep_min": _minutes(found.get("prepTime")),
                "cook_min": _minutes(found.get("cookTime")),
                "ingredients": [parse_ingredient(html.unescape(i)) for i in found.get("recipeIngredient", [])],
                "steps": _steps(found.get("recipeInstructions")),
                "chef_tips": [],
                "tags": tags[:8],
                "source_url": url,
            }
    raise ValueError("No recipe data found on that page")


def import_from_url(url: str) -> dict:
    resp = httpx.get(url, follow_redirects=True, timeout=20, headers={"User-Agent": "Mozilla/5.0 (recipe-app)"})
    resp.raise_for_status()
    return parse_recipe_html(resp.text, url)
