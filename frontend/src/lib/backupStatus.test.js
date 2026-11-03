import { describe, expect, it } from "vitest";
import { describeBackup } from "./backupStatus";

describe("describeBackup", () => {
  it("is pending until the first run", () => {
    expect(describeBackup({ offsite: null }).level).toBe("pending");
    expect(describeBackup(undefined).level).toBe("pending");
  });
  it("is ok for a recent good run", () => {
    const d = describeBackup({ offsite: { ok: true, age_hours: 3.2, images: 1 } });
    expect(d).toEqual({ level: "ok", text: "Backed up to the external drive 3 h ago (1 photo)." });
  });
  it("warns on a failed run, with the reason", () => {
    const d = describeBackup({ offsite: { ok: false, age_hours: 1, message: "backup drive D: is not connected" } });
    expect(d.level).toBe("warn");
    expect(d.text).toContain("D: is not connected");
  });
  it("warns when the last good run is stale, even though it succeeded", () => {
    const d = describeBackup({ offsite: { ok: true, age_hours: 80, images: 4 } });
    expect(d.level).toBe("warn");
    expect(d.text).toContain("3 days");
  });
});
