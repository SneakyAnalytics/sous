import React, { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link as LinkIcon, Search } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import RecipeCard from "../components/RecipeCard";

export default function Recipes() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [url, setUrl] = useState("");
  const { data: recipes = [], isLoading } = useQuery({ queryKey: ["recipes", q], queryFn: () => api.recipes(q) });
  const importer = useMutation({
    mutationFn: api.importRecipe,
    onSuccess: (r) => { qc.invalidateQueries({ queryKey: ["recipes"] }); navigate(`/recipes/${r.id}`); },
  });

  return (
    <div className="page stack">
      <div className="page-head"><h1>Recipes</h1></div>
      <form className="row" onSubmit={(e) => { e.preventDefault(); url.trim() && importer.mutate(url.trim()); }}>
        <input type="url" placeholder="Paste a recipe URL to import…" value={url} onChange={(e) => setUrl(e.target.value)} style={{ flex: 1 }} />
        <button className="btn" disabled={importer.isPending || !url.trim()}><LinkIcon size={16} /> {importer.isPending ? "Importing…" : "Import"}</button>
      </form>
      {importer.isError && <div className="error">{importer.error.message}</div>}
      <div className="row"><Search size={18} /><input type="text" placeholder="Search by title, tag or ingredient" value={q} onChange={(e) => setQ(e.target.value)} style={{ flex: 1 }} /></div>
      {isLoading ? <p className="muted">Loading…</p> : recipes.length === 0 ? (
        <p className="muted">{q ? "Nothing matches." : "No recipes yet. Ask the Chef for one or import a URL."}</p>
      ) : (
        <div className="recipe-grid">{recipes.map((r) => <RecipeCard key={r.id} recipe={r} />)}</div>
      )}
    </div>
  );
}
