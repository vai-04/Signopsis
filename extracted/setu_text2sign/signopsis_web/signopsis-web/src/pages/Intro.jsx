import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion, useMotionValue, useSpring, useTransform } from "framer-motion";
import { ArrowRight, RotateCcw } from "lucide-react";
import { LogoMark } from "../components/Brand.jsx";
import { usePrefersReducedMotion } from "../hooks/useMediaQuery.js";
import { cx } from "../utils/cx.js";

const HANDS = ["🤟", "✋", "👌", "✌️", "🤙", "👋", "☝️", "🤞", "🖐️"];
const NAME = "SIGNOPSIS".split("");
// phases: 0 type "synopsis" · 1 syn -> sign · 2 letters become hands · 3 hands become SIGNOPSIS · 4 invite
const TIMELINE = [0, 2300, 4000, 6700, 8100];

/* ------------------------------------------------------------------ backdrop */
function Backdrop({ reduced }) {
  const blobs = [
    { c: ["#D96868", "#91AE6E", "#D96868"], x: ["-10%", "8%", "-10%"], y: ["-12%", "6%", "-12%"], s: "62vmax", pos: "left-[-12vmax] top-[-18vmax]" },
    { c: ["#689D4B", "#D96868", "#689D4B"], x: ["6%", "-10%", "6%"], y: ["8%", "-6%", "8%"], s: "58vmax", pos: "right-[-16vmax] bottom-[-20vmax]" },
    { c: ["#91AE6E", "#F2F2F2", "#91AE6E"], x: ["0%", "12%", "0%"], y: ["0%", "10%", "0%"], s: "46vmax", pos: "right-[8vmax] top-[-14vmax]" },
    { c: ["#F2F2F2", "#91AE6E", "#F2F2F2"], x: ["0%", "-14%", "0%"], y: ["0%", "-8%", "0%"], s: "40vmax", pos: "left-[6vmax] bottom-[-16vmax]" },
  ];
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
      <div className="absolute inset-0 bg-light" />
      {blobs.map((b, i) => (
        <motion.div
          key={i}
          className={cx("absolute rounded-full opacity-70 blur-[90px] will-change-transform", b.pos)}
          style={{ width: b.s, height: b.s }}
          animate={reduced ? { backgroundColor: b.c[0] } : { backgroundColor: b.c, x: b.x, y: b.y, scale: [1, 1.12, 1] }}
          transition={{ duration: 14 + i * 3, repeat: Infinity, ease: "easeInOut" }}
        />
      ))}
      {!reduced && (
        <motion.div
          className="absolute left-1/2 top-1/2 h-[160vmax] w-[160vmax] -translate-x-1/2 -translate-y-1/2 opacity-[.18]"
          style={{ background: "conic-gradient(from 0deg, #D96868, #F2F2F2, #91AE6E, #689D4B, #F2F2F2, #D96868)" }}
          animate={{ rotate: 360 }}
          transition={{ duration: 60, repeat: Infinity, ease: "linear" }}
        />
      )}
      <div className="grain absolute inset-0" />
      {/* signing-space grid, faint */}
      <svg className="absolute inset-0 h-full w-full opacity-[.07]">
        <defs>
          <pattern id="grid" width="56" height="56" patternUnits="userSpaceOnUse">
            <path d="M56 0H0V56" fill="none" stroke="#1F2421" strokeWidth="1" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#grid)" />
      </svg>
    </div>
  );
}

