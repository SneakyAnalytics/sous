from app.grocery import build_list, parse_ingredient


def recipe(title, servings, *lines):
    return {"title": title, "servings": servings, "ingredients": [parse_ingredient(l) for l in lines]}


def test_parse_mixed_fraction_and_note():
    p = parse_ingredient("1 1/2 cups all-purpose flour, sifted")
    assert (p["quantity"], p["unit"], p["name"], p["note"]) == (1.5, "cup", "all-purpose flour", "sifted")


def test_parse_unicode_fraction_and_no_unit():
    assert parse_ingredient("½ tsp salt")["quantity"] == 0.5
    p = parse_ingredient("3 large eggs")
    assert p["quantity"] == 3 and p["unit"] == "" and p["name"] == "large eggs"


def test_parse_fl_oz_and_range():
    assert parse_ingredient("2 fl oz lime juice")["unit"] == "fl oz"
    assert parse_ingredient("2-3 cloves garlic")["quantity"] == 2


def test_merge_across_volume_units():
    items = build_list([
        {"recipe": recipe("A", 4, "2 tbsp olive oil"), "servings": 4},
        {"recipe": recipe("B", 4, "1/4 cup olive oil"), "servings": 4},
    ])
    oil = [i for i in items if i["name"] == "olive oil"]
    assert len(oil) == 1 and oil[0]["display"] == "6 tbsp"


def test_scaling_by_servings_and_singular_merge():
    items = build_list([
        {"recipe": recipe("A", 2, "1 onion"), "servings": 4},
        {"recipe": recipe("B", 4, "2 onions"), "servings": 4},
    ])
    assert len(items) == 1 and items[0]["quantity"] == 4 and items[0]["recipes"] == ["A", "B"]


def test_different_unit_families_stay_separate_and_categorised():
    items = build_list([{"recipe": recipe("A", 1, "1 lb chicken thighs", "2 cloves garlic"), "servings": 1}])
    cats = {i["name"]: i["category"] for i in items}
    assert cats == {"chicken thighs": "Meat & Seafood", "garlic": "Produce"}


def test_plural_ingredients_are_categorized():
    from app.grocery import categorize
    assert categorize("carrots") == "Produce"
    assert categorize("yellow onions") == "Produce"
    assert categorize("diced tomatoes") in ("Produce", "Canned & Dry Goods")
    assert categorize("eggs") == "Dairy & Eggs"
    assert categorize("mystery thing") == "Other"


def test_a_stale_other_category_is_rechecked_when_building_the_list():
    from app.grocery import build_list
    recipe = {"title": "Soup", "servings": 4, "ingredients": [{"name": "carrots", "quantity": 3, "category": "Other"}]}
    assert build_list([{"recipe": recipe, "servings": 4}])[0]["category"] == "Produce"
