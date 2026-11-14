import React from "react";
import { Star } from "lucide-react";
import { fmtStars, nextRating, starFills, tapValue } from "../lib/stars";

/** One star, filled `fill` of the way across (0, 0.5 or 1). */
function StarShape({ fill, size }) {
  return (
    <span className="star" style={{ width: size, height: size }}>
      <Star size={size} className="star-empty" />
      {fill > 0 && <Star size={size} fill="currentColor" className="star-full" style={{ clipPath: `inset(0 ${(1 - fill) * 100}% 0 0)` }} />}
    </span>
  );
}

/** A rating drawn as five stars, with half stars. */
export function Stars({ value, size = 16 }) {
  return (
    <span className="stars" role="img" aria-label={`${fmtStars(value)} out of 5 stars`}>
      {starFills(value).map((fill, i) => <StarShape key={i} fill={fill} size={size} />)}
    </span>
  );
}

/**
 * Pick a rating from 0.5 to 5. Each star has two tap targets: the left half gives a half star, the right half a whole
 * one. Tap your current rating again to clear it.
 */
export function StarInput({ value, onChange, label, size = 36 }) {
  return (
    <span className="star-input">
      {[1, 2, 3, 4, 5].map((n) => (
        <span key={n} className="star-slot" style={{ width: size, height: size }}>
          <StarShape fill={starFills(value)[n - 1]} size={size} />
          {[true, false].map((left) => {
            const v = tapValue(n, left);
            return (
              <button key={String(left)} type="button" className={`star-hit ${left ? "left" : "right"}`} aria-label={`${label}: ${fmtStars(v)} stars`}
                aria-pressed={value === v} onClick={() => onChange(nextRating(value, v))} />
            );
          })}
        </span>
      ))}
      <span className="star-readout">{value ? fmtStars(value) : "–"}</span>
    </span>
  );
}
