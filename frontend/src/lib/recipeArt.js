import { recipeBeef, recipeBreakfast, recipeChicken, recipeDefault, recipePasta, recipeSeafood, recipeSoup, recipeVeg } from "../assets";

// First match wins, so a "pasta" tag beats "chili" in the title (Chili Mac is pasta, not soup).
const CATEGORIES = [
  [recipeSoup, /\b(soup|stew|chili|chowder|broth)\b/],
  [recipePasta, /\b(pasta|noodles?|spaghetti|macaroni|lasagna|ramen|mac)\b/],
  [recipeChicken, /\b(chicken|poultry|turkey)\b/],
  [recipeBeef, /\b(beef|steak|pork|sausage|lamb|burger|ribs?|meatballs?)\b/],
  [recipeSeafood, /\b(fish|salmon|seafood|shrimp|cod|tuna|crab)\b/],
  [recipeVeg, /\b(vegetarian|vegan|salad|vegetables?|veggie)\b/],
  [recipeBreakfast, /\b(breakfast|brunch|eggs?|pancakes?|waffles?|baking|baked)\b/],
];

/** Picks an illustration for a recipe: tags first, then the title, then the default. */
export function recipeArt(recipe) {
  for (const text of [(recipe.tags || []).join(" "), recipe.title || ""]) {
    const t = text.toLowerCase();
    for (const [art, re] of CATEGORIES) if (re.test(t)) return art;
  }
  return recipeDefault;
}

/** The recipe's own cover photo if one was uploaded, otherwise the illustration for its type. */
export function recipeImage(recipe) {
  return recipe.cover_updated ? `/api/recipes/${recipe.id}/cover?v=${recipe.cover_updated}` : recipeArt(recipe);
}
