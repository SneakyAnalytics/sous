const STALE_HOURS = 3; // the backup container reports every 10 minutes; three hours of silence means it has stopped

/** What to tell the household about backups: { level: "ok" | "warn" | "pending", text }. */
export function describeBackup(status) {
  const off = status?.offsite;
  if (!off) return { level: "pending", text: "The copy to the external drive hasn't reported yet." };
  if (!off.ok) return { level: "warn", text: `The last backup to the external drive failed: ${off.message}` };
  if (off.age_hours > STALE_HOURS) {
    const ago = off.age_hours < 48 ? `${Math.round(off.age_hours)} hours` : `${Math.round(off.age_hours / 24)} days`;
    return { level: "warn", text: `The external-drive backup hasn't reported in ${ago}. The backup container may have stopped, or the drive may be unplugged.` };
  }
  const when = off.age_hours < 1 ? "less than an hour ago" : off.age_hours < 36 ? `${Math.round(off.age_hours)} h ago` : `${Math.round(off.age_hours / 24)} days ago`;
  const photos = off.images === 1 ? "1 photo" : `${off.images ?? 0} photos`;
  return { level: "ok", text: `Backed up to the external drive ${when} (${photos}).` };
}
