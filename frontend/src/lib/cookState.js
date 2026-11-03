// Cook mode state that must outlive a step change or a page reload: which step you're on, what's checked off,
// and every step's timer. Timers store an absolute end time, so they keep counting while the phone is locked.

const TTL_MS = 6 * 60 * 60 * 1000; // a half-finished cook is resumed for six hours, then forgotten

export const newTimer = (total) => ({ total, left: total, endAt: null, ringing: false });

export function remaining(t, now) {
  return t.endAt ? Math.max(0, Math.ceil((t.endAt - now) / 1000)) : t.left;
}
export const isRunning = (t) => t.endAt != null;

export function startTimer(t, now) {
  return { ...t, endAt: now + t.left * 1000, ringing: false };
}
export function pauseTimer(t, now) {
  return { ...t, left: remaining(t, now), endAt: null };
}

/** Marks every running timer that has run out as ringing. Returns the new timers and the steps that just rang. */
export function tick(timers, now) {
  const rang = [];
  const next = {};
  for (const [step, t] of Object.entries(timers)) {
    if (t.endAt && t.endAt <= now) {
      next[step] = { ...t, left: 0, endAt: null, ringing: true };
      rang.push(+step);
    } else next[step] = t;
  }
  return { timers: rang.length ? next : timers, rang };
}

const key = (recipeId) => `sous-cook-${recipeId}`;

export function saveCook(recipeId, state, now = Date.now()) {
  try { localStorage.setItem(key(recipeId), JSON.stringify({ ...state, savedAt: now })); } catch { /* storage full or blocked */ }
}
export function clearCook(recipeId) {
  try { localStorage.removeItem(key(recipeId)); } catch { /* ignore */ }
}
/** The saved state for this recipe at these servings, or null if there is none, it is stale, or it doesn't fit. */
export function loadCook(recipeId, servings, now = Date.now()) {
  try {
    const s = JSON.parse(localStorage.getItem(key(recipeId)) || "null");
    if (!s || now - s.savedAt > TTL_MS || s.servings !== servings) return null;
    // a timer that ran out while the app was closed rings on return
    return { ...s, timers: tick(s.timers || {}, now).timers };
  } catch { return null; }
}
