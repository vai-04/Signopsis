import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowRight, Camera, Mic, Monitor, Cpu, ShieldCheck, Languages, Hand, MessageSquareText, RefreshCcw, Brain, Presentation, Server, Plug, Check,
} from "lucide-react";
import { SectionTag, Scribble } from "../Brand.jsx";
import { TrustBadge, TrustBar } from "../TrustBadge.jsx";
import { GlossStrip } from "../GlossStrip.jsx";
import { SpeakerDot } from "../Bits.jsx";
import { LazyMount, Reveal } from "../LazyMount.jsx";
import { BrowserFrame } from "../ScreenGlance.jsx";
import { ConverseScreen } from "../ConverseScreen.jsx";
import { ComposeScreen } from "../ComposeScreen.jsx";
import { EnrollmentScreen } from "../EnrollmentScreen.jsx";
import { ScreenGlance } from "../ScreenGlance.jsx";
import { Diagnostics } from "../Diagnostics.jsx";
import { TRUST } from "../../services/adapters.js";
import { useBackend } from "../../hooks/useBackend.js";
import { cx } from "../../utils/cx.js";

const wrap = "mx-auto max-w-7xl px-4 sm:px-6";

function Heading({ n, tag, title, lead, tone, children }) {
  return (
    <Reveal className="max-w-3xl">
      <SectionTag n={n} tone={tone}>{tag}</SectionTag>
      <h2 className={cx("mt-4 text-[clamp(2.2rem,5vw,4rem)] font-extrabold leading-[0.98]", tone === "light" && "text-light")}>{title}</h2>
      {lead && <p className={cx("mt-4 text-lg", tone === "light" ? "text-light/70" : "text-ink-soft")}>{lead}</p>}
      {children}
    </Reveal>
  );
}

