import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Check, Lightbulb, Pause, Play, X } from "lucide-react";
import { api } from "../api";
import { fmtClock, scaleIngredient } from "../lib/format";

function useWakeLock() {
  useEffect(() => {
    let lock;
    const acquire = async () => { try { lock = await navigator.wakeLock?.request("screen"); } catch { /* unsupported or denied */ } };
    acquire();
    const onVisible = () => document.visibilityState === "visible" && acquire();
    document.addEventListener("visibilitychange", onVisible);
    return () => { document.removeEventListener("visibilitychange", onVisible); lock?.release?.(); };
  }, []);
}

function beep() {
  try {
    const ctx = new AudioContext();
    [0, 0.3, 0.6].forEach((t) => {
      const o = ctx.createOscillator(); const g = ctx.createGain();
      o.frequency.value = 880; g.gain.value = 0.2; o.connect(g); g.connect(ctx.destination);
      o.start(ctx.currentTime + t); o.stop(ctx.currentTime + t + 0.2);
    });
  } catch { /* audio blocked */ }
}

/** Counts down from `seconds`; resets whenever the step changes (key). */
function StepTimer({ seconds }) {
  const [left, setLeft] = useState(seconds);
  const [running, setRunning] = useState(false);
  const endAt = useRef(null);
  useEffect(() => {
    if (!running) return;
    endAt.current = Date.now() + left * 1000; // wall-clock based: survives a throttled background tab
    const id = setInterval(() => {
      const remaining = Math.ceil((endAt.current - Date.now()) / 1000);
      if (remaining <= 0) { setLeft(0); setRunning(false); beep(); } else setLeft(remaining);
    }, 250);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running]);
  const ringing = left === 0;
  return (
    <div className={`timer ${ringing ? "ringing" : ""}`}>
      <span className="clock">{ringing ? "Time!" : fmtClock(left)}</span>
      {!ringing && <button className="btn small" onClick={() => setRunning(!running)}>{running ? <><Pause size={14} /> Pause</> : <><Play size={14} /> Start</>}</button>}
      <button className="btn outline small" onClick={() => { setRunning(false); setLeft(seconds); }}>Reset</button>
    </div>
  );
}

export default function Cook() {
  const { id } = useParams();
  const [sp] = useSearchParams();
  const { data: r } = useQuery({ queryKey: ["recipe", id], queryFn: () => api.recipe(id) });
  const [i, setI] = useState(-1); // -1 = mise en place, steps.length = done
  const [checked, setChecked] = useState({});
  useWakeLock();

  const factor = useMemo(() => (r ? (+sp.get("servings") || r.servings) / r.servings : 1), [r, sp]);
  if (!r) return <div className="cook"><div className="cook-body muted">Loading…</div></div>;
  const total = r.steps.length;
  const step = r.steps[i];
  const done = i >= total;

  return (
    <div className="cook">
      <div className="cook-top">
        <strong style={{ fontFamily: "var(--font-display)", fontSize: "1.2rem" }}>{r.title}</strong>
        <Link to={`/recipes/${r.id}`} className="icon-btn" aria-label="Exit cook mode"><X size={20} /></Link>
      </div>
      <div className="cook-progress"><div style={{ width: `${((i + 1) / (total + 1)) * 100}%` }} /></div>
      <div className="cook-body">
        {i === -1 && (
          <>
            <div className="cook-label">Mise en place: gather everything</div>
            <ul className="cook-ings">
              {r.ingredients.map((ing, k) => (
                <li key={k} className={checked[k] ? "done" : ""} onClick={() => setChecked({ ...checked, [k]: !checked[k] })}>
                  <input type="checkbox" readOnly checked={!!checked[k]} /> {scaleIngredient(ing, factor)}{ing.note && `, ${ing.note}`}
                </li>
              ))}
            </ul>
            {r.chef_tips[0] && <div className="tip-box"><Lightbulb size={16} style={{ verticalAlign: "-3px" }} /> {r.chef_tips[0]}</div>}
          </>
        )}
        {step && (
          <>
            <div className="cook-label">Step {i + 1} of {total}</div>
            <div className="cook-step">{step.text}</div>
            {step.timer_seconds > 0 && <StepTimer key={i} seconds={step.timer_seconds} />}
            {step.tip && <div className="tip-box"><Lightbulb size={16} style={{ verticalAlign: "-3px" }} /> {step.tip}</div>}
          </>
        )}
        {done && (
          <div className="stack" style={{ alignItems: "center", textAlign: "center" }}>
            <Check size={64} color="var(--color-forest)" />
            <h1>Dinner is served.</h1>
            <p className="muted">How did it turn out?</p>
            <Rate recipe={r} />
            <Link className="btn" to={`/recipes/${r.id}`}>Back to recipe</Link>
          </div>
        )}
      </div>
      {!done && (
        <div className="cook-nav">
          <button className="btn outline" disabled={i < 0} onClick={() => setI(i - 1)}><ArrowLeft size={20} /> Back</button>
          <button className="btn" onClick={() => setI(i + 1)}>{i === -1 ? "Start" : i === total - 1 ? "Finish" : "Next"} <ArrowRight size={20} /></button>
        </div>
      )}
    </div>
  );
}

function Rate({ recipe }) {
  const [stars, setStars] = useState(recipe.rating || 0);
  return (
    <div className="row" style={{ justifyContent: "center" }}>
      {[1, 2, 3, 4, 5].map((n) => (
        <button key={n} className="icon-btn" aria-label={`${n} stars`} onClick={() => { setStars(n); api.patchRecipe(recipe.id, { rating: n }); }}>
          <span style={{ color: "var(--color-gravel)", fontSize: "1.6rem", lineHeight: 1 }}>{n <= stars ? "★" : "☆"}</span>
        </button>
      ))}
    </div>
  );
}
