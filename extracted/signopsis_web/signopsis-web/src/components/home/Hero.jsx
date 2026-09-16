import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, ArrowDown, Mic, Hand } from "lucide-react";
import { ThreeScene } from "../ThreeScene.jsx";
import { TrustBadge } from "../TrustBadge.jsx";
import { GlossStrip } from "../GlossStrip.jsx";
import { SpeakerDot } from "../Bits.jsx";
import { usePrefersReducedMotion } from "../../hooks/useMediaQuery.js";
import { cx } from "../../utils/cx.js";

// the hero tells one tiny story, on a loop: someone signs, it's unsure, it asks, it's clear
const STORY = [
  { scene: "signing", badge: "pending", who: "Priya", ch: "sign", text: "", gloss: ["ME", "?"], note: "Reading Priya's signs…" },
  { scene: "repair", badge: "repair", who: "Priya", ch: "sign", text: "Which sign did you mean?", gloss: ["ME", "BANK", "GO"], options: ["BANK", "RIVER"], note: "Two signs look alike. It asks." },
  { scene: "enhanced", badge: "enhanced", who: "Priya", ch: "sign", text: "I'm going to the bank.", gloss: ["ME", "BANK", "GO"], note: "Her answer settles it." },
  { scene: "high", badge: "high", who: "Dr. Rao", ch: "speech", text: "Great, it's open till four.", gloss: ["BANK", "OPEN", "TIME-4"], note: "Speech → the avatar signs it." },
  { scene: "hold", badge: "hold", who: "Priya", ch: "sign", text: "Too dark to read. Nothing shown.", gloss: [], note: "Bad light? It holds, and says why." },
];
const PICKS = [
  { key: "signing", label: "Signing" },
  { key: "high", label: "Clear" },
  { key: "enhanced", label: "Enhanced" },
  { key: "repair", label: "Checking" },
  { key: "hold", label: "Held" },
];

