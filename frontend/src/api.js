async function request(path, options = {}) {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch { /* not JSON */ }
    throw new Error(detail);
  }
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

export const api = {
  chat: () => request("/chat"),
  sendChat: (text) => request("/chat", { method: "POST", body: { text } }),
  clearChat: () => request("/chat", { method: "DELETE" }),
  recipes: (q = "") => request(`/recipes?q=${encodeURIComponent(q)}`),
  recipe: (id) => request(`/recipes/${id}`),
  patchRecipe: (id, body) => request(`/recipes/${id}`, { method: "PATCH", body }),
  deleteRecipe: (id) => request(`/recipes/${id}`, { method: "DELETE" }),
  importRecipe: (url) => request("/recipes/import", { method: "POST", body: { url } }),
  currentWeek: () => request("/plan/current-week"),
  plan: (week) => request(`/plan/${week}`),
  addToPlan: (week, recipe_id, servings) => request(`/plan/${week}/items`, { method: "POST", body: { recipe_id, servings } }),
  patchPlanItem: (id, body) => request(`/plan/items/${id}`, { method: "PATCH", body }),
  removePlanItem: (id) => request(`/plan/items/${id}`, { method: "DELETE" }),
  setStatus: (week, key, status) => request(`/plan/${week}/list/${encodeURIComponent(key)}`, { method: "PUT", body: { status } }),
  cartMatch: (names) => request("/cart/match", { method: "POST", body: { names } }),
  cartAdd: (lines) => request("/cart/add", { method: "POST", body: { lines } }),
};
