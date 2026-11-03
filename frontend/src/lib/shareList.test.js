import { describe, expect, it } from "vitest";
import { groceryText } from "./shareList";

const list = [
  { name: "onion", display: "1", category: "Produce", status: "need" },
  { name: "carrots", display: "3", category: "Produce", status: null },
  { name: "salt", display: "1 tsp", category: "Spices & Baking", status: "have" },
  { name: "olive oil", display: "", category: "Oils & Condiments", status: "need" },
];

describe("groceryText", () => {
  it("lists what is not already in the house, by category", () => {
    expect(groceryText(list, "week of Nov 2")).toBe(
      "Groceries, week of Nov 2\n\nProduce\n• 1 onion\n• 3 carrots\n\nOils & Condiments\n• olive oil");
  });
  it("says so when there is nothing to buy", () => {
    expect(groceryText([list[2]], "week of Nov 2")).toBe("Groceries, week of Nov 2: nothing to buy.");
  });
});
