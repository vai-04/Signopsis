import { cx } from "../utils/cx.js";

/** SIGNOPSIS mark: two open palms meeting over a dot (the "point" of a conversation) */
export function LogoMark({ size = 36, className = "" }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden="true" className={className}>
      <rect width="48" height="48" rx="15" fill="#1F2421" />
      <path d="M11 33c0-8 4.5-14 10.5-14 3 0 4.5 2 4.5 4" stroke="#91AE6E" strokeWidth="4.2" fill="none" strokeLinecap="round" />
      <path d="M37 33c0-8-4.5-14-10.5-14" stroke="#F2F2F2" strokeWidth="4.2" fill="none" strokeLinecap="round" />
      <circle cx="24" cy="11.5" r="3.6" fill="#D96868" />
      <path d="M14 37h20" stroke="#689D4B" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

export function Wordmark({ className = "", tone = "ink" }) {
  return (
    <span className={cx("font-extrabold tracking-[-0.04em]", tone === "light" ? "text-light" : "text-ink", className)}>
      sign<span className="text-coral">o</span>psis
    </span>
  );
}

export function Logo({ className = "", tone = "ink", size = 36 }) {
  return (
    <span className={cx("inline-flex items-center gap-2.5", className)}>
      <LogoMark size={size} />
      <Wordmark tone={tone} className="text-[1.35rem] leading-none" />
    </span>
  );
}

/** hand-drawn underline / strike used in headings */
export function Scribble({ className = "", color = "#D96868", variant = "under" }) {
  if (variant === "strike") {
    return (
      <svg className={cx("pointer-events-none absolute inset-x-[-4%] top-1/2 h-[0.5em] w-[108%] -translate-y-1/2", className)} viewBox="0 0 200 20" preserveAspectRatio="none" aria-hidden="true">
        <path d="M3 13 C 40 6, 80 15, 120 8 S 180 6, 197 9" stroke={color} strokeWidth="5" fill="none" strokeLinecap="round" />
      </svg>
    );
  }
  return (
    <svg className={cx("pointer-events-none absolute -bottom-[0.18em] left-0 h-[0.35em] w-full", className)} viewBox="0 0 200 16" preserveAspectRatio="none" aria-hidden="true">
      <path d="M2 11 C 50 3, 90 14, 140 6 S 185 5, 198 8" stroke={color} strokeWidth="4.5" fill="none" strokeLinecap="round" />
    </svg>
  );
}

export function SectionTag({ n, children, tone = "ink" }) {
  return (
    <div className={cx("flex items-center gap-3 font-mono text-[11px] font-semibold uppercase tracking-[.22em]", tone === "light" ? "text-light/70" : "text-mute")}>
      <span className={cx("grid h-7 min-w-7 place-items-center rounded-full px-2 text-[11px]", tone === "light" ? "bg-light text-ink" : "bg-ink text-light")}>{n}</span>
      <span>{children}</span>
      <span className={cx("h-px w-10", tone === "light" ? "bg-light/30" : "bg-ink/20")} />
    </div>
  );
}
