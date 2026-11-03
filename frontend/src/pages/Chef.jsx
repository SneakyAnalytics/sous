import React, { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, CalendarPlus, ChefHat, Pencil, Send, Trash2 } from "lucide-react";
import { api } from "../api";
import { chefError, chefThinking, chefWave } from "../assets";

const dayName = (iso) => new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { weekday: "long" });

const STARTERS = [
  "What's a great weeknight dinner under 40 minutes?",
  "Teach me to cook the perfect steak",
  "Best-loved classic pasta I should master",
  "I have chicken thighs and rice, what should I make?",
];

export default function Chef() {
  const qc = useQueryClient();
  const { data: history = [] } = useQuery({ queryKey: ["chat"], queryFn: api.chat });
  const [sp] = useSearchParams();
  const [text, setText] = useState(sp.get("ask") || ""); // the planner links here with a day prefilled
  const [pending, setPending] = useState(null); // the user's message shown while the chef thinks
  const endRef = useRef(null);

  const send = useMutation({
    mutationFn: api.sendChat,
    onSettled: () => {
      setPending(null);
      qc.invalidateQueries({ queryKey: ["chat"] });
      qc.invalidateQueries({ queryKey: ["recipes"] });
      qc.invalidateQueries({ queryKey: ["recipe"] });
      qc.invalidateQueries({ queryKey: ["taste"] });
      qc.invalidateQueries({ queryKey: ["plan"] });
    },
  });
  const clear = useMutation({ mutationFn: api.clearChat, onSuccess: () => qc.invalidateQueries({ queryKey: ["chat"] }) });

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [history.length, pending, send.isPending]);

  const submit = (msg) => {
    const t = msg.trim();
    if (!t || send.isPending) return;
    setPending(t);
    setText("");
    send.mutate(t);
  };

  return (
    <div className="chat">
      <div className="chat-log">
        {history.length === 0 && !pending && (
          <div className="stack" style={{ margin: "auto 0" }}>
            <img className="art hero" style={{ width: "min(150px, 38vw)" }} src={chefWave} alt="Chef Claude waving" />
            <h1><ChefHat style={{ verticalAlign: "-4px" }} /> What are we cooking?</h1>
            <p className="muted">I'm your chef. Ask for ideas, techniques, or the best version of a dish. When you pick one, I'll write it into your recipe book.</p>
            <div className="suggestions">
              {STARTERS.map((s) => <button key={s} className="btn outline small" onClick={() => submit(s)}>{s}</button>)}
            </div>
          </div>
        )}
        {history.map((m) => (
          <React.Fragment key={m.id}>
            <div className={`bubble ${m.role}`}><ReactMarkdown>{m.text}</ReactMarkdown></div>
            {m.events.map((e, i) => (
              <Link key={i} className="event-card" to={`/recipes/${e.recipe_id}`}>
                {e.type === "recipe_saved" ? <BookOpen size={18} /> : e.type === "recipe_revised" ? <Pencil size={18} /> : <CalendarPlus size={18} />}
                <span><strong>{e.title}</strong> <span className="muted">{e.type === "recipe_saved" ? "saved to recipes" : e.type === "recipe_revised" ? "revised" : e.cook_date ? `planned for ${dayName(e.cook_date)}` : "added to this week"}</span></span>
              </Link>
            ))}
          </React.Fragment>
        ))}
        {pending && <div className="bubble user">{pending}</div>}
        {send.isPending && <div className="thinking"><img className="art" src={chefThinking} alt="" /><span className="muted">Chef is thinking…</span></div>}
        {send.isError && <div className="thinking"><img className="art" src={chefError} alt="" /><span className="error">{send.error.message}</span></div>}
        <div ref={endRef} />
      </div>
      <form className="chat-input" onSubmit={(e) => { e.preventDefault(); submit(text); }}>
        <textarea rows={1} value={text} placeholder="Ask the chef…" onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(text); } }} />
        <button className="btn" disabled={send.isPending || !text.trim()} aria-label="Send"><Send size={18} /></button>
        {history.length > 0 && (
          <button type="button" className="icon-btn" aria-label="Clear chat" onClick={() => confirm("Clear the whole conversation? Saved recipes stay.") && clear.mutate()}>
            <Trash2 size={18} />
          </button>
        )}
      </form>
    </div>
  );
}
