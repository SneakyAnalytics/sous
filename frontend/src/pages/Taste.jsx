import React, { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";

export default function Taste() {
  const qc = useQueryClient();
  const { data: t } = useQuery({ queryKey: ["taste"], queryFn: api.taste });
  const { data: pantry = [] } = useQuery({ queryKey: ["pantry"], queryFn: api.pantry });
  const unstaple = useMutation({ mutationFn: (name) => api.setStaple(name, false), onSuccess: (d) => { qc.setQueryData(["pantry"], d); qc.invalidateQueries({ queryKey: ["plan"] }); } });
  const [text, setText] = useState(null);
  const save = useMutation({ mutationFn: api.saveTaste, onSuccess: (d) => { qc.setQueryData(["taste"], d); setText(null); } });
  if (!t) return <div className="page muted">Loading…</div>;
  const value = text ?? t.preferences;
  return (
    <div className="page stack">
      <h1>Our taste</h1>
      <p className="muted">This is what the chef knows about you two. It comes from your ratings, favorites, notes after cooking, and what you write here. The chef also adds to it when you tell it a lasting preference.</p>
      <section className="stack">
        <h2>Preferences</h2>
        <textarea rows={6} value={value} placeholder={"No cilantro\nKadie likes spicy food\nWe want more fish"} onChange={(e) => setText(e.target.value)} />
        <div className="row"><button className="btn" disabled={text === null || save.isPending} onClick={() => save.mutate(text)}>Save</button></div>
      </section>
      {Object.entries(t.by_person || {}).map(([who, p]) => (
        <section key={who} className="stack">
          <h2>{who}</h2>
          {p.loved.length > 0 && <p><strong>Loves:</strong> {p.loved.join(" · ")}</p>}
          {p.disliked.length > 0 && <p><strong>Didn't enjoy:</strong> {p.disliked.join(" · ")}</p>}
        </section>
      ))}
      <section className="stack">
        <h2>Pantry staples</h2>
        <p className="muted" style={{ margin: 0 }}>Ingredients you always have. They start as "Have" on every grocery list. Pin an ingredient on the Plan page to add it here.</p>
        {pantry.length ? <div className="row">{pantry.map((n) => (
          <span key={n} className="chip">{n} <button className="icon-btn" style={{ padding: 0 }} aria-label={`Remove ${n}`} onClick={() => unstaple.mutate(n)}>×</button></span>
        ))}</div> : <p className="muted">None yet.</p>}
      </section>
      <section className="stack">
        <h2>Loved</h2>
        {t.loved.length ? <p>{t.loved.join(" · ")}</p> : <p className="muted">Rate a recipe 4 or 5 stars, or favorite it.</p>}
        {t.liked_tags.length > 0 && <div className="row">{t.liked_tags.map((g) => <span key={g} className="chip">{g}</span>)}</div>}
      </section>
      {t.disliked.length > 0 && <section><h2>Didn't enjoy</h2><p>{t.disliked.join(" · ")}</p></section>}
      {t.cook_notes.length > 0 && (
        <section className="stack">
          <h2>Notes after cooking</h2>
          {t.cook_notes.map((n, i) => <div key={i} className="card"><strong>{n.recipe}</strong> <span className="muted">{n.cooked_on}{n.rating ? ` · ${n.rating}★` : ""}</span><div>{n.notes}</div></div>)}
        </section>
      )}
      <p><Link to="/">Ask the chef for ideas</Link></p>
    </div>
  );
}
