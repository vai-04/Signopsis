import { useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Hand, Mic, Keyboard, Monitor, Radio, Server, FlaskConical, Loader2 } from "lucide-react";
import { useBackend } from "../hooks/useBackend.js";
import { cx } from "../utils/cx.js";

const SPEAKER_COLORS = ["#689D4B", "#D96868", "#1F2421", "#91AE6E", "#b8574f", "#4E7A36"];
const SHAPES = ["circle", "square", "diamond", "triangle"];
const CHANNEL_ICON = { sign: Hand, speech: Mic, text: Keyboard, screen: Monitor };

export function speakerStyle(index) {
  return { color: SPEAKER_COLORS[index % SPEAKER_COLORS.length], shape: SHAPES[index % SHAPES.length] };
}

/** Speaker identity: colour AND shape AND initial, so it survives colour blindness and greyscale. */
export function SpeakerDot({ name = "?", index = 0, channel, size = 28, className = "" }) {
  const { color, shape } = speakerStyle(index);
  const Icon = channel ? CHANNEL_ICON[channel] : null;
  const radius = shape === "circle" ? "9999px" : shape === "square" ? "8px" : "6px";
  return (
    <span className={cx("relative inline-grid shrink-0 place-items-center", className)} style={{ width: size, height: size }} aria-hidden="true">
      <span
        className="absolute inset-0"
        style={{
          background: color, borderRadius: radius,
          transform: shape === "diamond" ? "rotate(45deg) scale(.82)" : undefined,
          clipPath: shape === "triangle" ? "polygon(50% 4%, 98% 96%, 2% 96%)" : undefined,
        }}
      />
      <span className={cx("relative font-extrabold text-white", shape === "triangle" && "translate-y-[2px]")} style={{ fontSize: size * 0.42 }}>
        {name.slice(0, 1).toUpperCase()}
      </span>
      {Icon && (
        <span className="absolute -right-1.5 -bottom-1.5 grid h-4 w-4 place-items-center rounded-full bg-white shadow ring-1 ring-ink/10">
          <Icon className="h-2.5 w-2.5 text-ink" strokeWidth={2.8} />
        </span>
      )}
    </span>
  );
}

/** Backend connection: LIVE (server) or DEMO (mock). */
export function ModeBadge({ className = "", onClick, wrapClass }) {
  const b = useBackend();
  if (wrapClass) return <span className={wrapClass}><ModeBadge className={className} onClick={onClick} /></span>;
  const live = b.resolved === "live";
  const broken = live && !!b.error;
  const Icon = b.checking ? Loader2 : live ? Server : FlaskConical;
  const label = b.checking ? "Connecting" : live ? (b.error ? "Server error" : "Live server") : "Demo mode";
  return (
    <button
      type="button"
      onClick={onClick}
      title={live ? "Connected to the SIGNOPSIS backend" : "Running on recorded backend data in your browser. Connect a server in Settings."}
      className={cx("inline-flex min-h-10 items-center gap-2 rounded-full border-2 px-3 text-xs font-bold uppercase tracking-wider transition",
        broken ? "border-coral/50 bg-coral-soft text-ink" : live ? "border-moss/40 bg-moss/10 text-moss-deep" : "border-ink/15 bg-white text-ink-soft hover:border-ink/40", className)}
    >
      <span className="relative flex h-2.5 w-2.5">
        {live && !broken && !b.checking && <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-moss opacity-60" />}
        <span className={cx("relative inline-flex h-2.5 w-2.5", live && !broken ? "rounded-full bg-moss" : broken ? "rotate-45 bg-coral" : "rounded-full bg-coral")} />
      </span>
      <Icon className={cx("h-3.5 w-3.5", b.checking && "animate-spin")} aria-hidden="true" />
      {label}
    </button>
  );
}

/** Pipeline mode chip (WATCH / SPEAK / CONVERSE / LISTEN / SCREEN) */
export function PipelineChip({ mode, className = "" }) {
  return (
    <span className={cx("inline-flex items-center gap-1.5 rounded-full bg-ink px-2.5 py-1 font-mono text-[11px] font-bold tracking-widest text-light", className)}>
      <Radio className="h-3 w-3 text-sage" aria-hidden="true" /> {mode}
    </span>
  );
}

/** Enrollment shots: filled / current / empty, with numbers (not colour only) */
export function ShotProgress({ have = 0, need = 4, className = "" }) {
  return (
    <ol className={cx("flex items-center gap-2", className)} aria-label={`${have} of ${need} samples recorded`}>
      {Array.from({ length: need }, (_, i) => {
        const done = i < have, cur = i === have;
        return (
          <li key={i} className="flex items-center gap-2">
            <motion.span
              initial={false}
              animate={{ scale: cur ? 1.12 : 1 }}
              className={cx("grid h-10 w-10 place-items-center rounded-2xl border-2 text-sm font-extrabold",
                done ? "border-moss bg-moss text-ink" : cur ? "border-ink bg-white text-ink" : "border-ink/15 bg-white/60 text-mute")}
            >
              {done ? "✓" : i + 1}
            </motion.span>
            {i < need - 1 && <span className={cx("h-0.5 w-5 rounded", done ? "bg-moss" : "bg-ink/15")} aria-hidden="true" />}
          </li>
        );
      })}
    </ol>
  );
}

export function Toast({ message, onClose, tone = "ink", ms = 4500 }) {
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    if (!message) return undefined;
    const t = setTimeout(() => close.current?.(), ms);
    return () => clearTimeout(t);
  }, [message, ms]);
  return (
    <AnimatePresence>
      {message && (
        <motion.div
          role="status"
          initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 20, opacity: 0 }}
          className={cx("fixed bottom-24 left-1/2 z-[80] flex max-w-[92vw] -translate-x-1/2 items-center gap-3 rounded-2xl px-4 py-3 text-sm font-semibold shadow-(--shadow-lift) md:bottom-8",
            tone === "coral" ? "bg-coral text-ink" : "bg-ink text-light")}
        >
          <span>{message}</span>
          {onClose && <button className="min-h-10 rounded-full px-3 underline underline-offset-4" onClick={onClose}>Dismiss</button>}
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function Segmented({ options, value, onChange, label, className = "", size = "md" }) {
  return (
    <div role="radiogroup" aria-label={label} className={cx("inline-flex flex-wrap rounded-full bg-ink/6 p-1", className)}>
      {options.map(o => {
        const on = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={on}
            disabled={o.disabled}
            onClick={() => onChange(o.value)}
            className={cx("relative min-h-10 rounded-full px-3.5 text-sm font-semibold transition-colors disabled:opacity-40",
              size === "lg" && "min-h-12 px-5", on ? "text-light" : "text-ink-soft hover:text-ink")}
          >
            {on && <motion.span layoutId={`seg-${label}`} className="absolute inset-0 rounded-full bg-ink" transition={{ type: "spring", stiffness: 400, damping: 32 }} />}
            <span className="relative inline-flex items-center gap-1.5">{o.icon}{o.label}</span>
          </button>
        );
      })}
    </div>
  );
}

export function Kbd({ children }) {
  return <kbd className="rounded-md border border-ink/20 bg-white px-1.5 py-0.5 font-mono text-[11px] font-bold text-ink-soft shadow-[0_1px_0_rgba(0,0,0,.15)]">{children}</kbd>;
}
