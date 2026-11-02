import { describe, expect, it } from "vitest";
import { ingredientTerms, segmentStep, usedIngredients } from "./ingredients";

const ings = [
  { name: "Italian sausage" }, { name: "carrots" }, { name: "garlic" }, { name: "dried thyme" },
  { name: "crushed red pepper flakes" }, { name: "chicken broth" }, { name: "diced tomatoes" }, { name: "white beans" },
  { name: "bay leaves" }, { name: "salt and pepper" }, { name: "yellow onion" }, { name: "celery" },
];
const names = (text) => usedIngredients(text, ings).map((i) => ings[i].name);

describe("ingredient matching", () => {
  it("derives specific phrases, skipping generic last words", () => {
    expect(ingredientTerms("crushed red pepper flakes")).toEqual(["crushed red pepper flake", "red pepper flake", "pepper flake"]);
    expect(ingredientTerms("salt and pepper")).toEqual(["salt", "pepper"]);
  });
  it("matches singular and plural mentions", () => {
    expect(names("Add the onion, carrots and celery.")).toEqual(["yellow onion", "carrots", "celery"]);
    expect(names("Stir in the bean and one carrot")).toEqual(["white beans", "carrots"]);
  });
  it("prefers the longer phrase over a shorter one", () => {
    expect(names("Add the garlic, thyme and pepper flakes.")).toEqual(["garlic", "dried thyme", "crushed red pepper flakes"]);
  });
  it("finds partial names and ignores unrelated words", () => {
    expect(names("Crumble the sausage and cook until browned.")).toEqual(["Italian sausage"]);
    expect(names("Pour in half the broth and the diced tomatoes with the bay leaves.")).toEqual(["chicken broth", "diced tomatoes", "bay leaves"]);
    expect(names("Simmer until tender.")).toEqual([]);
  });
  it("splits text into segments that rejoin to the original", () => {
    const text = "Brown the sausage, then add garlic.";
    const segs = segmentStep(text, ings);
    expect(segs.map((s) => s.text).join("")).toBe(text);
    expect(segs.filter((s) => s.index !== undefined).map((s) => s.text)).toEqual(["sausage", "garlic"]);
  });
});
