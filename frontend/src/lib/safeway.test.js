import { describe, expect, it } from "vitest";
import { searchQuery, searchUrl } from "./safeway";

describe("safeway search", () => {
  it("keeps plain ingredients as they are", () => {
    expect(searchQuery("yellow onion")).toBe("yellow onion");
    expect(searchQuery("Italian sausage")).toBe("italian sausage");
  });
  it("uses the first alternative and drops notes and brackets", () => {
    expect(searchQuery("white wine or chicken broth")).toBe("white wine");
    expect(searchQuery("parmesan, optional: a rind to simmer")).toBe("parmesan");
    expect(searchQuery("diced tomatoes (14 oz)")).toBe("diced tomatoes");
    expect(searchQuery("kale  ")).toBe("kale");
  });
  it("builds an encoded search link", () => {
    expect(searchUrl("bay leaves")).toBe("https://www.safeway.com/shop/search-results.html?q=bay%20leaves");
    expect(searchUrl("half & half")).toContain("q=half%20%26%20half");
  });
});
