import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Lightbulb, ListChecks, Pause, Play, X } from "lucide-react";
import { api } from "../api";
import { chefCelebrate } from "../assets";
import { StarInput } from "../components/Stars";
import { fmtClock, scaleIngredient } from "../lib/format";
import { amountLabel, segmentStep, usedIngredients } from "../lib/ingredients";
import { swipeDirection } from "../lib/swipe";
import { clearCook, isRunning, loadCook, newTimer, pauseTimer, remaining, saveCook, startTimer, tick } from "../lib/cookState";

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

let audioCtx = null;
/** iOS only lets audio play after a tap, so every timer button primes one shared context. */
function unlockAudio() {
  try {
    audioCtx ||= new (window.AudioContext || window.webkitAudioContext)();
    if (audioCtx.state === "suspended") audioCtx.resume();
  } catch { /* no audio available */ }
}

function alarm() {
  try { navigator.vibrate?.([300, 150, 300, 150, 300]); } catch { /* unsupported */ }
  try {
    audioCtx ||= new (window.AudioContext || window.webkitAudioContext)();
    const ctx = audioCtx;
    [0, 0.3, 0.6].forEach((t) => {
      const o = ctx.createOscillator(); const g = ctx.createGain();
      o.frequency.value = 880; g.gain.value = 0.25; o.connect(g); g.connect(ctx.destination);
      o.start(ctx.currentTime + t); o.stop(ctx.currentTime + t + 0.2);
    });
  } catch { /* audio blocked */ }
}

function StepTimer({ timer, now, onToggle, onReset }) {
  const left = remaining(timer, now);
  const running = isRunning(timer);
  return (
    <div className={`timer ${timer.ringing ? "ringing" : ""}`}>
      <span className="clock">{timer.ringing ? "Time!" : fmtClock(left)}</span>
      {!timer.ringing && <button className="btn small" onClick={() => { unlockAudio(); onToggle(); }}>{running ? <><Pause size={14} /> Pause</> : <><Play size={14} /> Start</>}</button>}
      <button className="btn outline small" onClick={onReset}>{timer.ringing ? "Dismiss" : "Reset"}</button>
    </div>
  );
}