function FloatingHands({ reduced }) {
  const items = useMemo(() => Array.from({ length: 16 }, (_, i) => ({
    e: HANDS[i % HANDS.length], left: (i * 61) % 100, size: 18 + ((i * 37) % 34), dur: 16 + ((i * 13) % 14), delay: -((i * 7) % 20), rot: ((i * 47) % 60) - 30,
  })), []);
  if (reduced) return null;
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
      {items.map((h, i) => (
        <motion.span
          key={i}
          className="absolute bottom-[-10vh] select-none opacity-25 grayscale-[30%]"
          style={{ left: `${h.left}%`, fontSize: h.size }}
          animate={{ y: ["0vh", "-125vh"], rotate: [h.rot, -h.rot] }}
          transition={{ duration: h.dur, delay: h.delay, repeat: Infinity, ease: "linear" }}
        >
          {h.e}
        </motion.span>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ word stages */
const glyph = "inline-block font-extrabold leading-none tracking-[-0.055em]";
const WORD_SIZE = "text-[clamp(3.2rem,15vw,11.5rem)]";

function TypedWord({ phase, typed }) {
  // phase 0: "synopsis" typed · phase 1: "syn" struck and replaced by "sign"
  const old = [..."syn"].map((c, i) => ({ k: `o${i}`, c, kind: "old" }));
  const neu = [..."sign"].map((c, i) => ({ k: `n${i}`, c, kind: "new" }));
  const tail = [..."opsis"].map((c, i) => ({ k: `t${i}`, c, kind: "tail" }));
  const letters = phase === 0 ? [...old, ...tail].slice(0, typed) : [...neu, ...tail];
  return (
    <div className={cx("relative flex items-end justify-center", WORD_SIZE)} aria-hidden="true">
      <AnimatePresence mode="popLayout" initial={false}>
        {letters.map((l, i) => (
          <motion.span
            key={l.k}
            layout
            className={cx(glyph, l.kind === "new" ? "text-moss" : "text-ink")}
            initial={l.kind === "new" ? { y: "-120%", opacity: 0, rotate: -12 } : { opacity: 0, y: 12 }}
            animate={{ y: 0, opacity: 1, rotate: 0 }}
            exit={{ y: "-140%", opacity: 0, rotate: 18, color: "#D96868", transition: { duration: 0.55, delay: (2 - (i % 3)) * 0.06 } }}
            transition={{ type: "spring", stiffness: 260, damping: 18, delay: l.kind === "new" ? 0.35 + i * 0.09 : 0 }}
          >
            {l.c}
          </motion.span>
        ))}
      </AnimatePresence>
      {phase === 0 && (
        <motion.span
          className="mb-[0.12em] ml-1 inline-block h-[0.78em] w-[0.07em] rounded-full bg-coral"
          animate={{ opacity: [1, 0, 1] }}
          transition={{ duration: 0.9, repeat: Infinity }}
        />
      )}
      {phase === 0 && typed >= 8 && (
        <motion.svg
          className="pointer-events-none absolute bottom-[0.28em] left-[calc(50%-2.05em)] h-[0.4em] w-[1.55em]"
          viewBox="0 0 120 30" initial={{ pathLength: 0 }} aria-hidden="true"
        >
          <motion.path d="M4 18 C 30 6, 70 26, 116 12" stroke="#D96868" strokeWidth="7" fill="none" strokeLinecap="round"
            initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ delay: 0.5, duration: 0.5 }} />
        </motion.svg>
      )}
    </div>
  );
}

function Tiles({ phase, reduced }) {
  // phase 2: hands showing · phase >=3: letters showing
  const flipped = phase === 2;
  return (
    <div className={cx("flex items-end justify-center", "text-[clamp(2.6rem,10.5vw,9.5rem)]")} style={{ perspective: "1200px" }} aria-hidden="true">
      {NAME.map((c, i) => (
        <motion.span
          key={i}
          className="relative inline-block w-[0.7em] text-center"
          style={{ transformStyle: "preserve-3d" }}
          initial={reduced ? false : { rotateY: 0, y: 0 }}
          animate={{ rotateY: flipped ? 180 : 360, y: flipped ? [0, -18, 0] : 0 }}
          transition={{ duration: reduced ? 0 : 0.8, delay: reduced ? 0 : i * 0.07, ease: [0.6, 0, 0.2, 1], y: { duration: 0.9, delay: i * 0.07 + 0.4, repeat: flipped ? Infinity : 0, repeatDelay: 0.4 } }}
        >
          <span
            className={cx(glyph, "block bg-[length:400%_100%] bg-clip-text text-transparent")}
            style={{
              backfaceVisibility: "hidden",
              backgroundImage: "linear-gradient(100deg,#1F2421 0%,#689D4B 22%,#D96868 44%,#1F2421 60%,#91AE6E 80%,#1F2421 100%)",
              animation: reduced ? undefined : "sgn-shimmer 7s ease-in-out infinite",
              backgroundPosition: `${i * 9}% 50%`,
            }}
          >
            {c}
          </span>
          <span
            className="absolute inset-0 grid place-items-center"
            style={{ backfaceVisibility: "hidden", transform: "rotateY(180deg)" }}
          >
            <span className="grid aspect-square w-[0.66em] place-items-center rounded-[0.18em] bg-white/85 text-[0.46em] shadow-[0_0.08em_0.25em_rgba(31,36,33,.18)] ring-1 ring-ink/10">
              {HANDS[i]}
            </span>
          </span>
        </motion.span>
      ))}
    </div>
  );
}

const DEFS = [
  { word: "syn·op·sis", ipa: "/sɪˈnɒp.sɪs/", def: "a brief summary of something." },
  { word: "sign·op·sis", ipa: "/saɪˈnɒp.sɪs/", def: "the whole conversation, signed and spoken, understood at a glance." },
  { word: "S · I · G · N · O · P · S · I · S", ipa: "fingerspelled", def: "every letter is a handshape before it is a word." },
];

/* ------------------------------------------------------------------ page */
export default function Intro({ onEnter }) {
  const reduced = usePrefersReducedMotion();
  const [phase, setPhase] = useState(reduced ? 4 : 0);
  const [typed, setTyped] = useState(0);
  const [leaving, setLeaving] = useState(null);
  const [run, setRun] = useState(0);
  const enterBtn = useRef(null);

  const mx = useMotionValue(-999), my = useMotionValue(-999);
  const sx = useSpring(mx, { stiffness: 120, damping: 20 }), sy = useSpring(my, { stiffness: 120, damping: 20 });
  const glow = useTransform([sx, sy], ([x, y]) => `radial-gradient(420px circle at ${x}px ${y}px, rgba(255,255,255,.55), transparent 60%)`);

  useEffect(() => {
    if (reduced) { setPhase(4); setTyped(8); return undefined; }
    setPhase(0); setTyped(0);
    const timers = TIMELINE.slice(1).map((t, i) => setTimeout(() => setPhase(i + 1), t));
    let n = 0;
    const typer = setInterval(() => { n += 1; setTyped(n); if (n >= 8) clearInterval(typer); }, 150);
    return () => { timers.forEach(clearTimeout); clearInterval(typer); };
  }, [reduced, run]);

  useEffect(() => { if (phase === 4) enterBtn.current?.focus({ preventScroll: true }); }, [phase]);

  const enter = useCallback((x, y) => {
    if (leaving) return;
    setLeaving({ x: x ?? window.innerWidth / 2, y: y ?? window.innerHeight / 2 });
    setTimeout(onEnter, reduced ? 0 : 750);
  }, [leaving, onEnter, reduced]);

  useEffect(() => {
    const k = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); enter(); } };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [enter]);

  const def = DEFS[phase === 0 ? 0 : phase === 1 ? 1 : phase === 2 ? 2 : 1];

  return (
    <main
      className="relative flex min-h-[100svh] cursor-pointer flex-col overflow-hidden text-ink"
      onClick={e => enter(e.clientX, e.clientY)}
      onPointerMove={e => { mx.set(e.clientX); my.set(e.clientY); }}
      aria-label="SIGNOPSIS intro. Press Enter or click anywhere to continue."
    >
      <style>{"@keyframes sgn-shimmer{0%,100%{background-position:0% 50%}50%{background-position:100% 50%}}"}</style>
      <Backdrop reduced={reduced} />
      <FloatingHands reduced={reduced} />
      {!reduced && <motion.div className="pointer-events-none absolute inset-0" style={{ background: glow }} aria-hidden="true" />}

      <header className="relative z-10 flex items-center justify-between px-5 pt-5 sm:px-8 sm:pt-7">
        <span className="flex items-center gap-2.5">
          <LogoMark size={40} />
          <span className="hidden font-mono text-[11px] font-semibold uppercase tracking-[.25em] text-ink/60 sm:inline">sign ⇄ speech interpreter</span>
        </span>
        <button
          type="button"
          onClick={e => { e.stopPropagation(); setRun(r => r + 1); }}
          className="btn-ghost min-h-11 cursor-pointer px-4 text-sm"
          aria-label="Replay the intro animation"
        >
          <RotateCcw className="h-4 w-4" aria-hidden="true" /> Replay
        </button>
      </header>

      <section className="relative z-10 flex flex-1 flex-col items-center justify-center px-4 text-center">
        <h1 className="sr-only">SIGNOPSIS</h1>
        <motion.p
          key={`eyebrow-${phase > 1}`}
          initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
          className="mb-4 rounded-full border border-ink/15 bg-white/60 px-4 py-1.5 font-mono text-[11px] font-semibold uppercase tracking-[.3em] text-ink/70 backdrop-blur"
        >
          {phase < 2 ? "a word, rewritten" : phase === 2 ? "spelled in hands" : "introducing"}
        </motion.p>

        <div className="relative flex min-h-[1.1em] w-full items-center justify-center text-[clamp(3.2rem,15vw,11.5rem)]">
          <AnimatePresence mode="wait">
            {phase < 2 ? (
              <motion.div key="typed" exit={{ opacity: 0, scale: 0.94, filter: "blur(8px)" }} transition={{ duration: 0.35 }}>
                <TypedWord phase={phase} typed={typed} />
              </motion.div>
            ) : (
              <motion.div key="tiles" initial={{ opacity: 0, scale: 1.04 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.4 }}>
                <Tiles phase={phase} reduced={reduced} />
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <AnimatePresence mode="wait">
          <motion.div
            key={def.word}
            initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.4 }}
            className="mt-6 max-w-xl"
          >
            <p className="font-mono text-sm text-ink/70">
              <b className="text-ink">{def.word}</b> <span className="text-ink/50">{def.ipa}</span> <i className="text-coral">noun.</i>
            </p>
            <p className="mt-1 text-lg font-medium text-ink/80 sm:text-xl">{def.def}</p>
          </motion.div>
        </AnimatePresence>

        <motion.div
          initial={false}
          animate={phase >= 4 ? { opacity: 1, y: 0 } : { opacity: 0, y: 24 }}
          transition={{ type: "spring", stiffness: 140, damping: 18 }}
          className={cx("mt-10 flex flex-col items-center gap-4", phase < 4 && "pointer-events-none")}
          aria-hidden={phase < 4}
        >
          <p className="max-w-lg text-balance text-2xl font-bold tracking-tight sm:text-3xl">
            Sign and speech, both ways, <span className="relative inline-block">
              without the guesswork.
              <svg className="absolute -bottom-2 left-0 h-3 w-full" viewBox="0 0 200 12" preserveAspectRatio="none" aria-hidden="true">
                <motion.path d="M2 8 C 60 2, 120 11, 198 5" stroke="#D96868" strokeWidth="4" fill="none" strokeLinecap="round"
                  initial={{ pathLength: 0 }} animate={{ pathLength: phase >= 4 ? 1 : 0 }} transition={{ delay: 0.3, duration: 0.7 }} />
              </svg>
            </span>
          </p>
          <button
            ref={enterBtn}
            type="button"
            onClick={e => { e.stopPropagation(); enter(e.clientX, e.clientY); }}
            className="group relative mt-2 inline-flex min-h-14 cursor-pointer items-center gap-3 rounded-full bg-ink py-2 pl-7 pr-2 text-lg font-bold text-light shadow-(--shadow-lift)"
            tabIndex={phase >= 4 ? 0 : -1}
          >
            {!reduced && <span className="absolute inset-1 -z-10 animate-ping rounded-full bg-coral/30 [animation-duration:2.6s]" aria-hidden="true" />}
            Enter SIGNOPSIS
            <span className="grid h-11 w-11 place-items-center rounded-full bg-coral transition-transform group-hover:translate-x-1">
              <ArrowRight className="h-5 w-5" aria-hidden="true" />
            </span>
          </button>
        </motion.div>
      </section>

      <footer className="relative z-10 flex items-center justify-between px-5 pb-6 font-mono text-[11px] font-semibold uppercase tracking-[.22em] text-ink/55 sm:px-8">
        <span>click anywhere · or press enter</span>
        <span className="hidden sm:inline">ISL · English · हिन्दी · Hinglish</span>
      </footer>

      {/* exit wipe */}
      <AnimatePresence>
        {leaving && (
          <motion.div
            className="fixed inset-0 z-50 bg-ink"
            initial={{ clipPath: `circle(0px at ${leaving.x}px ${leaving.y}px)` }}
            animate={{ clipPath: `circle(150vmax at ${leaving.x}px ${leaving.y}px)` }}
            transition={{ duration: 0.75, ease: [0.7, 0, 0.3, 1] }}
            aria-hidden="true"
          >
            <div className="grid h-full place-items-center">
              <motion.span initial={{ opacity: 0, scale: 0.6 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.25 }} className="text-6xl">🤟</motion.span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </main>
  );
}
