import { scaleIngredient } from "./format";

// Last words that don't identify an ingredient on their own ("red pepper flakes" -> "flakes").
const GENERIC = new Set(["flakes", "leaves", "leaf", "powder", "sauce", "paste", "oil", "stock", "cream", "juice"]);

const singular = (w) => (w.length > 3 && w.endsWith("es") && /(?:ch|sh|x|s|o)es$/.test(w) ? w.slice(0, -2) : w.length > 3 && w.endsWith("s") ? w.slice(0, -1) : w);

/** Phrases a step might use to refer to an ingredient, longest first: "italian sausage", "sausage". */
export function ingredientTerms(name) {
  const out = [];
  // "salt and pepper" is two things a step can mention separately.
  for (const part of name.toLowerCase().replace(/\(.*?\)/g, "").split(/\s+and\s+|,/)) {
    const words = part.trim().split(/\s+/).filter(Boolean);
    if (!words.length) continue;
    for (let n = words.length; n >= 1; n--) {
      const tail = words.slice(-n);
      if (n === 1 && (GENERIC.has(tail[0]) || tail[0].length < 3)) continue;
      out.push(tail.map(singular).join(" "));
    }
  }
  return [...new Set(out)];
}

/**
 * Finds ingredient mentions in a step's text. Longer phrases win, so "pepper flakes" is not also read as "pepper".
 * Returns non-overlapping matches sorted by position: [{ start, end, index }] (index into `ingredients`).
 */
export function findMentions(text, ingredients) {
  const candidates = [];
  ingredients.forEach((ing, index) => {
    for (const term of ingredientTerms(ing.name)) {
      const re = new RegExp(`\\b${term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/ /g, "\\s+")}(?:e?s)?\\b`, "gi");
      for (const m of text.matchAll(re)) candidates.push({ start: m.index, end: m.index + m[0].length, index, len: term.length });
    }
  });
  candidates.sort((a, b) => b.len - a.len || a.start - b.start);
  const taken = [];
  for (const c of candidates) {
    if (!taken.some((t) => c.start < t.end && t.start < c.end)) taken.push(c);
  }
  return taken.sort((a, b) => a.start - b.start).map(({ start, end, index }) => ({ start, end, index }));
}

/** The text split into plain and ingredient pieces: [{ text }, { text, index }]. */
export function segmentStep(text, ingredients) {
  const out = [];
  let at = 0;
  for (const m of findMentions(text, ingredients)) {
    if (m.start > at) out.push({ text: text.slice(at, m.start) });
    out.push({ text: text.slice(m.start, m.end), index: m.index });
    at = m.end;
  }
  if (at < text.length) out.push({ text: text.slice(at) });
  return out;
}

/** Distinct ingredient indexes a step uses, in the order they first appear. */
export function usedIngredients(text, ingredients) {
  return [...new Set(findMentions(text, ingredients).map((m) => m.index))];
}

export function amountLabel(ing, factor) {
  const label = scaleIngredient(ing, factor);
  return ing.note ? `${label}, ${ing.note}` : label;
}
