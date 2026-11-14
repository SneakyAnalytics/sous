/** The phrase to search Safeway for: the ingredient without alternatives, notes or brackets ("white wine or broth" -> "white wine"). */
export function searchQuery(name) {
  return String(name || "")
    .toLowerCase()
    .replace(/\(.*?\)/g, " ")
    .split(/\s+or\s+|,|;/)[0]
    .replace(/\b(optional|to taste|for serving|for garnish)\b/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function searchUrl(name) {
  return `https://www.safeway.com/shop/search-results.html?q=${encodeURIComponent(searchQuery(name))}`;
}
