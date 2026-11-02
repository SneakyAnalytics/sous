"""Deterministic grocery math: parse, scale, merge and categorise ingredients.

Nothing here calls a language model. The chef writes recipes; the list is arithmetic.
"""
import re
from fractions import Fraction

# Everything in a family converts to its base unit (tsp for volume, oz for weight).
VOLUME = {"tsp": 1, "tbsp": 3, "fl oz": 6, "cup": 48, "ml": 0.2029, "l": 202.9}
WEIGHT = {"oz": 1, "lb": 16, "g": 0.03527, "kg": 35.274}

UNIT_ALIASES = {
    "teaspoon": "tsp", "teaspoons": "tsp", "tsp": "tsp", "t": "tsp",
    "tablespoon": "tbsp", "tablespoons": "tbsp", "tbsp": "tbsp", "tbs": "tbsp", "tbl": "tbsp",
    "cup": "cup", "cups": "cup", "c": "cup",
    "fluid ounce": "fl oz", "fluid ounces": "fl oz", "fl oz": "fl oz",
    "ml": "ml", "milliliter": "ml", "milliliters": "ml",
    "l": "l", "liter": "l", "liters": "l", "litre": "l", "litres": "l",
    "oz": "oz", "ounce": "oz", "ounces": "oz",
    "lb": "lb", "lbs": "lb", "pound": "lb", "pounds": "lb",
    "g": "g", "gram": "g", "grams": "g",
    "kg": "kg", "kilogram": "kg", "kilograms": "kg",
    "clove": "clove", "cloves": "clove",
    "can": "can", "cans": "can",
    "bunch": "bunch", "bunches": "bunch",
    "pinch": "pinch", "pinches": "pinch",
    "slice": "slice", "slices": "slice",
    "stick": "stick", "sticks": "stick",
    "package": "package", "packages": "package", "pkg": "package",
}

CATEGORIES = [
    ("Produce", "onion garlic ginger lemon lime tomato potato carrot celery pepper lettuce spinach kale "
                "basil cilantro parsley thyme rosemary mint dill scallion shallot mushroom zucchini squash "
                "cucumber avocado apple banana berry berries broccoli cauliflower cabbage herb chive jalapeno "
                "eggplant asparagus corn sage orange"),
    ("Meat & Seafood", "chicken beef pork bacon sausage turkey lamb steak shrimp salmon fish cod ham "
                       "prosciutto ground"),
    ("Dairy & Eggs", "milk butter cream cheese yogurt egg eggs parmesan mozzarella cheddar sour"),
    ("Bakery", "bread bun buns tortilla pita baguette naan roll rolls"),
    ("Canned & Dry Goods", "rice pasta noodle noodles flour sugar bean beans lentil lentils broth stock "
                           "tomatoes paste can oats quinoa couscous breadcrumbs panko"),
    ("Spices & Baking", "salt pepper paprika cumin oregano cinnamon nutmeg chili powder vanilla baking "
                        "yeast cornstarch turmeric coriander cayenne flakes seasoning"),
    ("Oils & Condiments", "oil vinegar soy sauce mustard mayo mayonnaise ketchup honey syrup sriracha "
                          "worcestershire salsa wine"),
    ("Frozen", "frozen ice"),
]
CATEGORY_ORDER = [c for c, _ in CATEGORIES] + ["Other"]

_FRACTIONS = {"½": "1/2", "¼": "1/4", "¾": "3/4", "⅓": "1/3", "⅔": "2/3", "⅛": "1/8"}
_QTY = re.compile(r"^\s*(\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)(?:\s*(?:-|–|to)\s*(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?))?\s*")


def _to_float(s: str) -> float:
    return float(sum(Fraction(p) for p in s.split()))


def categorize(name: str) -> str:
    words = set(re.findall(r"[a-z]+", name.lower()))
    for category, keywords in CATEGORIES:
        if words & set(keywords.split()):
            return category
    return "Other"


def normalize_unit(unit: str | None) -> str:
    u = (unit or "").strip().lower().rstrip(".")
    return UNIT_ALIASES.get(u, u)


