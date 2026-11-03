import React, { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { useMutation } from "@tanstack/react-query";
import { Check, Send, Sparkles, X } from "lucide-react";
import { api } from "../api";
import { chefBasket, chefError } from "../assets";

/**
 * Match each needed ingredient to a Safeway product. The chef can pick (and re-search) with you in the chat,
 * you review every row, then press the button to add to the cart. Never checks out.
 */
export default function CartReview({ items, onClose }) {
  const [rows, setRows] = useState({}); // key -> { include, productId, qty }
  const [cands, setCands] = useState(null); // key -> candidate products (or null while searching)
  const [errors, setErrors] = useState({}); // key -> lookup error
  const [msgs, setMsgs] = useState([]);
  const [text, setText] = useState("");
  const endRef = useRef(null);
  const match = useMutation({ mutationFn: () => api.cartMatch(items.map((i) => i.name)) });
  const add = useMutation({ mutationFn: (lines) => api.cartAdd(lines) });
  const chat = useMutation({
    mutationFn: (t) => api.cartChat({
      items: items.map((i) => ({ key: i.key, name: i.name, display: i.display, recipes: i.recipes })),
      candidates: cands,
      selections: Object.fromEntries(Object.entries(rows).map(([k, r]) => [k, { include: r.include, product_id: r.productId, quantity: r.qty }])),
      history: msgs.map((m) => ({ role: m.role, text: m.text })),
      text: t,
    }),
    onSuccess: (res) => {
      setCands(res.candidates);
      setRows((prev) => {
        const next = { ...prev };
        for (const [k, s] of Object.entries(res.selections)) next[k] = { include: s.include, productId: s.product_id, qty: s.quantity };
        return next;
      });
      setMsgs((m) => [...m, { role: "assistant", text: res.reply }]);
    },
    onError: (e) => setMsgs((m) => [...m, { role: "assistant", text: `Sorry, that failed: ${e.message}`, error: true }]),
  });

  useEffect(() => {
    match.mutate(undefined, {
      onSuccess: (res) => {
        setCands(Object.fromEntries(items.map((i) => [i.key, res[i.name]?.candidates || []])));
        setErrors(Object.fromEntries(items.filter((i) => res[i.name]?.error).map((i) => [i.key, res[i.name].error])));
        setRows(Object.fromEntries(items.map((i) => {
          const first = res[i.name]?.candidates?.[0];
          return [i.key, { include: !!first, productId: first?.id || "", qty: 1 }];
        })));
      },
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }, [msgs.length, chat.isPending]);

  const send = (t) => {
    const v = t.trim();
    if (!v || chat.isPending || !cands) return;
    setMsgs((m) => [...m, { role: "user", text: v }]);
    setText("");
    chat.mutate(v);
  };
  const set = (key, patch) => setRows((r) => ({ ...r, [key]: { ...r[key], ...patch } }));
  const chosen = items.filter((i) => rows[i.key]?.include && rows[i.key].productId);
  const results = add.data && Object.fromEntries(add.data.results.map((r) => [r.key, r]));
  const failed = add.data?.results.filter((r) => !r.ok) || [];
  const locked = !!add.data;

  return (
    <div className="card stack" style={{ border: "2px solid var(--color-forest)" }}>
      <div className="page-head" style={{ margin: 0 }}>
        <h2 style={{ margin: 0 }} className="row"><img className="art" style={{ width: 48 }} src={chefBasket} alt="" /> Safeway cart</h2>
        <button className="icon-btn" onClick={onClose} aria-label="Close"><X size={16} /></button>
      </div>
      <p className="muted">Check each match, or ask the chef to pick or change them. Items are added to your cart only. You check out in the Safeway app.</p>
      {match.isPending && <p className="muted">Searching Safeway… this can take a minute.</p>}
      {match.isError && <div className="thinking"><img className="art" src={chefError} alt="" /><span className="error">{match.error.message}</span></div>}
      {cands && items.map((i) => {
        const list = cands[i.key] || [];
        const row = rows[i.key] || {};
        const r = results?.[i.key];
        return (
          <div key={i.key} className="cart-row">
            <input type="checkbox" checked={!!row.include} disabled={!list.length || locked} onChange={(e) => set(i.key, { include: e.target.checked })} />
            <div><strong>{i.display} {i.name}</strong>{errors[i.key] && <div className="error">{errors[i.key]}</div>}{!errors[i.key] && !list.length && <div className="muted">No match found</div>}</div>
            {list.length > 0 ? (
              <select value={row.productId} disabled={locked} onChange={(e) => set(i.key, { productId: e.target.value, include: true })}>
                {list.map((c) => <option key={c.id} value={c.id}>{c.name}{c.price != null ? ` ($${Number(c.price).toFixed(2)})` : ""}{c.in_stock === false ? " (out of stock)" : ""}</option>)}
              </select>
            ) : <span />}
            {r ? (r.ok ? <Check size={18} color="var(--color-forest)" /> : <span className="error" title={r.error}>Failed</span>)
              : <input type="number" min="1" value={row.qty ?? 1} disabled={!list.length || locked} onChange={(e) => set(i.key, { qty: Math.max(1, +e.target.value || 1) })} />}
          </div>
        );
      })}

      {cands && !locked && (
        <div className="shop-chat stack">
          {msgs.map((m, k) => <div key={k} className={`bubble ${m.role} ${m.error ? "error" : ""}`}><ReactMarkdown>{m.text}</ReactMarkdown></div>)}
          {chat.isPending && <div className="bubble assistant muted">Chef is looking through Safeway…</div>}
          <div ref={endRef} />
          <div className="row">
            <button className="btn outline small" disabled={chat.isPending} onClick={() => send("Pick the best product for every item, and ask me about anything ambiguous.")}><Sparkles size={14} /> Pick for me</button>
          </div>
          <form className="chat-input" style={{ padding: 0, border: 0, background: "none" }} onSubmit={(e) => { e.preventDefault(); send(text); }}>
            <input value={text} placeholder="e.g. get organic onions, or skip the broth" onChange={(e) => setText(e.target.value)} />
            <button className="btn" disabled={chat.isPending || !text.trim()} aria-label="Send"><Send size={18} /></button>
          </form>
        </div>
      )}

      {cands && !locked && (
        <div className="row">
          <button className="btn" disabled={!chosen.length || add.isPending}
            onClick={() => add.mutate(chosen.map((i) => ({ key: i.key, product_id: rows[i.key].productId, quantity: rows[i.key].qty })))}>
            {add.isPending ? "Adding…" : `Add ${chosen.length} to Safeway cart`}
          </button>
        </div>
      )}
      {add.isError && <p className="error">{add.error.message}</p>}
      {add.data && <p>{failed.length ? <span className="error">{failed.length} item(s) failed. Add those in the Safeway app.</span> : <strong>All added. Open the Safeway app to check out.</strong>}</p>}
    </div>
  );
}
