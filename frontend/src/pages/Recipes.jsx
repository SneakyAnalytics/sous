import React, { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardPaste, Link as LinkIcon, Search, Undo2 } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";
import RecipeCard from "../components/RecipeCard";
import { emptySearch } from "../assets";
import { describeBackup } from "../lib/backupStatus";
import { FILTERS, SORTS, browse } from "../lib/browse";

export default function Recipes() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [url, setUrl] = useState("");
  const [pasting, setPasting] = useState(false);
  const [pasted, setPasted] = useState("");
  const [filter, setFilter] = useState("all");
  const [sort, setSort] = useState("newest");
  const justDeleted = useLocation().state?.deleted;
  const [undone, setUndone] = useState(false);
  const { data: recipes = [], isLoading } = useQuery({ queryKey: ["recipes", q], queryFn: () => api.recipes(q) });
  const { data: status } = useQuery({ queryKey: ["backup"], queryFn: api.backupStatus, staleTime: 60_000 });
  const backup = status && describeBackup(status);
  const { data: trash = [] } = useQuery({ queryKey: ["trash"], queryFn: api.trash });
  const restore = useMutation({
    mutationFn: api.restoreRecipe,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["recipes"] }); qc.invalidateQueries({ queryKey: ["trash"] }); },
  });
  const parse = useMutation({
    mutationFn: api.parseRecipe,
    onSuccess: (r) => { qc.invalidateQueries({ queryKey: ["recipes"] }); navigate(`/recipes/${r.id}`); },
  });
  const importer = useMutation({
    mutationFn: api.importRecipe,
    onSuccess: (r) => { qc.invalidateQueries({ queryKey: ["recipes"] }); navigate(`/recipes/${r.id}`); },
  });

  const shown = browse(recipes, filter, sort);
  return (
    <div className="page stack">
      <div className="page-head"><h1>Recipes</h1></div>
      <form className="row" onSubmit={(e) => { e.preventDefault(); url.trim() && importer.mutate(url.trim()); }}>
        <input type="url" placeholder="Paste a recipe URL to import…" value={url} onChange={(e) => setUrl(e.target.value)} style={{ flex: 1 }} />
        <button className="btn" disabled={importer.isPending || !url.trim()}><LinkIcon size={16} /> {importer.isPending ? "Importing…" : "Import"}</button>
      </form>
      {importer.isError && <div className="error">{importer.error.message}</div>}
      <button className="btn outline small" style={{ alignSelf: "flex-start" }} onClick={() => setPasting(!pasting)}><ClipboardPaste size={14} /> Paste a recipe</button>
      {pasting && (
        <div className="card stack">
          <p className="muted" style={{ margin: 0 }}>Paste a recipe from a chat, a website or a card. The chef turns it into steps with timers and keeps your amounts.</p>
          <textarea rows={8} value={pasted} onChange={(e) => setPasted(e.target.value)} placeholder="Paste the ingredients and the method here…" />
          <div className="row">
            <button className="btn" disabled={parse.isPending || pasted.trim().length < 20} onClick={() => parse.mutate(pasted)}>{parse.isPending ? "Writing it up… this takes a few seconds" : "Save as a recipe"}</button>
          </div>
          {parse.isError && <div className="error">{parse.error.message}</div>}
        </div>
      )}
      {justDeleted && !undone && (
        <div className="undo-bar">
          <span>Deleted “{justDeleted.title}”.</span>
          <button className="btn small" disabled={restore.isPending} onClick={() => restore.mutate(justDeleted.id, { onSuccess: () => setUndone(true) })}><Undo2 size={14} /> Undo</button>
        </div>
      )}
      <div className="row"><Search size={18} /><input type="text" placeholder="Search by title, tag or ingredient" value={q} onChange={(e) => setQ(e.target.value)} style={{ flex: 1 }} /></div>
      <div className="row browse-bar">
        {FILTERS.map((f) => <button key={f.id} className={`chip-btn ${filter === f.id ? "on" : ""}`} onClick={() => setFilter(f.id)}>{f.label}</button>)}
        <select aria-label="Sort" value={sort} onChange={(e) => setSort(e.target.value)} style={{ width: "auto", marginLeft: "auto" }}>
          {SORTS.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
        </select>
      </div>
      {isLoading ? <p className="muted">Loading…</p> : recipes.length === 0 ? (
        <div className="empty"><img className="art hero" src={emptySearch} alt="" /><p className="muted">{q ? "Nothing matches." : "No recipes yet. Ask the Chef for one or import a URL."}</p></div>
      ) : (
        shown.length === 0 ? <p className="muted">Nothing in “{FILTERS.find((f) => f.id === filter).label}”.</p>
        : <div className="recipe-grid">{shown.map((r) => <RecipeCard key={r.id} recipe={r} />)}</div>
      )}
      {trash.length > 0 && (
        <details className="trash">
          <summary>Recently deleted ({trash.length})</summary>
          {trash.map((t) => (
            <div key={t.id} className="row" style={{ justifyContent: "space-between", padding: ".35rem 0" }}>
              <span>{t.title}</span>
              <button className="btn outline small" disabled={restore.isPending} onClick={() => restore.mutate(t.id)}><Undo2 size={14} /> Restore</button>
            </div>
          ))}
          <p className="muted" style={{ fontSize: ".8rem" }}>Deleted recipes are removed for good after 30 days.</p>
        </details>
      )}
      {backup && <p className={`backup-line ${backup.level}`}>{backup.text}</p>}
    </div>
  );
}
