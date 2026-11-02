/** 1.5 -> "1 1/2". Mirrors the backend's fmt_qty so a scaled recipe reads like the grocery list. */
export function fmtQty(q) {
  if (q == null) return "";
  let whole = Math.floor(q);
  let num = Math.round((q - whole) * 8);
  let den = 8;
  if (num === 8) { whole += 1; num = 0; }
  while (num && num % 2 === 0) { num /= 2; den /= 2; }
  const parts = [];
  if (whole || !num) parts.push(String(whole));
  if (num) parts.push(`${num}/${den}`);
  return parts.join(" ");
}

export function scaleIngredient(ing, factor) {
  const qty = ing.quantity == null ? null : ing.quantity * factor;
  return [fmtQty(qty), ing.unit, ing.name].filter(Boolean).join(" ");
}

export function fmtClock(totalSeconds) {
  const s = Math.max(0, Math.round(totalSeconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function totalMinutes(r) {
  return (r.prep_min || 0) + (r.cook_min || 0) || null;
}

/** "Mon, Oct 26" for a YYYY-MM-DD string, without a timezone shift. */
export function weekLabel(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function shiftWeek(iso, weeks) {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(y, m - 1, d + weeks * 7);
  return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}-${String(dt.getDate()).padStart(2, "0")}`;
}
