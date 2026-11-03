import { describe, expect, it } from "vitest";
import { recipeArt } from "./recipeArt";
import { recipeBeef, recipeChicken, recipeDefault, recipePasta, recipeSeafood, recipeSoup } from "../assets";

describe("recipeArt", () => {
  it("uses tags before the title", () => {
    expect(recipeArt({ title: "Dutch Oven Chili Mac", tags: ["pasta", "one pot"] })).toBe(recipePasta);
    expect(recipeArt({ title: "Dutch Oven Sausage & White Bean Soup", tags: ["soup", "dutch oven"] })).toBe(recipeSoup);
  });
  it("falls back to the title, then the default", () => {
    expect(recipeArt({ title: "Seared salmon", tags: [] })).toBe(recipeSeafood);
    expect(recipeArt({ title: "Lemon chicken thighs" })).toBe(recipeChicken);
    expect(recipeArt({ title: "Pork chops", tags: [] })).toBe(recipeBeef);
    expect(recipeArt({ title: "Mystery casserole", tags: [] })).toBe(recipeDefault);
  });
});