def parse_ingredient(line: str) -> dict:
    """'1 1/2 cups all-purpose flour, sifted' -> {quantity, unit, name, note}. Unparseable lines keep their text."""
    text = line.strip()
    for glyph, plain in _FRACTIONS.items():
        text = text.replace(glyph, f" {plain}")
    note = ""
    if "," in text:
        text, note = (p.strip() for p in text.split(",", 1))
    text = re.sub(r"\(([^)]*)\)", lambda m: "", text).strip()
    quantity = None
    m = _QTY.match(text)
    if m:
        quantity = _to_float(m.group(1))
        text = text[m.end():]
    unit = ""
    for n in (2, 1):  # "fl oz" before single words
        words = text.split(None, n)
        if len(words) > n and normalize_unit(" ".join(words[:n])) in {**VOLUME, **WEIGHT, **{v: 1 for v in UNIT_ALIASES.values()}}:
            unit = normalize_unit(" ".join(words[:n]))
            text = words[n]
            break
    text = re.sub(r"^of\s+", "", text.strip())
    return {"quantity": quantity, "unit": unit, "name": text, "note": note, "category": categorize(text)}


def _family(unit: str):
    if unit in VOLUME:
        return "vol", VOLUME[unit]
    if unit in WEIGHT:
        return "wt", WEIGHT[unit]
    return None, 1


def _singular(name: str) -> str:
    n = name.lower().strip()
    for suffix, repl in (("ies", "y"), ("oes", "o"), ("s", "")):
        if n.endswith(suffix) and not n.endswith("ss") and len(n) > 3:
            return n[: -len(suffix)] + repl
    return n


def merge_key(name: str, unit: str) -> str:
    fam, _ = _family(unit)
    return f"{_singular(name)}|{fam or unit}"


def _humanize(base_qty: float, fam: str | None, unit: str) -> tuple[float, str]:
    if fam == "vol":
        if base_qty >= 48:
            return base_qty / 48, "cup"
        if base_qty >= 3:
            return base_qty / 3, "tbsp"
        return base_qty, "tsp"
    if fam == "wt":
        return (base_qty / 16, "lb") if base_qty >= 16 else (base_qty, "oz")
    return base_qty, unit


def fmt_qty(q: float | None) -> str:
    if q is None:
        return ""
    whole = int(q)
    frac = Fraction(q - whole).limit_denominator(8)
    if frac == 1:
        whole, frac = whole + 1, Fraction(0)
    parts = [str(whole)] if whole or not frac else []
    if frac:
        parts.append(f"{frac.numerator}/{frac.denominator}")
    return " ".join(parts)


def build_list(plan_items: list[dict]) -> list[dict]:
    """plan_items: [{recipe: {...}, servings: int}]. Returns merged, scaled, categorised items."""
    merged: dict[str, dict] = {}
    for item in plan_items:
        recipe = item["recipe"]
        scale = item["servings"] / max(recipe["servings"], 1)
        for ing in recipe["ingredients"]:
            unit = normalize_unit(ing.get("unit"))
            qty = ing.get("quantity")
            name = ing["name"].strip()
            fam, factor = _family(unit)
            key = merge_key(name, unit)
            entry = merged.setdefault(key, {
                "key": key, "name": name.lower(), "family": fam, "unit": unit, "base_qty": 0.0,
                "has_qty": False, "category": ing.get("category") or categorize(name), "recipes": [],
            })
            if qty is not None:
                entry["base_qty"] += qty * scale * factor
                entry["has_qty"] = True
            if recipe["title"] not in entry["recipes"]:
                entry["recipes"].append(recipe["title"])
    out = []
    for e in merged.values():
        qty, unit = (None, e["unit"])
        if e["has_qty"]:
            qty, unit = _humanize(e["base_qty"], e["family"], e["unit"])
        out.append({
            "key": e["key"], "name": e["name"], "quantity": qty, "unit": unit,
            "display": " ".join(p for p in (fmt_qty(qty), unit) if p),
            "category": e["category"], "recipes": e["recipes"],
        })
    out.sort(key=lambda i: (CATEGORY_ORDER.index(i["category"]) if i["category"] in CATEGORY_ORDER else 99, i["name"]))
    return out
