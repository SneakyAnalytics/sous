import { describe, expect, it } from "vitest";
import { swipeDirection } from "./swipe";

describe("swipeDirection", () => {
  it("swipes left for next and right for back", () => {
    expect(swipeDirection(-120, 10)).toBe("next");
    expect(swipeDirection(120, -10)).toBe("back");
  });
  it("ignores short moves and vertical scrolls", () => {
    expect(swipeDirection(-40, 0)).toBeNull();
    expect(swipeDirection(-100, 90)).toBeNull(); // mostly a scroll
    expect(swipeDirection(0, 200)).toBeNull();
  });
});
