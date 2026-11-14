import { describe, expect, it } from "vitest";
import { describeBackup } from "./backupStatus";

describe("describeBackup", () => {
  it("is pending until the first run", () => {
    expect(describeBackup({ offsite: null }).level).toBe("pending");
    expect(describeBackup(undefined).level).toBe("pending");
  });
  it("is ok for a recent good run", () => {
    const d = describeBackup({ offsite: { ok: true, age_hours: 2.2, images: 1 } });
    expect(d).toEqual({ level: "ok", text: "Backed up to the external drive 2 h ago (1 photo)." });
    expect(describeBackup({ offsite: { ok: true, age_hours: 0.1, images: 0 } }).text).toBe("Backed up to the external drive less than an hour ago (0 photos).");
  });
  it("warns on a failed run, with the reason", () => {
    const d = describeBackup({ offsite: { ok: false, age_hours: 1, message: "backup drive D: is not connected" } });
    expect(d.level).toBe("warn");
    expect(d.text).toContain("D: is not connected");
  });
  it("warns when the backup container has gone quiet, even though its last report was good", () => {
    const hours = describeBackup({ offsite: { ok: true, age_hours: 5, images: 4 } });
    expect(hours.level).toBe("warn");
    expect(hours.text).toContain("hasn't reported in 5 hours");
    const days = describeBackup({ offsite: { ok: true, age_hours: 80, images: 4 } });
    expect(days.text).toContain("3 days");
    expect(days.text).toContain("backup container may have stopped"); // the likely cause, alongside an unplugged drive
  });
});
