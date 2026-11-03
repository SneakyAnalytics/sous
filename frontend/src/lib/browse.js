export const FILTERS = [
  { id: "all", label: "All" },
  { id: "favorites", label: "Favorites" },
  { id: "cooked", label: "Cooked" },
  { id: "new", label: "Not cooked yet" },
];
export const SORTS = [
  { id: "newest", label: "Newest" },
  { id: "rating", label: "Highest rated" },
  { id: "recent", label: "Recently cooked" },
  { id: "most", label: "Most cooked" },
  { id: "az", label: "A to Z" },
];

const by = (key, dir = -1) => (a, b) => (a[key] > b[key] ? dir : a[key] < b[key] ? -dir : 0);

/** Filters then sorts the recipe list. `newest` keeps the server's order (favorites first, then newest). */
export function browse(recipes, filter, sort) {
  let out = recipes.filter((r) => ({
    all: true, favorites: r.favorite, cooked: (r.cook_count || 0) > 0, new: !(r.cook_count || 0),
  })[filter] ?? true);
  const rank = {
    rating: (a, b) => (b.rating || 0) - (a.rating || 0) || (b.cook_count || 0) - (a.cook_count || 0),
    recent: (a, b) => (b.last_cooked || "").localeCompare(a.last_cooked || ""),
    most: (a, b) => (b.cook_count || 0) - (a.cook_count || 0) || (b.rating || 0) - (a.rating || 0),
    az: (a, b) => a.title.localeCompare(b.title, undefined, { sensitivity: "base" }),
  }[sort];
  if (rank) out = [...out].sort(rank);
  return out;
}

/** "Cooked 3 times, last Nov 1" or "Not cooked yet". */
export function cookedLine(r) {
  const n = r.cook_count || 0;
  if (!n) return "Not cooked yet";
  const [y, m, d] = (r.last_cooked || "").split("-").map(Number);
  const last = y ? new Date(y, m - 1, d).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "";
  return `Cooked ${n} ${n === 1 ? "time" : "times"}${last ? `, last ${last}` : ""}`;
}