export default function Cook() {
  const { id } = useParams();
  const [sp] = useSearchParams();
  const { data: r } = useQuery({ queryKey: ["recipe", id], queryFn: () => api.recipe(id) });
  const servings = +sp.get("servings") || null;
  // Resume where a reload (or the phone dropping the app) left off.
  const [state, setState] = useState(() => loadCook(id, servings) || { i: -1, checked: {}, timers: {}, servings });
  const [showAll, setShowAll] = useState(false); // full ingredient list, reachable from every step
  const [now, setNow] = useState(() => Date.now());
  const touch = useRef(null); // where the current swipe started
  useWakeLock();

  const { i, checked, timers } = state;
  const anyRunning = Object.values(timers).some(isRunning);
  useEffect(() => {
    if (!anyRunning) return;
    const t = setInterval(() => {
      const n = Date.now();
      setNow(n);
      setState((st) => {
        const res = tick(st.timers, n);
        if (!res.rang.length) return st;
        alarm();
        return { ...st, timers: res.timers };
      });
    }, 250);
    return () => clearInterval(t);
  }, [anyRunning]);

  const total = r?.steps.length ?? 0;
  const done = r ? i >= total : false;
  useEffect(() => { if (r) (done ? clearCook(id) : saveCook(id, state)); }, [r, done, id, state]);

  const factor = useMemo(() => (r ? (servings || r.servings) / r.servings : 1), [r, servings]);
  if (!r) return <div className="cook"><div className="cook-body muted">Loading…</div></div>;
  const at = Math.min(i, total); // a saved step can't point past a recipe that has since been revised
  const step = r.steps[at];
  const used = step ? usedIngredients(step.text, r.ingredients) : [];
  const go = (n) => setState((st) => ({ ...st, i: n }));
  const setTimer = (k, fn) => setState((st) => ({ ...st, timers: { ...st.timers, [k]: fn(st.timers[k] || newTimer(r.steps[k].timer_seconds)) } }));
  const toggleCheck = (k) => setState((st) => ({ ...st, checked: { ...st.checked, [k]: !st.checked[k] } }));
  const onSwipeEnd = (e) => {
    const t = touch.current; touch.current = null;
    if (!t || done) return;
    const c = e.changedTouches[0];
    const dir = swipeDirection(c.clientX - t.x, c.clientY - t.y);
    if (dir === "next") go(Math.min(at + 1, total));
    else if (dir === "back" && at >= 0) go(at - 1);
  };
  const others = Object.entries(timers).filter(([k, t]) => +k !== at && (isRunning(t) || t.ringing));

  return (
    <div className="cook">
      <div className="cook-top">
        <strong className="cook-title">{r.title}</strong>
        <div className="row" style={{ gap: ".4rem", flexWrap: "nowrap" }}>
          <button className={`btn small ${showAll ? "" : "outline"}`} onClick={() => setShowAll(!showAll)} aria-pressed={showAll}><ListChecks size={16} /> Ingredients</button>
          <Link to={`/recipes/${r.id}`} className="icon-btn" aria-label="Exit cook mode"><X size={20} /></Link>
        </div>
      </div>
      {showAll && (
        <div className="cook-sheet">
          <ul className="cook-ings compact">
            {r.ingredients.map((ing, k) => (
              <li key={k} className={checked[k] ? "done" : ""} onClick={() => toggleCheck(k)}>
                <input type="checkbox" readOnly checked={!!checked[k]} /> {amountLabel(ing, factor)}
              </li>
            ))}
          </ul>
          <button className="btn outline small" onClick={() => confirm("Reset the steps, check marks and timers?") && (clearCook(id), setState({ i: -1, checked: {}, timers: {}, servings }))}>Start over</button>
        </div>
      )}
      {others.length > 0 && (
        <div className="timer-strip">
          {others.map(([k, t]) => (
            <button key={k} className={`chip-timer ${t.ringing ? "ringing" : ""}`} onClick={() => go(+k)}>
              Step {+k + 1} · {t.ringing ? "Time!" : fmtClock(remaining(t, now))}
            </button>
          ))}
        </div>
      )}
      <div className="cook-progress"><div style={{ width: `${((at + 1) / (total + 1)) * 100}%` }} /></div>
      <div className="cook-body" onTouchStart={(e) => { touch.current = { x: e.touches[0].clientX, y: e.touches[0].clientY }; }} onTouchEnd={onSwipeEnd}>
        {at === -1 && (
          <>
            <div className="cook-label">Mise en place: gather everything</div>
            <ul className="cook-ings">
              {r.ingredients.map((ing, k) => (
                <li key={k} className={checked[k] ? "done" : ""} onClick={() => toggleCheck(k)}>
                  <input type="checkbox" readOnly checked={!!checked[k]} /> {scaleIngredient(ing, factor)}{ing.note && `, ${ing.note}`}
                </li>
              ))}
            </ul>
            {r.chef_tips[0] && <div className="tip-box"><Lightbulb size={16} style={{ verticalAlign: "-3px" }} /> {r.chef_tips[0]}</div>}
          </>
        )}
        {step && (
          <>
            <div className="cook-label">Step {at + 1} of {total}</div>
            <div className="cook-step">
              {segmentStep(step.text, r.ingredients).map((seg, k) => seg.index === undefined ? seg.text : (
                <button key={k} type="button" className="ing-ref" data-amount={amountLabel(r.ingredients[seg.index], factor)}>{seg.text}</button>
              ))}
            </div>
            {used.length > 0 && (
              <div className="uses">
                <div className="cook-label">This step uses</div>
                <ul>{used.map((k) => <li key={k}>{amountLabel(r.ingredients[k], factor)}</li>)}</ul>
              </div>
            )}
            {step.timer_seconds > 0 && (
              <StepTimer timer={timers[at] || newTimer(step.timer_seconds)} now={now}
                onToggle={() => setTimer(at, (t) => (isRunning(t) ? pauseTimer(t, Date.now()) : startTimer(t, Date.now())))}
                onReset={() => setTimer(at, (t) => newTimer(t.total))} />
            )}
            {step.tip && <div className="tip-box"><Lightbulb size={16} style={{ verticalAlign: "-3px" }} /> {step.tip}</div>}
          </>
        )}
        {done && (
          <div className="stack" style={{ alignItems: "center", textAlign: "center" }}>
            <img className="art hero" src={chefCelebrate} alt="" />
            <h1>Dinner is served.</h1>
            <p className="muted">How did it turn out?</p>
            <Rate recipe={r} />
            <Link className="btn" to={`/recipes/${r.id}`}>Back to recipe</Link>
          </div>
        )}
      </div>
      {!done && (
        <div className="cook-nav">
          <button className="btn outline" disabled={at < 0} onClick={() => go(at - 1)}><ArrowLeft size={20} /> Back</button>
          <button className="btn" onClick={() => go(at + 1)}>{at === -1 ? "Start" : at === total - 1 ? "Finish" : "Next"} <ArrowRight size={20} /></button>
        </div>
      )}
    </div>
  );
}

function Rate({ recipe }) {
  const { data: household } = useQuery({ queryKey: ["household"], queryFn: api.household, staleTime: Infinity });
  const [stars, setStars] = useState({}); // person -> 1..5
  const [notes, setNotes] = useState("");
  const [saved, setSaved] = useState(false);
  const rated = Object.keys(stars).length;
  const save = useMutation({ mutationFn: () => api.logCook(recipe.id, { ratings: stars, notes }), onSuccess: () => setSaved(true) });
  return (
    <div className="stack" style={{ width: "100%", maxWidth: 520 }}>
      {(household?.members ?? []).map((who) => (
        <div key={who} className="row" style={{ justifyContent: "center", gap: ".4rem", flexWrap: "nowrap" }}>
          <strong style={{ minWidth: "3.5rem", textAlign: "right" }}>{who}</strong>
          <StarInput label={who} value={stars[who]} onChange={(v) => { setStars({ ...stars, [who]: v }); setSaved(false); }} />
        </div>
      ))}
      <textarea rows={3} value={notes} placeholder="What would we change next time? (the chef reads this)" onChange={(e) => { setNotes(e.target.value); setSaved(false); }} />
      <button className="btn" disabled={save.isPending || saved || (!Object.values(stars).some(Boolean) && !notes.trim())} onClick={() => { setStars(Object.fromEntries(Object.entries(stars).filter(([, n]) => n))); save.mutate(); }}>
        {saved ? "Saved. The chef will remember." : "Save how it went"}
      </button>
      {save.isError && <div className="error">{save.error.message}</div>}
    </div>
  );
}
