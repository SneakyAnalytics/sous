import React, { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarCheck, ChefHat, ChevronLeft, ChevronRight, Flame, Plus, ShoppingCart, Star, X } from "lucide-react";
import { api } from "../api";
import { bannerWeek } from "../assets";
import { shiftWeek, todayIso, totalMinutes, weekDays, weekLabel } from "../lib/format";
import CartReview from "../components/CartReview";

function MealRow({ it, days, defaultTime, onMove, onServings, onTime, onRemove }) {
  return (
    <div className="meal">
      <Link to={`/recipes/${it.recipe_id}`} className="meal-title">{it.recipe.title}</Link>
      <div className="meal-actions">
        <label className="muted" title="Servings">Serves <input type="number" min="1" defaultValue={it.servings}
          onBlur={(e) => +e.target.value !== it.servings && onServings(Math.max(1, +e.target.value || 1))} /></label>
        <select aria-label="Move to day" value={it.cook_date || ""} onChange={(e) => e.target.value && onMove(e.target.value)}>
          {!it.cook_date && <option value="">Pick a day…</option>}
          {days.map((d) => <option key={d.iso} value={d.iso}>{d.weekday} {d.date}</option>)}
        </select>
        {it.cook_date && <input type="time" aria-label="Dinner time" value={it.cook_time || defaultTime || ""} onChange={(e) => e.target.value && onTime(e.target.value)} />}
        <Link className="btn ember small" to={`/cook/${it.recipe_id}?servings=${it.servings}`}><Flame size={14} /> Cook</Link>
        <button className="icon-btn" aria-label="Remove" onClick={onRemove}><X size={16} /></button>
      </div>
    </div>
  );
}

