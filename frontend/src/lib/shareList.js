/** The grocery list as plain text for a message: what still needs buying, grouped like the store aisles. */
export function groceryText(list, weekTitle) {
  const toBuy = list.filter((i) => i.status !== "have");
  if (!toBuy.length) return `Groceries, ${weekTitle}: nothing to buy.`;
  const groups = toBuy.reduce((acc, i) => ((acc[i.category] ||= []).push(i), acc), {});
  const lines = [`Groceries, ${weekTitle}`];
  for (const [category, items] of Object.entries(groups)) {
    lines.push("", category);
    for (const i of items) lines.push(`• ${[i.display, i.name].filter(Boolean).join(" ")}`);
  }
  return lines.join("\n");
}

/** Opens the phone's share sheet when there is one, otherwise copies. Returns "shared" | "copied". */
export async function shareText(text, title) {
  if (navigator.share) {
    try { await navigator.share({ title, text }); return "shared"; } catch (e) { if (e.name === "AbortError") return "shared"; }
  }
  await navigator.clipboard.writeText(text);
  return "copied";
}
