const GLYPHS = { "½": "1/2", "¼": "1/4", "¾": "3/4", "⅓": "1/3", "⅔": "2/3", "⅛": "1/8" };

/** "1 1/2" -> 1.5, "½" -> 0.5, "2" -> 2, "" -> null. Returns undefined for something that isn't a quantity. */
export function parseQty(text) {
  let s = String(text ?? "").trim();
  if (!s) return null;
  for (const [g, plain] of Object.entries(GLYPHS)) s = s.replace(g, ` ${plain}`);
  let total = 0;
  for (const part of s.trim().split(/\s+/)) {
    const frac = part.match(/^(\d+)\/(\d+)$/);
    if (frac) {
      if (+frac[2] === 0) return undefined;
      total += +frac[1] / +frac[2];
    } else if (/^\d+(\.\d+)?$/.test(part)) total += parseFloat(part);
    else return undefined;
  }
  return total;
}
