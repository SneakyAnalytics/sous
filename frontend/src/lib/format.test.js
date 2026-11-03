import { describe, expect, it } from "vitest";
import { fmtClock, fmtQty, scaleIngredient, shiftWeek, weekDays } from "./format";

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
  it("lists the seven days of a week, across a month end", () => {
    const days = weekDays("2026-10-26");
    expect(days.map((d) => d.iso)).toEqual(["2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30", "2026-10-31", "2026-11-01"]);
  });
});

import { fmtTime, mondayOf } from "./format";
describe("times and weeks", () => {
  it("formats 24-hour times for people", () => {
    expect(fmtTime("16:40")).toBe("4:40 PM");
    expect(fmtTime("00:05")).toBe("12:05 AM");
    expect(fmtTime("12:00")).toBe("12:00 PM");
    expect(fmtTime(null)).toBe("");
  });
  it("finds the Monday of any day, including Sundays and month boundaries", () => {
    expect(mondayOf("2026-11-01")).toBe("2026-10-26"); // a Sunday belongs to the week that started the Monday before
    expect(mondayOf("2026-11-02")).toBe("2026-11-02");
    expect(mondayOf("2026-11-04")).toBe("2026-11-02");
    expect(mondayOf("2026-01-01")).toBe("2025-12-29");
  });
});
