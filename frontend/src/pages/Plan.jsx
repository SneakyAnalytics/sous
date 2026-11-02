import React, { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Flame, ShoppingCart, X } from "lucide-react";
import { api } from "../api";
import { shiftWeek, weekLabel } from "../lib/format";
import CartReview from "../components/CartReview";

export default function Plan() {
  const qc = useQueryClient();
  const { data: cw } = useQuery({ queryKey: ["current-week"], queryFn: api.currentWeek });
  const [offset, setOffset] = useState(0);
  const [reviewing, setReviewing] = useState(false);
  const week = cw ? shiftWeek(cw.week_start, offset) : null;
  const { data: plan } = useQuery({ queryKey: ["plan", week], queryFn: () => api.plan(week), enabled: !!week });
  const { data: recipes = [] } = useQuery({ queryKey: ["recipes", ""], queryFn: () => api.recipes("") });
  const refresh = () => qc.invalidateQueries({ queryKey: ["plan", week] });

  const add = useMutation({ mutationFn: (id) => api.addToPlan(week, id), onSuccess: refresh });
  const remove = useMutation({ mutationFn: api.removePlanItem, onSuccess: refresh });
  const servings = useMutation({ mutationFn: ({ id, n }) => api.patchPlanItem(id, { servings: n }), onSuccess: refresh });
  const setStatus = useMutation({
    mutationFn: ({ key, status }) => api.setStatus(week, key, status),
    onMutate: async ({ key, status }) => { // optimistic: the toggle should feel instant
      await qc.cancelQueries({ queryKey: ["plan", week] });
      const prev = qc.getQueryData(["plan", week]);
      qc.setQueryData(["plan", week], { ...prev, list: prev.list.map((i) => (i.key === key ? { ...i, status } : i)) });
      return { prev };
    },
    onError: (_e, _v, ctx) => qc.setQueryData(["plan", week], ctx.prev),
    onSettled: refresh,
  });

  if (!plan) return <div className="page muted">Loading…</div>;
  const unanswered = plan.list.filter((i) => !i.status).length;
  const needed = plan.list.filter((i) => i.status === "need");
  const groups = plan.list.reduce((acc, i) => ((acc[i.category] ||= []).push(i), acc), {});
  const planned = new Set(plan.items.map((i) => i.recipe_id));

  return (
    <div className="page stack">
      <div className="page-head">
        <h1>Week of {weekLabel(week)}</h1>
        <div className="week-nav">
          <button className="icon-btn" aria-label="Previous week" onClick={() => setOffset(offset - 1)}><ChevronLeft size={18} /></button>
          <button className="btn outline small" onClick={() => setOffset(0)} disabled={offset === 0}>This week</button>
          <button className="icon-btn" aria-label="Next week" onClick={() => setOffset(offset + 1)}><ChevronRight size={18} /></button>
        </div>
      </div>

      <section className="stack">
        <h2>Meals</h2>
        {plan.items.length === 0 && <p className="muted">Nothing planned. Pick recipes below, or ask the Chef to add one.</p>}
        {plan.items.map((it) => (
          <div key={it.id} className="card row">
            <Link to={`/recipes/${it.recipe_id}`} style={{ flex: 1, fontWeight: 600, textDecoration: "none" }}>{it.recipe.title}</Link>
            <label className="muted">Servings <input type="number" min="1" defaultValue={it.servings} onBlur={(e) => +e.target.value !== it.servings && servings.mutate({ id: it.id, n: Math.max(1, +e.target.value || 1) })} /></label>
            <Link className="btn ember small" to={`/cook/${it.recipe_id}?servings=${it.servings}`}><Flame size={14} /> Cook</Link>
            <button className="icon-btn" aria-label="Remove" onClick={() => remove.mutate(it.id)}><X size={16} /></button>
          </div>
        ))}
        <div className="row">
          <select defaultValue="" onChange={(e) => { if (e.target.value) { add.mutate(+e.target.value); e.target.value = ""; } }} style={{ maxWidth: 320 }}>
            <option value="">+ Add a recipe…</option>
            {recipes.filter((r) => !planned.has(r.id)).map((r) => <option key={r.id} value={r.id}>{r.title}</option>)}
          </select>
        </div>
      </section>

      {plan.list.length > 0 && (
        <section>
          <h2>Grocery list</h2>
          <p className="muted">For each ingredient, mark whether you already have enough. Anything marked <strong>Need</strong> goes to your Safeway cart.</p>
          <div className="row" style={{ marginBottom: ".5rem" }}>
            <button className="btn outline small" onClick={() => plan.list.filter((i) => !i.status).forEach((i) => setStatus.mutate({ key: i.key, status: "need" }))} disabled={!unanswered}>Mark the rest as Need</button>
            <span className="muted">{unanswered ? `${unanswered} still to answer` : `${needed.length} to buy`}</span>
          </div>
          {Object.entries(groups).map(([cat, items]) => (
            <div key={cat} className="list-group">
              <h3>{cat}</h3>
              {items.map((i) => (
                <div key={i.key} className="list-row">
                  <div className="what">{i.display && <strong>{i.display} </strong>}{i.name}<small>{i.recipes.join(", ")}</small></div>
                  <div className="seg">
                    <button className={i.status === "have" ? "on-have" : ""} onClick={() => setStatus.mutate({ key: i.key, status: i.status === "have" ? null : "have" })}>Have</button>
                    <button className={i.status === "need" ? "on-need" : ""} onClick={() => setStatus.mutate({ key: i.key, status: i.status === "need" ? null : "need" })}>Need</button>
                  </div>
                </div>
              ))}
            </div>
          ))}
          <div className="row" style={{ marginTop: "1rem" }}>
            <button className="btn" disabled={unanswered > 0 || needed.length === 0} onClick={() => setReviewing(true)}>
              <ShoppingCart size={18} /> Review {needed.length} item{needed.length === 1 ? "" : "s"} for Safeway
            </button>
            {unanswered > 0 && <span className="muted">Answer every ingredient first.</span>}
          </div>
        </section>
      )}
      {reviewing && <CartReview items={needed} onClose={() => setReviewing(false)} />}
    </div>
  );
}
