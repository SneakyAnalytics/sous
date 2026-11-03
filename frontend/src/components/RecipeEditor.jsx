import React, { useState } from "react";
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { fmtQty } from "../lib/format";
import { parseQty } from "../lib/qty";

const move = (list, i, d) => {
  const j = i + d;
  if (j < 0 || j >= list.length) return list;
  const next = [...list];
  [next[i], next[j]] = [next[j], next[i]];
  return next;
};

/** Edit a recipe by hand. Saving keeps the previous version, so "Undo last revision" works on these edits too. */
export default function RecipeEditor({ recipe, onSave, onCancel, saving, error }) {
  const [f, setF] = useState({
    title: recipe.title, description: recipe.description || "", servings: recipe.servings,
    prep_min: recipe.prep_min ?? "", cook_min: recipe.cook_min ?? "", tags: recipe.tags.join(", "),
    chef_tips: recipe.chef_tips.join("\n"),
  });
  const [ings, setIngs] = useState(recipe.ingredients.map((i) => ({ qty: i.quantity == null ? "" : fmtQty(i.quantity), unit: i.unit || "", name: i.name, note: i.note || "" })));
  const [steps, setSteps] = useState(recipe.steps.map((s) => ({ text: s.text, minutes: s.timer_seconds ? String(Math.round((s.timer_seconds / 60) * 100) / 100) : "", tip: s.tip || "" })));
  const [problem, setProblem] = useState("");
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const upd = (list, setList, i, patch) => setList(list.map((x, k) => (k === i ? { ...x, ...patch } : x)));

  const save = () => {
    if (!f.title.trim()) return setProblem("A recipe needs a title.");
    const ingredients = [];
    for (const [n, i] of ings.entries()) {
      if (!i.name.trim()) continue;
      const quantity = parseQty(i.qty);
      if (quantity === undefined) return setProblem(`Ingredient ${n + 1}: "${i.qty}" isn't an amount. Use something like 2, 1/2 or 1 1/2.`);
      ingredients.push({ quantity, unit: i.unit.trim(), name: i.name.trim(), note: i.note.trim() });
    }
    const out = [];
    for (const [n, s] of steps.entries()) {
      if (!s.text.trim()) continue;
      const mins = s.minutes === "" ? 0 : parseFloat(s.minutes);
      if (Number.isNaN(mins) || mins < 0) return setProblem(`Step ${n + 1}: the timer should be a number of minutes.`);
      out.push({ text: s.text.trim(), ...(mins > 0 && { timer_seconds: Math.round(mins * 60) }), ...(s.tip.trim() && { tip: s.tip.trim() }) });
    }
    if (!out.length) return setProblem("Add at least one step.");
    setProblem("");
    onSave({
      title: f.title.trim(), description: f.description.trim(), servings: Math.max(1, +f.servings || 1),
      prep_min: f.prep_min === "" ? null : +f.prep_min, cook_min: f.cook_min === "" ? null : +f.cook_min,
      tags: f.tags.split(",").map((t) => t.trim()).filter(Boolean), chef_tips: f.chef_tips.split("\n").map((t) => t.trim()).filter(Boolean),
      ingredients, steps: out,
    });
  };

  return (
    <div className="stack editor">
      <label>Title<input value={f.title} onChange={set("title")} /></label>
      <label>Description<textarea rows={2} value={f.description} onChange={set("description")} /></label>
      <div className="row">
        <label>Servings<input type="number" min="1" value={f.servings} onChange={set("servings")} style={{ width: "5rem" }} /></label>
        <label>Prep (min)<input type="number" min="0" value={f.prep_min} onChange={set("prep_min")} style={{ width: "5rem" }} /></label>
        <label>Cook (min)<input type="number" min="0" value={f.cook_min} onChange={set("cook_min")} style={{ width: "5rem" }} /></label>
      </div>
      <label>Tags (comma separated)<input value={f.tags} onChange={set("tags")} placeholder="soup, dutch oven, weeknight" /></label>

      <h2>Ingredients</h2>
      {ings.map((i, k) => (
        <div key={k} className="ed-row ing">
          <input aria-label="Amount" placeholder="1 1/2" value={i.qty} onChange={(e) => upd(ings, setIngs, k, { qty: e.target.value })} />
          <input aria-label="Unit" placeholder="cup" value={i.unit} onChange={(e) => upd(ings, setIngs, k, { unit: e.target.value })} />
          <input aria-label="Ingredient" placeholder="all-purpose flour" value={i.name} onChange={(e) => upd(ings, setIngs, k, { name: e.target.value })} />
          <input aria-label="Note" placeholder="sifted" value={i.note} onChange={(e) => upd(ings, setIngs, k, { note: e.target.value })} />
          <button className="icon-btn" aria-label="Remove ingredient" onClick={() => setIngs(ings.filter((_, x) => x !== k))}><Trash2 size={16} /></button>
        </div>
      ))}
      <button className="btn outline small" style={{ alignSelf: "flex-start" }} onClick={() => setIngs([...ings, { qty: "", unit: "", name: "", note: "" }])}><Plus size={14} /> Add ingredient</button>

      <h2>Steps</h2>
      {steps.map((s, k) => (
        <div key={k} className="ed-step">
          <div className="row" style={{ alignItems: "flex-start", flexWrap: "nowrap" }}>
            <strong>{k + 1}.</strong>
            <textarea aria-label={`Step ${k + 1}`} rows={2} value={s.text} onChange={(e) => upd(steps, setSteps, k, { text: e.target.value })} style={{ flex: 1 }} />
            <div className="col-btns">
              <button className="icon-btn" aria-label="Move step up" disabled={k === 0} onClick={() => setSteps(move(steps, k, -1))}><ArrowUp size={16} /></button>
              <button className="icon-btn" aria-label="Move step down" disabled={k === steps.length - 1} onClick={() => setSteps(move(steps, k, 1))}><ArrowDown size={16} /></button>
              <button className="icon-btn" aria-label="Remove step" onClick={() => setSteps(steps.filter((_, x) => x !== k))}><Trash2 size={16} /></button>
            </div>
          </div>
          <div className="row" style={{ marginLeft: "1.6rem" }}>
            <label className="muted">Timer (min)<input value={s.minutes} onChange={(e) => upd(steps, setSteps, k, { minutes: e.target.value })} inputMode="decimal" style={{ width: "4.5rem" }} /></label>
            <input aria-label="Tip" placeholder="Tip for this step (optional)" value={s.tip} onChange={(e) => upd(steps, setSteps, k, { tip: e.target.value })} style={{ flex: 1, minWidth: "10rem" }} />
          </div>
        </div>
      ))}
      <button className="btn outline small" style={{ alignSelf: "flex-start" }} onClick={() => setSteps([...steps, { text: "", minutes: "", tip: "" }])}><Plus size={14} /> Add step</button>

      <label>Chef's tips (one per line)<textarea rows={4} value={f.chef_tips} onChange={set("chef_tips")} /></label>
      {(problem || error) && <div className="error">{problem || error}</div>}
      <div className="row">
        <button className="btn" disabled={saving} onClick={save}>{saving ? "Saving…" : "Save changes"}</button>
        <button className="btn outline" disabled={saving} onClick={onCancel}>Cancel</button>
        <span className="muted">The previous version is kept, so you can undo.</span>
      </div>
    </div>
  );
}
