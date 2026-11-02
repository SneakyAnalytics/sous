import { describe, expect, it } from "vitest";
import { fmtClock, fmtQty, scaleIngredient, shiftWeek } from "./format";

describe("format", () => {
  it("formats fractions", () => {
    expect(fmtQty(1.5)).toBe("1 1/2");
    expect(fmtQty(0.25)).toBe("1/4");
    expect(fmtQty(2)).toBe("2");
    expect(fmtQty(0.99)).toBe("1");
  });
  it("scales ingredients", () => {
    expect(scaleIngredient({ quantity: 1, unit: "cup", name: "rice" }, 1.5)).toBe("1 1/2 cup rice");
    expect(scaleIngredient({ quantity: null, unit: "", name: "salt" }, 2)).toBe("salt");
  });
  it("formats clocks", () => expect(fmtClock(605)).toBe("10:05"));
  it("shifts weeks across a month boundary", () => expect(shiftWeek("2026-10-26", 1)).toBe("2026-11-02"));
});
