import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Check, ChefHat, ExternalLink, X } from "lucide-react";
import { chefBasket } from "../assets";
import { searchQuery, searchUrl } from "../lib/safeway";

const keyFor = (week) => `sous-shop-${week}`;

/**
 * Shop the "Need" items in your own logged-in Safeway session: one search link per item, tick each off as you add it to
 * your cart. Nothing here touches your Safeway account, and your progress is remembered per week.
 */
export default function ShoppingChecklist({ items, week, onClose }) {
  const [done, setDone] = useState(() => {
    try { return JSON.parse(localStorage.getItem(keyFor(week)) || "{}"); } catch { return {}; }
  });
  useEffect(() => { try { localStorage.setItem(keyFor(week), JSON.stringify(done)); } catch { /* storage blocked */ } }, [done, week]);
  const count = items.filter((i) => done[i.key]).length;
  const toggle = (key) => setDone((d) => ({ ...d, [key]: !d[key] }));

  return (
    <div className="card stack" style={{ border: "2px solid var(--color-forest)" }}>
      <div className="page-head" style={{ margin: 0 }}>
        <h2 style={{ margin: 0 }} className="row"><img className="art" style={{ width: 48 }} src={chefBasket} alt="" /> Safeway shopping</h2>
        <button className="icon-btn" onClick={onClose} aria-label="Close"><X size={16} /></button>
      </div>
      <p className="muted" style={{ margin: 0 }}>
        Tap <strong>Search</strong> to open the item on Safeway (you stay signed in to your own account), add it to your cart, then tick it off here.
        You check out in Safeway. <strong>{count} of {items.length}</strong> done.
      </p>
      <div className="progress"><div style={{ width: `${items.length ? (count / items.length) * 100 : 0}%` }} /></div>
      {items.map((i) => (
        <div key={i.key} className={`shop-row ${done[i.key] ? "done" : ""}`}>
          <button className={`tick ${done[i.key] ? "on" : ""}`} aria-label={`${done[i.key] ? "Unmark" : "Mark"} ${i.name} as added`} aria-pressed={!!done[i.key]} onClick={() => toggle(i.key)}>
            {done[i.key] && <Check size={16} />}
          </button>
          <div className="what"><strong>{i.display} </strong>{i.name}<small>{i.recipes.join(", ")}</small></div>
          <a className="btn outline small" href={searchUrl(i.name)} target="_blank" rel="noreferrer" aria-label={`Search Safeway for ${searchQuery(i.name)}`}>Search <ExternalLink size={13} /></a>
        </div>
      ))}
      <div className="row">
        <Link className="btn outline small" to={`/?ask=${encodeURIComponent("I'm shopping at Safeway. For each of these, what size or type should I look for, and what can I swap if they're out? ")}`}><ChefHat size={14} /> Ask the chef what to buy</Link>
        {count > 0 && <button className="btn outline small" onClick={() => confirm("Clear your ticks for this week?") && setDone({})}>Clear ticks</button>}
      </div>
    </div>
  );
}
