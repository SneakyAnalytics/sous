import React from "react";
import { Link } from "react-router-dom";
import { Clock, Star, Users } from "lucide-react";
import { totalMinutes } from "../lib/format";
import { recipeImage } from "../lib/recipeArt";
import { cookedLine } from "../lib/browse";

export default function RecipeCard({ recipe }) {
  const mins = totalMinutes(recipe);
  return (
    <Link to={`/recipes/${recipe.id}`} className="card recipe-card">
      <img className="thumb" src={recipeImage(recipe)} alt="" loading="lazy" />
      <h3>{recipe.favorite && <Star size={16} fill="currentColor" style={{ color: "var(--color-gravel)" }} />} {recipe.title}</h3>
      <div className="muted row" style={{ gap: ".9rem" }}>
        {mins && <span><Clock size={14} /> {mins} min</span>}
        <span><Users size={14} /> {recipe.servings}</span>
        {recipe.rating && <span style={{ color: "var(--color-gravel)" }}>{"★".repeat(recipe.rating)}</span>}
      </div>
      <div className="muted" style={{ fontSize: ".85rem" }}>{cookedLine(recipe)}</div>
      {recipe.description && <p className="muted" style={{ margin: 0 }}>{recipe.description}</p>}
      <div className="row" style={{ gap: ".3rem" }}>{recipe.tags.slice(0, 3).map((t) => <span key={t} className="chip">{t}</span>)}</div>
    </Link>
  );
}
