import { describe, expect, it } from "vitest";
import { parseQty } from "./qty";

describe("parseQty", () => {
  it("reads whole numbers, decimals, fractions and mixed numbers", () => {
    expect(parseQty("2")).toBe(2);
    expect(parseQty("0.25")).toBe(0.25);
    expect(parseQty("1/2")).toBe(0.5);
    expect(parseQty("1 1/2")).toBe(1.5);
    expect(parseQty(" 2  3/4 ")).toBe(2.75);
    expect(parseQty("½")).toBe(0.5);
    expect(parseQty("1½")).toBe(1.5);
  });
  it("treats blank as no quantity, and junk as invalid", () => {
    expect(parseQty("")).toBeNull();
    expect(parseQty(null)).toBeNull();
    expect(parseQty("a pinch")).toBeUndefined();
    expect(parseQty("1/0")).toBeUndefined();
  });
});
