import { beforeEach, describe, expect, it } from "vitest";
import { clearCook, isRunning, loadCook, newTimer, pauseTimer, remaining, saveCook, startTimer, tick } from "./cookState";

beforeEach(() => {
  const store = {};
  globalThis.localStorage = { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = String(v); }, removeItem: (k) => { delete store[k]; } };
});

describe("cook timers", () => {
  it("counts down from the stored end time and pauses where it was", () => {
    const t = startTimer(newTimer(600), 1_000_000);
    expect(isRunning(t)).toBe(true);
    expect(remaining(t, 1_000_000 + 90_000)).toBe(510);
    const paused = pauseTimer(t, 1_000_000 + 90_000);
    expect(isRunning(paused)).toBe(false);
    expect(remaining(paused, 9_999_999)).toBe(510);
    expect(remaining(startTimer(paused, 5_000_000), 5_000_000 + 10_000)).toBe(500);
  });
  it("tick rings only the timers that ran out, and leaves the object alone when none did", () => {
    const timers = { 2: startTimer(newTimer(60), 0), 7: startTimer(newTimer(1680), 0) };
    const early = tick(timers, 30_000);
    expect(early.rang).toEqual([]);
    expect(early.timers).toBe(timers);
    const later = tick(timers, 61_000);
    expect(later.rang).toEqual([2]);
    expect(later.timers[2]).toMatchObject({ ringing: true, left: 0, endAt: null });
    expect(isRunning(later.timers[7])).toBe(true);
  });
});

describe("cook persistence", () => {
  const state = { i: 7, checked: { 0: true }, servings: 4, timers: { 7: startTimer(newTimer(1680), 1_000_000) } };
  it("resumes the step, checks and a still-running timer", () => {
    saveCook("1", state, 1_000_000);
    const got = loadCook("1", 4, 1_000_000 + 600_000);
    expect(got.i).toBe(7);
    expect(got.checked).toEqual({ 0: true });
    expect(remaining(got.timers[7], 1_000_000 + 600_000)).toBe(1080);
  });
  it("rings a timer that ran out while the app was closed", () => {
    saveCook("1", state, 1_000_000);
    expect(loadCook("1", 4, 1_000_000 + 1_800_000).timers[7].ringing).toBe(true);
  });
  it("ignores stale, other-serving or cleared state", () => {
    saveCook("1", state, 1_000_000);
    expect(loadCook("1", 6, 1_000_100)).toBeNull();
    expect(loadCook("1", 4, 1_000_000 + 7 * 3600 * 1000)).toBeNull();
    clearCook("1");
    expect(loadCook("1", 4, 1_000_100)).toBeNull();
  });
});
