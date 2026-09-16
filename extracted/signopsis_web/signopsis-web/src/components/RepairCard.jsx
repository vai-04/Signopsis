import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { HelpCircle, PauseCircle, RotateCcw, Play, GraduationCap, X } from "lucide-react";
import { backend } from "../services/backend.js";
import { MiniSigner } from "./MiniSigner.jsx";
import { cx } from "../utils/cx.js";

const SPECIAL = new Set(["__none__", "__teach__", "__accept__", "SEND", "REPHRASE"]);

/**
 * Renders a RenderPlan.repair. Disambiguation options get a looping sign preview (GET /api/sign/{gloss}).
 * Keyboard: 1..n picks an option, Esc dismisses.
 */
export function RepairCard({ repair, reason, onAnswer, onDismiss, className = "", compact = false, autoFocus = true, hotkeys = true }) {
  const first = useRef(null);
  const [clips, setClips] = useState({});
  const hold = repair?.type === "resign";
  const opts = repair?.options || [];
  const signOpts = opts.filter(o => !SPECIAL.has(o.gloss));

  useEffect(() => {
    if (autoFocus) first.current?.focus({ preventScroll: true });
  }, [repair, autoFocus]);

  useEffect(() => {
    let alive = true;
    signOpts.forEach(o => {
      backend.sign(o.gloss).then(c => alive && setClips(m => ({ ...m, [o.gloss]: c }))).catch(() => {});
    });
    return () => { alive = false; };
  }, [repair]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!hotkeys) return undefined;
    const onKey = e => {
      if (e.target.closest?.("input,textarea,select")) return;
      const n = parseInt(e.key, 10);
      const list = displayed();
      if (n >= 1 && n <= list.length) { e.preventDefault(); onAnswer(list[n - 1]); }
      if (e.key === "Escape" && onDismiss) onDismiss();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (!repair) return null;

  // "Neither: re-sign" is always offered for disambiguation (maps to __none__)
  function displayed() {
    if (repair.type !== "disambiguate") return opts;
    const base = opts.filter(o => o.gloss !== "__none__");
    return [...base, { gloss: "__none__", label: "Neither: re-sign" }];
  }
  const list = displayed();
  const title = repair.type === "disambiguate" ? (repair.prompt || "Which sign did you mean?") : repair.prompt;
  const Icon = hold ? PauseCircle : HelpCircle;

  return (
    <motion.section
      role="alertdialog"
      aria-live="assertive"
      aria-label={title}
      initial={{ opacity: 0, y: 16, rotate: -1.2 }}
      animate={{ opacity: 1, y: 0, rotate: 0 }}
      exit={{ opacity: 0, y: 10 }}
      transition={{ type: "spring", stiffness: 260, damping: 24 }}
      className={cx("relative overflow-hidden rounded-[1.6rem] border-2 bg-white p-4 shadow-(--shadow-lift) sm:p-5",
        hold ? "border-ink" : "border-coral", className)}
    >
      <div className={cx("absolute inset-x-0 top-0 h-1.5", hold ? "bg-ink hatch" : "bg-coral")} aria-hidden="true" />
      <div className="flex items-start gap-3">
        <span className={cx("mt-0.5 grid h-10 w-10 shrink-0 place-items-center rounded-2xl", hold ? "bg-ink text-light" : "bg-coral text-ink")}>
          <Icon className="h-5 w-5" aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="eyebrow">{hold ? "Held · nothing shown" : repair.type === "confirm" ? "Check before sending" : "Quick question"}</p>
          <h3 className="mt-0.5 text-xl font-extrabold leading-tight tracking-tight sm:text-2xl">{title}</h3>
          {reason && !compact && humanReason(reason) && !title?.startsWith(humanReason(reason).replace(/\.$/, "")) && (
            <p className="mt-1 text-sm text-mute">{humanReason(reason)}</p>
          )}
        </div>
        {onDismiss && (
          <button type="button" onClick={onDismiss} className="btn-icon -mr-2 -mt-2 text-mute hover:text-ink" aria-label="Dismiss">
            <X className="h-5 w-5" />
          </button>
        )}
      </div>

      <div className={cx("mt-4 grid gap-2.5", signOpts.length ? "grid-cols-2 sm:grid-cols-[repeat(auto-fit,minmax(9rem,1fr))]" : "grid-cols-1 sm:grid-cols-2")}>
        {list.map((o, i) => {
          const special = SPECIAL.has(o.gloss);
          const isSign = !special;
          return (
            <button
              key={o.gloss + i}
              ref={i === 0 ? first : undefined}
              type="button"
              onClick={() => onAnswer(o)}
              aria-label={isSign ? `${o.label && o.label.toUpperCase() !== o.gloss ? `${o.gloss}, ${o.label}` : o.gloss}` : o.label}
              className={cx(
                "group relative flex min-h-12 items-center gap-3 rounded-2xl border-2 p-2 text-left transition",
                isSign ? "flex-col items-stretch border-ink/10 bg-light hover:border-ink" : "border-ink/10 bg-white px-4 hover:border-ink",
                o.gloss === "__none__" && signOpts.length && "col-span-2 sm:col-span-1",
              )}
            >
              {isSign && (
                <span aria-hidden="true" className="relative block aspect-[4/3] overflow-hidden rounded-xl bg-gradient-to-b from-sage-soft to-sage/60">
                  <MiniSigner clip={clips[o.gloss]} className="absolute inset-0" />
                  <span className="absolute left-2 top-2 inline-flex items-center gap-1 rounded-full bg-white/85 px-2 py-0.5 text-[10px] font-bold uppercase text-ink">
                    <Play className="h-2.5 w-2.5" aria-hidden="true" /> preview
                  </span>
                </span>
              )}
              <span className="flex items-center gap-2 px-1">
                <span className="grid h-6 w-6 shrink-0 place-items-center rounded-md border border-ink/20 font-mono text-[11px] font-bold text-mute" aria-hidden="true">{i + 1}</span>
                <span className={cx("font-extrabold", isSign ? "font-mono text-base uppercase tracking-wide" : "text-sm")}>
                  {o.gloss === "__none__" && <RotateCcw className="mr-1 inline h-4 w-4" aria-hidden="true" />}
                  {o.gloss === "__teach__" && <GraduationCap className="mr-1 inline h-4 w-4" aria-hidden="true" />}
                  {isSign ? o.gloss : o.label}
                </span>
              </span>
            </button>
          );
        })}
      </div>
      {!compact && hotkeys && <p className="mt-3 text-xs text-mute">Press <b>1</b>–<b>{list.length}</b> to answer. Your answer is remembered for this context.</p>}
    </motion.section>
  );
}

/** backend gate_reason strings contain numbers; the main UI keeps them qualitative */
export function humanReason(r = "") {
  const s = r
    .replace(/\s*\([^)]*\d[^)]*\)/g, "")                    // "(min 0.99 ≥ 0.75)", "(trust 0.47)"
    .replace(/,?\s*coverage\s*[\d.]+%?/gi, "")
    .replace(/\b(round-trip\s+)?trust\s*[\d.]+/gi, "")
    .replace(/\s*[≥<>]=?\s*[\d.]+/g, "")
    .replace(/\s{2,}/g, " ")
    .replace(/\s+([.,:])/g, "$1")
    .trim();
  const t = s.replace(/^[\s:.,;]+/, "").replace(/^[.\s]+$/, "");
  return t ? t[0].toUpperCase() + t.slice(1) : "";
}
