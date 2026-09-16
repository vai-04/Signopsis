import { Check, HelpCircle, PauseCircle, Sparkles, Loader2 } from "lucide-react";
import { motion } from "framer-motion";
import { TRUST, TRUST_LEVEL } from "../services/adapters.js";
import { cx } from "../utils/cx.js";

const ICON = { high: Check, enhanced: Sparkles, repair: HelpCircle, hold: PauseCircle, pending: Loader2 };

/** Icon + word + colour: state is never carried by colour alone. */
export function TrustBadge({ state, size = "md", className = "", showVerb = false }) {
  if (state === "pending") {
    return (
      <span className={cx("inline-flex items-center gap-1.5 rounded-full border-2 border-dashed border-ink/30 bg-white px-2.5 py-1 text-xs font-bold text-mute", className)}>
        <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> Reading…
      </span>
    );
  }
  const t = TRUST[state] || TRUST.hold;
  const Icon = ICON[state] || PauseCircle;
  const sz = size === "sm" ? "px-2 py-0.5 text-[11px]" : size === "lg" ? "px-3.5 py-1.5 text-sm" : "px-2.5 py-1 text-xs";
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 rounded-full font-bold uppercase tracking-wider",
        state === "repair" && "outline-2 outline-dashed outline-offset-2 outline-coral",
        state === "hold" && "hatch",
        sz, className,
      )}
      style={{ backgroundColor: t.color, color: t.ink }}
    >
      <Icon className={size === "lg" ? "h-4 w-4" : "h-3.5 w-3.5"} aria-hidden="true" strokeWidth={2.6} />
      <span>{t.label}</span>
      {showVerb && <span className="font-medium normal-case tracking-normal opacity-80">· {t.verb}</span>}
    </span>
  );
}

/**
 * Qualitative trust bar. Four labelled stops, a fill that eases to the current state,
 * no numbers. `state` may be "pending" while a phrase is being read.
 */
export function TrustBar({ state = "pending", compact = false, className = "", label = "Trust" }) {
  const order = ["hold", "repair", "enhanced", "high"];
  const level = state === "pending" ? 0.08 : TRUST_LEVEL[state] ?? 0;
  const t = TRUST[state];
  return (
    <div className={cx("w-full", className)} role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={100}
      aria-valuenow={Math.round(level * 100)} aria-valuetext={state === "pending" ? "reading" : `${t?.label}: ${t?.verb}`}>
      <div className="relative h-3 overflow-hidden rounded-full bg-ink/8">
        <motion.div
          className={cx("absolute inset-y-0 left-0 rounded-full", state === "hold" && "hatch", state === "pending" && "animate-pulse")}
          initial={false}
          animate={{ width: `${level * 100}%` }}
          transition={{ type: "spring", stiffness: 120, damping: 20 }}
          style={{ backgroundColor: state === "pending" ? "#c9cfca" : t?.color }}
        />
        {[0.35, 0.69, 0.93].map(x => (
          <span key={x} className="absolute inset-y-0 w-0.5 bg-light" style={{ left: `${x * 100}%` }} />
        ))}
      </div>
      {!compact && (
        <div className="mt-1.5 grid grid-cols-4 text-[10.5px] font-semibold uppercase tracking-wider">
          {order.map(k => (
            <span key={k} className={cx("transition-colors", k === state ? "text-ink" : "text-mute", k === "high" && "text-right", k === "enhanced" && "text-center", k === "repair" && "text-center")}>
              {k === state && <span aria-hidden="true">▸ </span>}{TRUST[k].label}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
