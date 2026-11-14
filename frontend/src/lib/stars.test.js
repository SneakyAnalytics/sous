import { describe, expect, it } from "vitest";
import { fmtStars, nextRating, starFills, tapValue } from "./stars";

describe("stars", () => {
  it("fills whole and half stars", () => {
    expect(starFills(3.5)).toEqual([1, 1, 1, 0.5, 0]);
    expect(starFills(5)).toEqual([1, 1, 1, 1, 1]);
    expect(starFills(0.5)).toEqual([0.5, 0, 0, 0, 0]);
    expect(starFills(0)).toEqual([0, 0, 0, 0, 0]);
    expect(starFills(undefined)).toEqual([0, 0, 0, 0, 0]);
  });
  it("snaps odd values to the nearest half instead of drawing a sliver", () => {
    expect(starFills(3.74)).toEqual([1, 1, 1, 0.5, 0]);
    expect(starFills(3.8)).toEqual([1, 1, 1, 1, 0]);
  });
  it("turns a tap on the left or right half of a star into a rating", () => {
    expect(tapValue(4, true)).toBe(3.5);
    expect(tapValue(4, false)).toBe(4);
    expect(tapValue(1, true)).toBe(0.5);
  });
  it("tapping the same rating again clears it", () => {
    expect(nextRating(3.5, 3.5)).toBeUndefined();
    expect(nextRating(3.5, 4)).toBe(4);
    expect(nextRating(undefined, 2)).toBe(2);
  });
  it("formats ratings without a trailing .0", () => {
    expect(fmtStars(4)).toBe("4");
    expect(fmtStars(4.5)).toBe("4.5");
  });
});
