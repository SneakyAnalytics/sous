/** How full each of the 5 stars is for a rating in half-star steps: 3.5 -> [1, 1, 1, 0.5, 0]. */
export function starFills(value) {
  const v = Math.round((value || 0) * 2) / 2;
  return [0, 1, 2, 3, 4].map((i) => Math.min(1, Math.max(0, v - i)));
}

/** The rating for a tap on the left (half) or right (whole) side of star number `star` (1 to 5). */
export function tapValue(star, leftHalf) {
  return leftHalf ? star - 0.5 : star;
}

/** Tapping the rating you already gave clears it. */
export function nextRating(current, tapped) {
  return current === tapped ? undefined : tapped;
}

/** 4 -> "4", 4.5 -> "4.5". */
export function fmtStars(value) {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}
