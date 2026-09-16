import { motion } from "framer-motion";
import { glossLabel, certaintyWord } from "../services/adapters.js";
import { cx } from "../utils/cx.js";

/**
 * ISL gloss tokens. Accepts GlossItem[] (text->sign) or string[] (sign->text / partials).
 * Fingerspelled items get a dotted border + "spelled" tag; the active one is lifted.
 */
export function GlossStrip({ items = [], active = -1, onPick, size = "md", className = "", showCertainty = false, label = "Sign gloss" }) {
  if (!items.length) return null;
  return (
    <ol className={cx("flex flex-wrap items-center gap-1.5", className)} aria-label={label}>
      {items.map((it, i) => {
        const g = typeof it === "string" ? { g: it, fingerspelled: it.startsWith("FS:") } : it;
        const unknown = g.g === "?";
        const on = i === active;
        const Tag = onPick ? motion.button : motion.span;
        return (
          <li key={`${g.g}-${i}`} className="flex items-center gap-1.5">
            <Tag
              type={onPick ? "button" : undefined}
              onClick={onPick ? () => onPick(i) : undefined}
              layout
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: on ? -3 : 0, scale: on ? 1.06 : 1 }}
              transition={{ type: "spring", stiffness: 380, damping: 26, delay: Math.min(i * 0.03, 0.3) }}
              className={cx(
                "gloss-token",
                size === "sm" && "px-2 py-0.5 text-[11.5px]",
                size === "lg" && "px-3.5 py-1.5 text-base",
                g.fingerspelled && "border-dashed",
                unknown && "border-coral text-coral-deep",
                on && "border-ink bg-ink text-light",
                onPick && "min-h-10 cursor-pointer hover:-translate-y-0.5",
              )}
              aria-current={on ? "true" : undefined}
              title={g.fingerspelled ? "Fingerspelled" : undefined}
            >
              <span>{unknown ? "unknown sign" : glossLabel(g)}</span>
              {g.fingerspelled && <span className={cx("ml-1.5 rounded bg-ink/8 px-1 text-[9.5px] font-semibold uppercase", on && "bg-white/15")}>spelled</span>}
              {showCertainty && g.roundtrip != null && (
                <span className={cx("ml-1.5 text-[10px] font-semibold uppercase", on ? "text-light/70" : "text-mute")}>{certaintyWord(g.roundtrip)}</span>
              )}
            </Tag>
            {i < items.length - 1 && <span className="text-ink/25" aria-hidden="true">·</span>}
          </li>
        );
      })}
    </ol>
  );
}
