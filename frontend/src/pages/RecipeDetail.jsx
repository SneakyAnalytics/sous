import React, { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarPlus, Clock, Flame, Lightbulb, Star, Trash2, Users } from "lucide-react";
import { api } from "../api";
import { scaleIngredient, totalMinutes } from "../lib/format";

export default function RecipeDetail() {
  const { id } = useParams();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { data: r, isLoading, isError } = useQuery({ queryKey: ["recipe", id], queryFn: () => api.recipe(id) });
  const [servings, setServings] = useState(null);
  const [added, setAdded] = useState(false);

  const patch = useMutation({ mutationFn: (b) => api.patchRecipe(id, b), onSuccess: (d) => { qc.setQueryData(["recipe", id], d); qc.invalidateQueries({ queryKey: ["recipes"] }); } });
  const del = useMutation({ mutationFn: () => api.deleteRecipe(id), onSuccess: () => { qc.invalidateQueries({ queryKey: ["recipes"] }); navigate("/recipes"); } });
  const plan = useMutation({
    mutationFn: async () => { const { week_start } = await api.currentWeek(); return api.addToPlan(week_start, r.id, servings || r.servings); },
    onSuccess: () => { setAdded(true); qc.invalidateQueries({ queryKey: ["plan"] }); },
  });

  if (isLoading) return <div className="page muted">Loading…</div>;
  if (isError || !r) return <div className="page error">Recipe not found.</div>;
  const n = servings || r.servings;
  const factor = n / r.servings;
  const mins = totalMinutes(r);

  return (
    <div className="page stack">
      <div className="page-head">
        <h1>{r.title}</h1>
        <div className="row">
          <button className="icon-btn" aria-label="Favorite" onClick={() => patch.mutate({ favorite: !r.favorite })}>
            <Star size={18} fill={r.favorite ? "currentColor" : "none"} style={{ color: "var(--color-gravel)" }} />
          </button>
          <button className="icon-btn" aria-label="Delete recipe" onClick={() => confirm(`Delete "${r.title}"?`) && del.mutate()}><Trash2 size={18} /></button>
        </div>
      </div>
      {r.description && <p>{r.description}</p>}
      <div className="row muted">
        {mins && <span><Clock size={14} /> {mins} min</span>}
        <span><Users size={14} /> <input type="number" min="1" value={n} onChange={(e) => setServings(Math.max(1, +e.target.value || 1))} style={{ width: "4rem", padding: ".2rem .4rem" }} /> servings</span>
        {r.source_url && <a href={r.source_url} target="_blank" rel="noreferrer">Source</a>}
        {r.tags.map((t) => <span key={t} className="chip">{t}</span>)}
      </div>
      <div className="row">
        <Link className="btn ember" to={`/cook/${r.id}?servings=${n}`}><Flame size={18} /> Start cooking</Link>
        <button className="btn outline" disabled={plan.isPending || added} onClick={() => plan.mutate()}>
          <CalendarPlus size={18} /> {added ? "Added to this week" : "Add to this week"}
        </button>
      </div>

      {r.chef_tips.length > 0 && (
        <div className="tip-box">
          <strong><Lightbulb size={16} style={{ verticalAlign: "-3px" }} /> Chef's tips</strong>
          <ul className="tip-list">{r.chef_tips.map((t, i) => <li key={i}>{t}</li>)}</ul>
        </div>
      )}
      <div className="cols">
        <div>
          <h2>Ingredients</h2>
          <ul className="ingredient-list">
            {r.ingredients.map((i, k) => <li key={k}>{scaleIngredient(i, factor)}{i.note && <span className="muted">, {i.note}</span>}</li>)}
          </ul>
        </div>
        <div>
          <h2>Method</h2>
          <ol className="step-list">
            {r.steps.map((s, k) => (
              <li key={k}>{s.text}
                {s.timer_seconds > 0 && <span className="chip" style={{ marginLeft: ".4rem" }}>{Math.round(s.timer_seconds / 60)} min</span>}
                {s.tip && <div className="muted">Tip: {s.tip}</div>}
              </li>
            ))}
          </ol>
        </div>
      </div>
      <div>
        <h2>Our notes</h2>
        <textarea rows={3} defaultValue={r.notes} placeholder="What would we change next time?" onBlur={(e) => e.target.value !== r.notes && patch.mutate({ notes: e.target.value })} />
      </div>
    </div>
  );
}