/* ------------------------------------------------------------------ marquee */
const TICKER = ["HELLO", "MY", "NAME", "P-R-I-Y-A", "WHERE", "HOSPITAL", "THANK-YOU", "TOMORROW", "ME", "UNDERSTAND", "NOT", "WATER", "WANT", "YOU", "HOW", "WELCOME", "SCHOOL", "HELP", "DOCTOR", "NEED"];
export function Marquee() {
  const row = [...TICKER, ...TICKER];
  return (
    <div className="relative -rotate-1 overflow-hidden bg-ink py-4 text-light" aria-hidden="true">
      <div className="flex w-max gap-3 [animation:marquee-x_45s_linear_infinite] motion-reduce:[animation:none]">
        {row.map((g, i) => (
          <span key={i} className={cx("rounded-xl border-2 px-3 py-1 font-mono text-sm font-extrabold tracking-wider",
            g.includes("-") && g.length > 5 && !g.includes("YOU") ? "border-dashed border-sage text-sage" : i % 7 === 3 ? "border-coral text-coral" : "border-light/25")}>
            {g}
          </span>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ why */
export function Why() {
  const cards = [
    { Icon: ShieldCheck, t: "It shows how sure it is", d: "Every caption carries a word: Clear, Enhanced, Checking or Held. Never a mystery percentage.", tone: "bg-moss text-ink" },
    { Icon: MessageSquareText, t: "It asks instead of guessing", d: "Two signs look alike? One quick tap settles it, and the answer is remembered for next time.", tone: "bg-coral text-ink" },
    { Icon: Hand, t: "It learns your signs", d: "Name signs, local variants, work words. Four takes, no retraining, yours alone.", tone: "bg-sage text-ink" },
  ];
  return (
    <section id="how" className={cx(wrap, "scroll-mt-24 py-20 sm:py-28")}>
      <Heading n="01" tag="Why SIGNOPSIS" title={<>A wrong caption is worse than <span className="relative inline-block">no caption<Scribble /></span>.</>}
        lead="Most translators always answer. SIGNOPSIS answers when the evidence is good, and turns the rest into a question or an honest pause." />
      <div className="mt-12 grid gap-4 md:grid-cols-3">
        {cards.map((c, i) => (
          <Reveal key={c.t} delay={i * 0.1} className={cx("group relative overflow-hidden rounded-[2rem] p-7 transition-transform hover:-translate-y-1", i === 1 && "md:translate-y-8", c.tone)}>
            <c.Icon className="h-9 w-9" aria-hidden="true" />
            <h3 className="mt-10 text-3xl font-extrabold leading-tight">{c.t}</h3>
            <p className="mt-3 text-[17px] opacity-85">{c.d}</p>
            <span className="absolute -bottom-6 -right-2 font-mono text-[7rem] font-extrabold leading-none opacity-10" aria-hidden="true">0{i + 1}</span>
          </Reveal>
        ))}
      </div>
      <Reveal className="mt-20 grid items-center gap-8 rounded-[2rem] bg-white p-6 shadow-(--shadow-card) sm:p-10 lg:grid-cols-[1fr_1.3fr]">
        <div>
          <p className="eyebrow">Measured on the simulator · 200 phrases · 6 camera conditions</p>
          <p className="mt-3 text-3xl font-extrabold leading-tight">Shown signs that were wrong: <span className="text-moss">about 1 in 45</span>, instead of 1 in 9.</p>
          <p className="mt-3 text-ink-soft">The difference became questions (23% of sentences) and honest holds (20%). In studio conditions, everything was shown and nothing was wrong.</p>
        </div>
        <div className="space-y-5">
          {[
            { k: "If it always guessed", v: 10.6, c: "bg-coral" },
            { k: "SIGNOPSIS, showing only what it trusts", v: 2.2, c: "bg-moss" },
          ].map((r, i) => (
            <div key={r.k}>
              <div className="flex justify-between text-sm font-bold"><span>{r.k}</span><span className="tabular-nums">{r.v}% wrong</span></div>
              <div className="mt-2 h-8 overflow-hidden rounded-xl bg-light">
                <motion.div className={cx("h-full rounded-xl", r.c, i === 0 && "hatch")} initial={{ width: 0 }} whileInView={{ width: `${r.v * 8}%` }}
                  viewport={{ once: true }} transition={{ duration: 1, delay: i * 0.2 }} />
              </div>
            </div>
          ))}
          <p className="text-xs text-mute">Placeholder sign motions; real-camera accuracy depends on the recorded lexicon. Details in Diagnostics.</p>
        </div>
      </Reveal>
    </section>
  );
}

/* ------------------------------------------------------------------ layers */
const LAYERS = [
  { id: "L0", Icon: Camera, name: "Capture", what: "Camera, mic and screen become points and text on your device.", io: "WireFrame → WS /ws/sign", ui: "CameraStage · ConsentSheet" },
  { id: "L1", Icon: Cpu, name: "Perceive", what: "Hands, body and face become a lattice of candidate signs.", io: "PerceptEvent", ui: "live HUD · partial gloss" },
  { id: "L2", Icon: ShieldCheck, name: "Trust", what: "Each slot is scored and gated: show, ask, or hold.", io: "gate: emit | repair | hold", ui: "TrustBar · TrustBadge" },
  { id: "L3", Icon: Brain, name: "Resolve", what: "Grammar, context and your own signs turn signs into meaning.", io: "SemanticFrame", ui: "CaptionStack · GlossStrip" },
  { id: "L4", Icon: Languages, name: "Render", what: "Captions, voice and the signing avatar, checked by reading its own signing back.", io: "RenderPlan · POST /api/text-to-sign", ui: "AvatarStage · Compose · Live stage" },
  { id: "L5", Icon: RefreshCcw, name: "Repair & memory", what: "Questions, teaching and remembered answers close the loop.", io: "repair_choice · enroll_* · /api/users/{u}/signs", ui: "RepairCard · Enrollment · Library" },
];
export function Layers() {
  const [on, setOn] = useState(2);
  const L = LAYERS[on];
  return (
    <section className="bg-ink py-20 text-light sm:py-28">
      <div className={wrap}>
        <Heading tone="light" n="02" tag="Six layers" title="From a raised eyebrow to a spoken sentence."
          lead="Every screen in this app maps to a layer of the SIGNOPSIS backend, and every arrow is a typed contract." />
        <div className="mt-12 grid gap-6 lg:grid-cols-[1.2fr_1fr]">
          <div className="grid gap-2" role="tablist" aria-label="Layers">
            {LAYERS.map((l, i) => (
                <button key={l.id} role="tab" aria-selected={on === i} onClick={() => setOn(i)} onMouseEnter={() => setOn(i)}
                  className={cx("flex min-h-16 w-full items-center gap-4 rounded-2xl border-2 px-4 text-left transition",
                    on === i ? "border-sage bg-sage text-ink" : "border-white/10 hover:border-white/30")}>
                  <span className="font-mono text-xs font-bold">{l.id}</span>
                  <l.Icon className="h-5 w-5" aria-hidden="true" />
                  <span className="text-xl font-extrabold">{l.name}</span>
                  <span className={cx("ml-auto hidden truncate text-sm sm:block", on === i ? "text-ink" : "text-light/65")}>{l.what.split(" ").slice(0, 5).join(" ")}…</span>
                </button>
            ))}
          </div>
          <AnimatePresence mode="wait">
            <motion.div key={L.id} role="tabpanel" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -10 }}
              className="relative overflow-hidden rounded-[2rem] bg-white/6 p-7">
              <span data-watermark={L.id} className="absolute -right-4 -top-8 font-mono text-[9rem] font-extrabold leading-none text-white/5" aria-hidden="true" />
              <L.Icon className="h-10 w-10 text-coral-deep" aria-hidden="true" />
              <h3 className="mt-6 text-4xl font-extrabold">{L.name}</h3>
              <p className="mt-3 text-lg text-light/80">{L.what}</p>
              <dl className="mt-8 space-y-4">
                <div><dt className="eyebrow text-sage">Contract</dt><dd className="mt-1 font-mono text-sm">{L.io}</dd></div>
                <div><dt className="eyebrow text-sage">In this app</dt><dd className="mt-1 font-mono text-sm">{L.ui}</dd></div>
              </dl>
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ interactive demo */
export function TryIt() {
  return (
    <section className={cx(wrap, "py-20 sm:py-28")}>
      <div className="flex flex-wrap items-end justify-between gap-6">
        <Heading n="03" tag="Try it here" title="A conversation, both directions."
          lead="Play Priya's signing (including the look-alike signs), or type as Dr. Rao and watch the avatar answer. Everything below is the real app." />
        <a href="#/converse" className="btn-primary">Open full screen <ArrowRight className="h-4 w-4" aria-hidden="true" /></a>
      </div>
      <Reveal className="mt-10">
        <BrowserFrame url="signopsis.app/converse" className="bg-light">
          <LazyMount minHeight={760}>
            <div className="h-[860px] md:h-[760px]"><ConverseScreen variant="embed" /></div>
          </LazyMount>
        </BrowserFrame>
      </Reveal>
    </section>
  );
}

/* ------------------------------------------------------------------ live teaser */
const LANGS = ["English", "हिन्दी", "Hinglish", "தமிழ்", "Español"];
export function LiveTeaser() {
  const [k, setK] = useState(0);
  useEffect(() => { const t = setInterval(() => setK(x => (x + 1) % LANGS.length), 1400); return () => clearInterval(t); }, []);
  return (
    <section className="relative overflow-hidden bg-coral py-20 text-ink sm:py-24">
      <div aria-hidden="true" className="dots absolute inset-0 opacity-30" />
      <div className={cx(wrap, "relative grid items-center gap-10 lg:grid-cols-2")}>
        <div>
          <SectionTag n="04">Live stage</SectionTag>
          <h2 className="mt-4 text-[clamp(2.4rem,5.5vw,4.5rem)] font-extrabold leading-[0.95]">Someone speaks. The whole room sees it signed.</h2>
          <p className="mt-4 max-w-lg text-lg text-ink/85">Auto-detects the spoken language every sentence, and lets the operator choose the sign language for the audience. Presenter mode hides everything but the signer and the captions.</p>
          <a href="#/live" className="btn mt-8 min-h-14 bg-ink px-7 text-lg text-light hover:bg-white hover:text-ink"><Presentation className="h-5 w-5" aria-hidden="true" /> Open the live stage</a>
        </div>
        <div className="rounded-[2rem] bg-ink p-6 shadow-2xl">
          <p className="eyebrow text-light/70">Hearing</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {LANGS.map((l, i) => (
              <span key={l} className={cx("rounded-full px-3 py-1.5 text-sm font-bold transition-all", i === k ? "scale-110 bg-sage text-ink" : "bg-white/10 text-light/70")}>{l}</span>
            ))}
          </div>
          <div className="my-6 flex items-center gap-3 text-light/65" aria-hidden="true">
            <span className="h-px flex-1 bg-white/15" /><Mic className="h-4 w-4" /><ArrowRight className="h-4 w-4" /><Hand className="h-4 w-4" /><span className="h-px flex-1 bg-white/15" />
          </div>
          <p className="eyebrow text-light/70">Signing in</p>
          <div className="mt-2 grid grid-cols-5 gap-2">
            {["ISL", "ASL", "BSL", "Auslan", "LSF"].map((s, i) => (
              <span key={s} className={cx("grid min-h-14 place-items-center rounded-2xl border-2 font-mono text-sm font-extrabold", i === 0 ? "border-sage bg-sage text-ink" : "border-white/10 text-light/60")}>{s}</span>
            ))}
          </div>
          <p className="mt-6 text-3xl font-extrabold text-light">“Good morning, welcome to school.”</p>
          <GlossStrip items={["MORNING", "GOOD", "WELCOME", "SCHOOL"]} size="sm" className="mt-3 [&_.gloss-token]:border-light/40 [&_.gloss-token]:bg-white/5 [&_.gloss-token]:text-light" />
        </div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ trust */
const EXAMPLES = {
  high: { who: "Priya", text: "Yesterday I went to the bank.", gloss: ["YESTERDAY", "ME", "BANK", "GO"], rule: "Every sign is well above the bar, and the whole phrase was covered." },
  enhanced: { who: "Priya", text: "My name is Priya.", gloss: ["MY", "NAME", "PRIYA"], rule: "The name sign was only readable because Priya taught it. Context and memory count, and it says so." },
  repair: { who: "Priya", text: "I go to the river?", gloss: ["ME", "RIVER", "GO"], rule: "RIVER and WATER look almost the same. Rather than pick one, it asks. One tap, remembered next time." },
  hold: { who: "Priya", text: "It's too dark. Add some light and sign it again.", gloss: [], rule: "Too little evidence (dark room, hands out of frame, an unknown sign). Nothing is shown or spoken." },
};
export function TrustSection() {
  const [k, setK] = useState("repair");
  const ex = EXAMPLES[k];
  return (
    <section id="trust" className={cx(wrap, "scroll-mt-24 py-20 sm:py-28")}>
      <Heading n="05" tag="Trust, in four words" title="No percentages. Four states you can read at a glance."
        lead="Each state has a colour, an icon, a word and a pattern, so it still works in greyscale, on a projector, or for colour-blind viewers." />
      <div className="mt-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-4" role="radiogroup" aria-label="Trust states">
        {["high", "enhanced", "repair", "hold"].map(s => (
          <button key={s} role="radio" aria-checked={k === s} onClick={() => setK(s)}
            className={cx("flex min-h-36 flex-col items-start justify-between rounded-[1.6rem] border-2 p-5 text-left transition",
              k === s ? "border-ink bg-white shadow-(--shadow-lift)" : "border-transparent bg-white/60 hover:bg-white")}>
            <TrustBadge state={s} size="lg" />
            <span>
              <span className="block text-lg font-extrabold">{TRUST[s].verb}</span>
              <span className="mt-1 block text-sm text-mute">{TRUST[s].blurb}</span>
            </span>
          </button>
        ))}
      </div>
      <AnimatePresence mode="wait">
        <motion.div key={k} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
          className="mt-6 grid gap-6 rounded-[2rem] bg-white p-6 shadow-(--shadow-card) sm:p-8 lg:grid-cols-[1.2fr_1fr]">
          <div className={cx("rounded-3xl border-2 p-5", k === "repair" ? "border-coral" : k === "hold" ? "border-ink" : "border-transparent bg-light")}>
            <div className="flex items-center gap-2"><SpeakerDot name={ex.who} index={0} channel="sign" /><b>{ex.who}</b><TrustBadge state={k} size="sm" /></div>
            <p className={cx("mt-3 text-3xl font-extrabold leading-tight", k === "repair" && "text-ink/60")}>{ex.text}</p>
            {ex.gloss.length > 0 && <GlossStrip items={ex.gloss} className="mt-3" />}
            <TrustBar state={k} className="mt-5" />
          </div>
          <div className="self-center">
            <p className="eyebrow">Why this state</p>
            <p className="mt-2 text-xl font-semibold leading-relaxed">{ex.rule}</p>
            <p className="mt-4 text-sm text-mute">Medical and legal phrases raise the bar automatically and add a reminder to confirm with a qualified interpreter.</p>
          </div>
        </motion.div>
      </AnimatePresence>
    </section>
  );
}

/* ------------------------------------------------------------------ feature embeds */
export function FeatureBand({ n, tag, title, lead, href, cta, children, tone = "light", id }) {
  return (
    <section id={id} className={cx("scroll-mt-24 py-20 sm:py-24", tone === "sage" && "bg-sage-soft", tone === "white" && "bg-white")}>
      <div className={wrap}>
        <div className="flex flex-wrap items-end justify-between gap-6">
          <Heading n={n} tag={tag} title={title} lead={lead} />
          {href && <a href={href} className="btn-ghost bg-white">{cta} <ArrowRight className="h-4 w-4" aria-hidden="true" /></a>}
        </div>
        <Reveal className="mt-10">{children}</Reveal>
      </div>
    </section>
  );
}

export const ComposeBand = () => (
  <FeatureBand n="06" tag="Compose" title="Write once. Preview the signing. Check its read-back." href="#/compose" cta="Open Compose" tone="sage"
    lead="“Your appointment is moved to Thursday at 4.” Unknown words get fingerspelled, and SIGNOPSIS asks before sending something it can't sign clearly.">
    <LazyMount minHeight={620}><ComposeScreen variant="embed" /></LazyMount>
  </FeatureBand>
);
export const TeachBand = () => (
  <FeatureBand n="07" tag="Teach a sign" title="Sign it once more, the same way." href="#/enroll" cta="Teach a sign"
    lead="Name signs like PRIYA, your town's word for market, your office's word for the server room. Four takes and it's yours.">
    <LazyMount minHeight={520}><EnrollmentScreen variant="embed" /></LazyMount>
  </FeatureBand>
);
export const GlanceBand = () => (
  <FeatureBand n="08" tag="Screen Glance" title="“What's happening on this page?”" href="#/glance" cta="Open Screen Glance" tone="white"
    lead="Cart page. Three items, total ₹2,480. Checkout is a button at the bottom right. Short, ordered, signed and spoken.">
    <LazyMount minHeight={440}><ScreenGlance variant="embed" /></LazyMount>
  </FeatureBand>
);
export const DiagBand = () => (
  <FeatureBand n="09" tag="Diagnostics" title="Calibrated, not just confident." href="#/diagnostics" cta="All diagnostics"
    lead="When SIGNOPSIS says a sign is clear, it's right about as often as it claims. These charts come straight from the backend's evaluation.">
    <LazyMount minHeight={420}><Diagnostics variant="embed" /></LazyMount>
  </FeatureBand>
);

/* ------------------------------------------------------------------ connect */
const ENDPOINTS = [
  ["POST", "/api/text-to-sign", "Compose, Converse, Live stage"],
  ["WS", "/ws/sign", "Converse, Teach a sign"],
  ["GET", "/api/sign/{gloss}", "Repair previews, Library"],
  ["GET", "/api/lexicon", "Library"],
  ["GET", "/api/simcam", "Simulated signer"],
  ["GET·DELETE", "/api/users/{u}/signs", "Library, Teach"],
  ["GET·POST", "/api/mode", "Diagnostics"],
  ["GET", "/api/eval/report", "Diagnostics"],
  ["POST", "/api/screen/describe", "Screen Glance"],
  ["GET", "/healthz", "Connection badge"],
];
export function Connect() {
  const b = useBackend();
  return (
    <section className={cx(wrap, "py-20 sm:py-28")}>
      <div className="grid gap-10 lg:grid-cols-[1fr_1.2fr]">
        <Heading n="10" tag="Plug in the backend" title="Demo today. Live in two commands."
          lead="The app runs on recorded outputs of the real SIGNOPSIS server. Point it at the server and every screen switches over: same contracts, same shapes.">
          <div className="mt-8 flex flex-wrap gap-3">
            <a href="#/settings#backend" className="btn-primary"><Plug className="h-4 w-4" aria-hidden="true" /> Connection settings</a>
            <span className="inline-flex min-h-12 items-center gap-2 rounded-full bg-white px-4 text-sm font-bold">
              <Server className={cx("h-4 w-4", b.resolved === "live" ? "text-moss" : "text-mute")} aria-hidden="true" />
              {b.resolved === "live" ? "Connected to a server" : "Running in demo mode"}
            </span>
          </div>
        </Heading>
        <Reveal className="overflow-hidden rounded-[2rem] bg-white shadow-(--shadow-card)">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Backend endpoints used by the app</caption>
            <thead className="bg-ink text-light">
              <tr><th className="px-4 py-3 font-mono text-xs">Method</th><th className="px-4 py-3 font-mono text-xs">Endpoint</th><th className="px-4 py-3 text-xs">Used by</th><th className="px-4 py-3 text-xs"><span className="sr-only">Ready</span></th></tr>
            </thead>
            <tbody>
              {ENDPOINTS.map(([m, p, u]) => (
                <tr key={p} className="border-t border-ink/5">
                  <td className="px-4 py-2.5 font-mono text-[11px] font-bold text-coral-deep">{m}</td>
                  <td className="px-4 py-2.5 font-mono text-[12.5px] font-bold">{p}</td>
                  <td className="px-4 py-2.5 text-mute">{u}</td>
                  <td className="px-4 py-2.5"><Check className="h-4 w-4 text-moss" aria-label="mocked and wired" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Reveal>
      </div>
    </section>
  );
}

export function FinalCTA() {
  return (
    <section className={cx(wrap, "pb-6")}>
      <Reveal className="grain relative overflow-hidden rounded-[2.5rem] bg-moss px-6 py-16 text-center text-ink sm:px-12 sm:py-24">
        <div aria-hidden="true" className="absolute -left-10 -top-10 text-[10rem] opacity-15">🤟</div>
        <div aria-hidden="true" className="absolute -bottom-12 -right-6 text-[12rem] opacity-15">👋</div>
        <h2 className="relative mx-auto max-w-3xl text-[clamp(2.4rem,6vw,5rem)] font-extrabold leading-[0.95]">Say it your way. Be understood, not guessed at.</h2>
        <div className="relative mt-10 flex flex-wrap justify-center gap-3">
          <a href="#/converse" className="btn min-h-14 bg-ink px-8 text-lg text-light hover:bg-white hover:text-ink">Try SIGNOPSIS <ArrowRight className="h-5 w-5" aria-hidden="true" /></a>
          <a href="#/live" className="btn min-h-14 border-2 border-ink/40 px-8 text-lg hover:bg-white/20"><Presentation className="h-5 w-5" aria-hidden="true" /> Live stage</a>
          <a href="#/glance" className="btn min-h-14 border-2 border-ink/40 px-8 text-lg hover:bg-white/20"><Monitor className="h-5 w-5" aria-hidden="true" /> Screen Glance</a>
        </div>
      </Reveal>
    </section>
  );
}
