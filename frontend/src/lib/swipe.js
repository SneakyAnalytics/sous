/** "next" | "back" | null for a touch that moved (dx, dy) px: it must be a deliberate, mostly-horizontal swipe. */
export function swipeDirection(dx, dy, minDistance = 70) {
  if (Math.abs(dx) < minDistance || Math.abs(dx) < Math.abs(dy) * 1.5) return null;
  return dx < 0 ? "next" : "back";
}
