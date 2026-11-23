import React, { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { BookOpen, CalendarX, Heart, Pencil, Send, Trash2, Undo2 } from "lucide-react";
import { api } from "../api";
import { chefThinking } from "../assets";

/** What the chef did on a turn, as a card you can act on. `undone` tracks cards whose action was reversed. */
function ActionCard({ event, undone, onUndo, busy }) {
  const t = event.type;
  if (t === "recipe_revised") {
    return (
      <div className="action-card">
        <Pencil size={16} /><span><strong>Updated the recipe.</strong> {undone ? "Put back the way it was." : event.reason}</span>
        {!undone && <button className="btn outline small" disabled={busy} onClick={onUndo}><Undo2 size={13} /> Undo</button>}
      </div>
    );
  }
  if (t === "recipe_retired") {
    return (
      <div className="action-card">
        <Trash2 size={16} /><span><strong>Took “{event.title}” out of your recipe book.</strong> {undone ? "It's back." : "Restorable for 30 days."}</span>
        {!undone && <button className="btn outline small" disabled={busy} onClick={onUndo}><Undo2 size={13} /> Restore</button>}
      </div>
    );
  }
  if (t === "preference_saved") return <div className="action-card"><Heart size={16} /><span><strong>Added to your taste:</strong> {event.note}</span></div>;
  if (t === "recipe_noted") return <div className="action-card"><BookOpen size={16} /><span><strong>Added a note to the recipe:</strong> {event.note}</span></div>;
  return null;
}

/**
 * The after-dinner conversation: the chef reads the ratings and comments, asks what to change, then updates the recipe,
 * remembers a taste, or (after asking) takes the recipe out of the book. The transcript lives here; the server is stateless.
 */
export default function Debrief({ recipeId }) {
  const qc = useQueryClient();
  const [turns, setTurns] = useState([]); // { role, text, events }
  const [text, setText] = useState("");
  const [undone, setUndone] = useState({}); // "turn-event" -> true
  const started = useRef(false);
  const endRef = useRef(null);

  const refresh = () => ["recipe", "recipes", "history", "plan", "taste", "trash"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
  const send = useMutation({
    mutationFn: ({ text: t, history }) => api.debrief(recipeId, { text: t, history }),
    onSuccess: (r) => { setTurns((ts) => [...ts, { role: "assistant", text: r.reply, events: r.events }]); refresh(); },
    onError: (_e, vars) => { if (vars.text) { setTurns((ts) => ts.slice(0, -1)); setText(vars.text); } }, // put the message back so it can be re-sent
  });
  const undo = useMutation({
    mutationFn: ({ event }) => (event.type === "recipe_retired" ? api.restoreRecipe(event.recipe_id) : api.undoRevision(event.recipe_id)),
    onSuccess: (_d, { id }) => { setUndone((u) => ({ ...u, [id]: true })); refresh(); },
  });

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    send.mutate({ text: null, history: [] }); // the chef speaks first
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }, [turns.length, send.isPending]);

  const submit = (e) => {
    e.preventDefault();
    const t = text.trim();
    if (!t || send.isPending) return;
    send.mutate({ text: t, history: turns });
    setTurns((ts) => [...ts, { role: "user", text: t }]);
    setText("");
  };

  return (
    <div className="debrief stack">
      <h2 style={{ margin: 0, textAlign: "center" }}>Talk it through with the chef</h2>
      <div className="stack" style={{ textAlign: "left" }}>
        {turns.map((m, i) => (
          <React.Fragment key={i}>
            <div className={`bubble ${m.role}`}><ReactMarkdown>{m.text}</ReactMarkdown></div>
            {(m.events || []).map((e, k) => (
              <ActionCard key={k} event={e} undone={undone[`${i}-${k}`]} busy={undo.isPending}
                onUndo={() => undo.mutate({ event: e, id: `${i}-${k}` })} />
            ))}
          </React.Fragment>
        ))}
        {send.isPending && <div className="thinking"><img className="art" src={chefThinking} alt="" /><span className="muted">Chef is thinking…</span></div>}
        {(send.isError || undo.isError) && <div className="error">{(send.error || undo.error).message}</div>}
        <div ref={endRef} />
      </div>
      <form className="chat-input" style={{ padding: 0, border: 0, background: "none" }} onSubmit={submit}>
        <input value={text} placeholder="Reply to the chef…" onChange={(e) => setText(e.target.value)} />
        <button className="btn" disabled={send.isPending || !text.trim()} aria-label="Send"><Send size={18} /></button>
      </form>
      <p className="muted" style={{ margin: 0, fontSize: ".8rem", textAlign: "center" }}>
        <CalendarX size={12} style={{ verticalAlign: "-1px" }} /> Changes are undoable. Nothing is removed without you saying yes.
      </p>
    </div>
  );
}
