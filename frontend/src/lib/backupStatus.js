const STALE_HOURS = 36; // the copy job runs daily; a day and a half without one means something is wrong

/** What to tell the household about backups: { level: "ok" | "warn" | "pending", text }. */
export function describeBackup(status) {
  const off = status?.offsite;
  if (!off) return { level: "pending", text: "The copy to the external drive hasn't run yet. It runs nightly." };
  if (!off.ok) return { level: "warn", text: `The last backup to the external drive failed: ${off.message}` };
  if (off.age_hours > STALE_HOURS) {
    const days = Math.round(off.age_hours / 24);
    return { level: "warn", text: `No backup to the external drive for ${days} day${days === 1 ? "" : "s"}. Check that it's plugged in.` };
  }
  const when = off.age_hours < 1 ? "less than an hour ago" : off.age_hours < 36 ? `${Math.round(off.age_hours)} h ago` : `${Math.round(off.age_hours / 24)} days ago`;
  const photos = off.images === 1 ? "1 photo" : `${off.images ?? 0} photos`;
  return { level: "ok", text: `Backed up to the external drive ${when} (${photos}).` };
}