export default function Plan() {
  const qc = useQueryClient();
  const { data: cw } = useQuery({ queryKey: ["current-week"], queryFn: api.currentWeek });
  const [offset, setOffset] = useState(0);
  const [reviewing, setReviewing] = useState(false);
  const [picking, setPicking] = useState(null); // ISO day the recipe picker is open for
  const [filter, setFilter] = useState("");
  const week = cw ? shiftWeek(cw.week_start, offset) : null;
  const { data: plan } = useQuery({ queryKey: ["plan", week], queryFn: () => api.plan(week), enabled: !!week });
  const { data: recipes = [] } = useQuery({ queryKey: ["recipes", ""], queryFn: () => api.recipes("") });
  const refresh = () => qc.invalidateQueries({ queryKey: ["plan", week] });

  const add = useMutation({ mutationFn: ({ id, day }) => api.addToPlan(week, id, day), onSuccess: () => { setPicking(null); setFilter(""); refresh(); } });
  const remove = useMutation({ mutationFn: api.removePlanItem, onSuccess: refresh });
  const patch = useMutation({ mutationFn: ({ id, body }) => api.patchPlanItem(id, body), onSuccess: refresh });
  const { data: cal } = useQuery({ queryKey: ["calendar"], queryFn: api.calendarStatus });
  const calSync = useMutation({ mutationFn: () => api.calendarSync(week), onSettled: () => qc.invalidateQueries({ queryKey: ["calendar"] }) });
  const target = useMutation({ mutationFn: (n) => api.setMealTarget(week, n), onSuccess: refresh });
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
  const days = weekDays(week);
  const today = todayIso();
  const unscheduled = plan.items.filter((it) => !it.cook_date);
  const q = filter.trim().toLowerCase();
  const pickable = recipes.filter((r) => !q || r.title.toLowerCase().includes(q) || r.tags.some((t) => t.toLowerCase().includes(q)));

  return (
    <div className="page stack">
      <div className="banner"><img src={bannerWeek} alt="" /></div>
      <div className="page-head">
        <h1>Week of {weekLabel(week)}</h1>
        <div className="week-nav">
          <button className="icon-btn" aria-label="Previous week" onClick={() => setOffset(offset - 1)}><ChevronLeft size={18} /></button>
          <button className="btn outline small" onClick={() => setOffset(0)} disabled={offset === 0}>This week</button>
          <button className="icon-btn" aria-label="Next week" onClick={() => setOffset(offset + 1)}><ChevronRight size={18} /></button>
        </div>
      </div>

      <section className="stack">
        <div className="row">
          <h2 style={{ margin: 0 }}>Meals</h2>
          <div className="stepper" role="group" aria-label="Meals to prep this week">
            <button aria-label="Fewer meals" disabled={!plan.meal_target || plan.meal_target <= 1} onClick={() => target.mutate(plan.meal_target - 1)}>−</button>
            <span><strong>{plan.meal_target ?? "?"}</strong> to prep</span>
            <button aria-label="More meals" disabled={plan.meal_target >= 14} onClick={() => target.mutate((plan.meal_target ?? plan.items.length) + 1)}>+</button>
          </div>
          <span className="muted">
            {plan.meal_target == null ? "Set how many meals you're prepping this week."
              : plan.items.length >= plan.meal_target ? `All ${plan.meal_target} planned` : `${plan.items.length} of ${plan.meal_target} planned`}
          </span>
        </div>

        {cal?.configured && (
          <div className="row muted">
            <CalendarCheck size={16} />
            <span>Meals sync to your Google "Meals" calendar (default {cal.dinner_time}).
              {calSync.isError ? <span className="error"> {calSync.error.message}</span>
                : calSync.data?.counts ? ` Synced: ${calSync.data.counts.created} added, ${calSync.data.counts.updated} changed, ${calSync.data.counts.deleted} removed.`
                : cal.last_sync && !cal.last_sync.ok ? <span className="error"> Last sync failed: {cal.last_sync.error}</span> : ""}</span>
            <button className="btn outline small" disabled={calSync.isPending} onClick={() => calSync.mutate()}>{calSync.isPending ? "Syncing…" : "Sync now"}</button>
          </div>
        )}
        <div className="week-grid">
          {days.map((d) => {
            const meals = plan.items.filter((it) => it.cook_date === d.iso);
            return (
              <div key={d.iso} className={`day ${d.iso === today ? "today" : ""} ${d.iso < today ? "past" : ""}`}>
                <div className="day-head"><strong>{d.weekday}</strong><span className="muted">{d.date}</span></div>
                {meals.map((it) => <MealRow key={it.id} it={it} days={days} onMove={(iso) => patch.mutate({ id: it.id, body: { cook_date: iso } })}
                  onServings={(n) => patch.mutate({ id: it.id, body: { servings: n } })} onTime={(t) => patch.mutate({ id: it.id, body: { cook_time: t } })} defaultTime={cal?.dinner_time} onRemove={() => remove.mutate(it.id)} />)}
                <button className="add-meal" onClick={() => setPicking(picking === d.iso ? null : d.iso)}><Plus size={14} /> {meals.length ? "Add another" : "Add a meal"}</button>
              </div>
            );
          })}
        </div>

        {unscheduled.length > 0 && (
          <div className="card stack">
            <strong>Planned, no day yet</strong>
            {unscheduled.map((it) => <MealRow key={it.id} it={it} days={days} onMove={(iso) => patch.mutate({ id: it.id, body: { cook_date: iso } })}
              onServings={(n) => patch.mutate({ id: it.id, body: { servings: n } })} onTime={(t) => patch.mutate({ id: it.id, body: { cook_time: t } })} defaultTime={cal?.dinner_time} onRemove={() => remove.mutate(it.id)} />)}
          </div>
        )}

        {picking && (
          <div className="card stack picker">
            <div className="row">
              <strong style={{ flex: 1 }}>Pick a saved recipe for {days.find((d) => d.iso === picking)?.weekday}</strong>
              <Link className="btn outline small" to={`/?ask=${encodeURIComponent(`Suggest 3 dinners for ${days.find((d) => d.iso === picking)?.weekday}. `)}`}><ChefHat size={14} /> Ask the chef instead</Link>
              <button className="icon-btn" aria-label="Close" onClick={() => setPicking(null)}><X size={16} /></button>
            </div>
            <input type="search" placeholder="Search your recipes…" value={filter} onChange={(e) => setFilter(e.target.value)} autoFocus />
            {pickable.length === 0 && <p className="muted">{recipes.length ? "No matches." : "No saved recipes yet. Ask the chef for ideas."}</p>}
            <div className="pick-list">
              {pickable.map((r) => (
                <button key={r.id} className="pick" onClick={() => add.mutate({ id: r.id, day: picking })}>
                  <span>{r.favorite && <Star size={13} fill="currentColor" />} {r.title}</span>
                  <span className="muted">{[totalMinutes(r) && `${totalMinutes(r)} min`, r.rating && `${r.rating}★`].filter(Boolean).join(" · ")}</span>
                </button>
              ))}
            </div>
          </div>
        )}
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
