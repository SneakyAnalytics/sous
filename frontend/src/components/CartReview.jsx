import React, { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Check, ShoppingCart, X } from "lucide-react";
import { api } from "../api";

/** Match each needed ingredient to a Safeway product, let the user adjust, then add to cart. Never checks out. */
export default function CartReview({ items, onClose }) {
  const [rows, setRows] = useState({}); // key -> {include, productId, qty}
  const match = useMutation({ mutationFn: () => api.cartMatch(items.map((i) => i.name)) });
  const add = useMutation({ mutationFn: (lines) => api.cartAdd(lines) });

  useEffect(() => {
    match.mutate(undefined, {
      onSuccess: (res) => setRows(Object.fromEntries(items.map((i) => {
        const first = res[i.name]?.candidates?.[0];
        return [i.key, { include: !!first, productId: first?.id || "", qty: 1 }];
      }))),
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const set = (key, patch) => setRows((r) => ({ ...r, [key]: { ...r[key], ...patch } }));
  const chosen = items.filter((i) => rows[i.key]?.include && rows[i.key].productId);
  const results = add.data && Object.fromEntries(add.data.results.map((r) => [r.key, r]));
  const failed = add.data?.results.filter((r) => !r.ok) || [];

  return (
    <div className="card stack" style={{ border: "2px solid var(--color-forest)" }}>
      <div className="page-head" style={{ margin: 0 }}>
        <h2 style={{ margin: 0 }}><ShoppingCart size={20} style={{ verticalAlign: "-3px" }} /> Safeway cart</h2>
        <button className="icon-btn" onClick={onClose} aria-label="Close"><X size={16} /></button>
      </div>
      <p className="muted">Check each match. Items are added to your cart only. You check out in the Safeway app.</p>
      {match.isPending && <p className="muted">Searching Safeway… this can take a minute.</p>}
      {match.isError && <p className="error">{match.error.message}</p>}
      {match.data && items.map((i) => {
        const res = match.data[i.name];
        const row = rows[i.key] || {};
        const r = results?.[i.key];
        return (
          <div key={i.key} className="cart-row">
            <input type="checkbox" checked={!!row.include} disabled={!res.candidates.length || !!add.data} onChange={(e) => set(i.key, { include: e.target.checked })} />
            <div><strong>{i.display} {i.name}</strong>{res.error && <div className="error">{res.error}</div>}{!res.error && !res.candidates.length && <div className="muted">No match found</div>}</div>
            {res.candidates.length > 0 ? (
              <select value={row.productId} disabled={!!add.data} onChange={(e) => set(i.key, { productId: e.target.value })}>
                {res.candidates.map((c) => <option key={c.id} value={c.id}>{c.name}{c.price != null ? ` ($${Number(c.price).toFixed(2)})` : ""}{c.in_stock === false ? " (out of stock)" : ""}</option>)}
              </select>
            ) : <span />}
            {r ? (r.ok ? <Check size={18} color="var(--color-forest)" /> : <span className="error" title={r.error}>Failed</span>)
              : <input type="number" min="1" value={row.qty ?? 1} disabled={!res.candidates.length} onChange={(e) => set(i.key, { qty: Math.max(1, +e.target.value || 1) })} />}
          </div>
        );
      })}
      {match.data && !add.data && (
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
