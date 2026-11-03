import { describe, expect, it } from "vitest";
import { browse, cookedLine } from "./browse";

const r = (id, title, extra = {}) => ({ id, title, favorite: false, cook_count: 0, rating: null, last_cooked: null, ...extra });
const list = [
  r(1, "Soup", { cook_count: 3, rating: 4, last_cooked: "2026-11-01", favorite: true }),
  r(2, "Chili Mac", { cook_count: 1, rating: 5, last_cooked: "2026-10-20" }),
  r(3, "apple pie"),
  r(4, "Tacos", { cook_count: 6, rating: 3, last_cooked: "2026-09-02" }),
];
const ids = (rs) => rs.map((x) => x.id);

describe("browse", () => {
  it("filters", () => {
    expect(ids(browse(list, "favorites", "newest"))).toEqual([1]);
    expect(ids(browse(list, "cooked", "newest"))).toEqual([1, 2, 4]);
    expect(ids(browse(list, "new", "newest"))).toEqual([3]);
  });
  it("sorts", () => {
    expect(ids(browse(list, "all", "rating"))).toEqual([2, 1, 4, 3]);
    expect(ids(browse(list, "all", "recent"))).toEqual([1, 2, 4, 3]);
    expect(ids(browse(list, "all", "most"))).toEqual([4, 1, 2, 3]);
    expect(ids(browse(list, "all", "az"))).toEqual([3, 2, 1, 4]); // case-insensitive
    expect(ids(browse(list, "all", "newest"))).toEqual([1, 2, 3, 4]); // server order untouched
  });
  it("describes cooking history", () => {
    expect(cookedLine(list[2])).toBe("Not cooked yet");
    expect(cookedLine(r(9, "x", { cook_count: 1, last_cooked: "2026-11-01" }))).toMatch(/^Cooked 1 time, last /);
    expect(cookedLine(list[0])).toMatch(/^Cooked 3 times, last /);
  });
});