export function Hero() {
  const reduced = usePrefersReducedMotion();
  const [i, setI] = useState(0);
  const [pinned, setPinned] = useState(null);
  useEffect(() => {
    if (pinned || reduced) return undefined;
    const t = setInterval(() => setI(x => (x + 1) % STORY.length), 3400);
    return () => clearInterval(t);
  }, [pinned, reduced]);
  const s = pinned ? STORY.find(x => x.scene === pinned) || { ...STORY[0], scene: pinned } : STORY[i];

  return (
    <section className="relative overflow-hidden">
      <div aria-hidden="true" className="pointer-events-none absolute -right-40 -top-40 h-[36rem] w-[36rem] rounded-full bg-sage/35 blur-3xl" />
      <div aria-hidden="true" className="pointer-events-none absolute -left-32 top-64 h-80 w-80 rounded-full bg-coral/20 blur-3xl" />
      <div className="relative mx-auto grid max-w-7xl items-center gap-8 px-4 pb-12 pt-6 sm:px-6 lg:grid-cols-[1.02fr_1fr] lg:pb-20 lg:pt-10">
        <div>
          <motion.p initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
            className="inline-flex items-center gap-2 rounded-full border border-ink/10 bg-white/70 py-1.5 pl-1.5 pr-4 text-sm font-semibold backdrop-blur">
            <span className="rounded-full bg-ink px-2.5 py-0.5 font-mono text-[11px] font-bold uppercase tracking-wider text-light">ISL first</span>
            Sign ⇄ speech, both ways, live
          </motion.p>
          <h1 className="mt-6 text-[clamp(2.9rem,7.4vw,6.3rem)] font-extrabold leading-[0.92] tracking-[-0.05em]">
            <motion.span className="block" initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}>Communication</motion.span>
            <motion.span className="block" initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}>
              without the{" "}
              <span className="relative inline-block whitespace-nowrap text-coral-deep">
                guesswork
                <svg className="absolute -bottom-[0.12em] left-0 h-[0.3em] w-full" viewBox="0 0 300 20" preserveAspectRatio="none" aria-hidden="true">
                  <motion.path d="M3 14 C 60 3, 120 18, 180 9 S 270 5, 297 11" stroke="#1F2421" strokeWidth="5" fill="none" strokeLinecap="round"
                    initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ delay: 0.7, duration: 0.8 }} />
                </svg>
              </span>
              <motion.span className="text-moss" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1.2 }}>.</motion.span>
            </motion.span>
          </h1>
          <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.35 }} className="mt-6 max-w-xl text-lg leading-relaxed text-ink-soft sm:text-xl">
            SIGNOPSIS turns signing into captions and voice, and speech into a signing avatar. It shows how sure it is,
            <b className="text-ink"> asks when it isn't</b>, and learns the signs you actually use.
          </motion.p>
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.45 }} className="mt-8 flex flex-wrap gap-3">
            <a href="#/converse" className="btn-primary min-h-14 px-7 text-lg">Try SIGNOPSIS <ArrowRight className="h-5 w-5" aria-hidden="true" /></a>
            <a href="#/home#how" className="btn-ghost min-h-14 px-7 text-lg">See how it works <ArrowDown className="h-5 w-5" aria-hidden="true" /></a>
          </motion.div>
          <div className="mt-10">
            <p className="eyebrow">The scene on the right is the trust state · try one</p>
            <div className="mt-2 flex flex-wrap gap-1.5" role="radiogroup" aria-label="Scene state">
              {PICKS.map(p => (
                <button key={p.key} role="radio" aria-checked={s.scene === p.key}
                  onClick={() => setPinned(pinned === p.key ? null : p.key)}
                  className={cx("chip", s.scene === p.key && "border-ink bg-ink text-light hover:text-light")}>
                  {p.label}
                </button>
              ))}
              {pinned && <button className="chip border-dashed" onClick={() => setPinned(null)}>↻ Auto</button>}
            </div>
          </div>
        </div>

        <div className="relative">
          <div className="relative aspect-square w-full overflow-hidden rounded-[2.5rem] bg-gradient-to-br from-white via-light to-sage-soft shadow-(--shadow-lift)">
            <ThreeScene state={s.scene} className="absolute inset-0" />
            <div className="pointer-events-none absolute left-5 top-5 flex items-center gap-2 rounded-full bg-white/80 px-3 py-1.5 text-xs font-bold backdrop-blur">
              <Mic className="h-3.5 w-3.5 text-coral-deep" aria-hidden="true" /> voice
              <span className="text-mute">⇄</span>
              <Hand className="h-3.5 w-3.5 text-moss" aria-hidden="true" /> hands
            </div>
            <AnimatePresence mode="wait">
              <motion.div key={s.scene} initial={{ opacity: 0, y: 18, rotate: -2 }} animate={{ opacity: 1, y: 0, rotate: 0 }} exit={{ opacity: 0, y: -10 }}
                transition={{ type: "spring", stiffness: 220, damping: 22 }}
                className={cx("absolute inset-x-4 bottom-4 rounded-3xl bg-white/92 p-4 shadow-(--shadow-lift) backdrop-blur sm:inset-x-6 sm:bottom-6",
                  s.badge === "repair" && "ring-2 ring-coral", s.badge === "hold" && "ring-2 ring-ink")}
                aria-live="polite">
                <div className="flex items-center gap-2">
                  <SpeakerDot name={s.who} index={s.who === "Priya" ? 0 : 1} channel={s.ch} size={26} />
                  <span className="text-sm font-bold">{s.who}</span>
                  <TrustBadge state={s.badge} size="sm" />
                </div>
                {s.text && <p className="mt-2 text-xl font-extrabold leading-snug sm:text-2xl">{s.text}</p>}
                {s.options && (
                  <div className="mt-2 flex gap-2">
                    {s.options.map((o, k) => <span key={o} className={cx("gloss-token", k === 0 && "border-coral bg-coral text-ink")}>{k + 1} · {o}</span>)}
                    <span className="gloss-token border-dashed text-mute">Neither</span>
                  </div>
                )}
                {!s.options && s.gloss.length > 0 && <GlossStrip items={s.gloss} size="sm" className="mt-2" />}
                <p className="mt-2 text-xs font-semibold text-mute">{s.note}</p>
              </motion.div>
            </AnimatePresence>
          </div>
          <div className="absolute -right-2 -top-4 hidden rotate-6 rounded-2xl bg-coral px-4 py-2 font-mono text-xs font-bold uppercase tracking-wider text-ink shadow-lg sm:block">
            no raw scores. just words.
          </div>
        </div>
      </div>
    </section>
  );
}
