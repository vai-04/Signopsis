import { useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ListChecks, MousePointerClick, ScanEye, Send, ShoppingBasket, Volume2, Lock, Loader2, Hand } from "lucide-react";
import { MiniSigner } from "./MiniSigner.jsx";
import { GlossStrip } from "./GlossStrip.jsx";
import { backend } from "../services/backend.js";
import { snapshotDom } from "../services/screen.js";
import { speak } from "../services/speech.js";
import { cx } from "../utils/cx.js";

const ITEMS = [
  { id: "it-kurta", name: "Cotton kurta", qty: 1, price: 1299, emoji: "👕" },
  { id: "it-bottle", name: "Steel water bottle", qty: 1, price: 549, emoji: "🧴" },
  { id: "it-notebook", name: "Notebook pack", qty: 2, price: 316, emoji: "📓" },
];
const TOTAL = ITEMS.reduce((a, i) => a + i.qty * i.price, 0);
const ACTIONS = [
  { intent: "items", label: "Read items", Icon: ListChecks, q: "Read me the items." },
  { intent: "checkout", label: "Go to checkout", Icon: MousePointerClick, q: "Where do I check out?" },
  { intent: "overview", label: "What's on screen?", Icon: ScanEye, q: "What's happening on this page?" },
];

/** A fictional shop page to describe. data-screen-* attributes are what the snapshot reads. */
function DemoShop({ highlight }) {
  const hl = id => highlight.includes(id);
  return (
    <div data-screen-kind="cart" className="relative flex h-full flex-col bg-white text-[13px] text-ink">
      <div className="flex items-center justify-between border-b border-ink/10 px-4 py-3">
        <span className="flex items-center gap-2 font-extrabold"><ShoppingBasket className="h-4 w-4 text-coral-deep" aria-hidden="true" /> tokri<span className="text-coral-deep">.</span></span>
        <span className="text-xs text-mute">Fictional demo store</span>
      </div>
      <div className="flex-1 space-y-2 overflow-hidden p-4">
        <h4 data-screen-title className="text-lg font-extrabold">Your cart</h4>
        {ITEMS.map(i => (
          <div key={i.id} id={i.id} data-screen-item data-name={i.name} data-qty={i.qty} data-price={i.price}
            className={cx("flex items-center gap-3 rounded-xl border p-2 transition-all duration-300", hl(i.id) ? "border-coral bg-coral-soft ring-4 ring-coral/30" : "border-ink/10")}>
            <span className="grid h-10 w-10 place-items-center rounded-lg bg-light text-xl" aria-hidden="true">{i.emoji}</span>
            <span className="flex-1 font-semibold">{i.name}<span className="block text-xs font-normal text-mute">Qty {i.qty}</span></span>
            <span className="font-bold">₹{(i.qty * i.price).toLocaleString("en-IN")}</span>
          </div>
        ))}
        <div className="flex items-center gap-2 rounded-xl bg-light p-2 text-xs text-mute" data-private>
          <Lock className="h-3.5 w-3.5" aria-hidden="true" /> Saved card ending •••• (never read aloud)
        </div>
      </div>
      <div className="flex items-center justify-between border-t border-ink/10 px-4 py-3">
        <span data-screen-total={TOTAL} className="font-extrabold">Total ₹{TOTAL.toLocaleString("en-IN")}</span>
        <button type="button" id="btn-checkout" data-screen-action data-primary tabIndex={-1}
          className={cx("rounded-full bg-moss px-4 py-2 font-bold text-ink transition-all", hl("btn-checkout") && "ring-4 ring-coral ring-offset-2 animate-pulse")}>
          Checkout
        </button>
      </div>
    </div>
  );
}

export function BrowserFrame({ url = "tokri.example/cart", children, className = "" }) {
  return (
    <div className={cx("overflow-hidden rounded-[1.4rem] border border-ink/10 bg-white shadow-(--shadow-lift)", className)}>
      <div className="flex items-center gap-2 border-b border-ink/10 bg-light px-3 py-2">
        <span className="flex gap-1.5" aria-hidden="true">
          <span className="h-3 w-3 rounded-full bg-coral" /><span className="h-3 w-3 rounded-full bg-sage" /><span className="h-3 w-3 rounded-full bg-moss" />
        </span>
        <span className="mx-auto max-w-[70%] truncate rounded-full bg-white px-4 py-1 font-mono text-[11px] text-mute">{url}</span>
      </div>
      {children}
    </div>
  );
}

/** S15 Screen Glance (pipeline E): ask about the page you're on; get a short answer in sign, text and voice. */
export function ScreenGlance({ variant = "page" }) {
  const embed = variant === "embed";
  const page = useRef(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState(null);
  const [busy, setBusy] = useState(false);
  const [clip, setClip] = useState(null);

  const ask = async (q, intent) => {
    const text = (q || question).trim() || "What's happening on this page?";
    setBusy(true);
    setQuestion("");
    try {
      const snap = snapshotDom(page.current);
      const r = await backend.describeScreen({ question: text, intent, snapshot: snap });
      setAnswer({ ...r, question: text });
      speak({ text: r.answer, lang: "en", rate: 1 }, { muted: embed });
      // sign the first sentence (short answers sign better than long ones)
      const first = r.answer.split(/(?<=\.)\s/)[0];
      const t2s = await backend.textToSign({ text: first, src_lang: "en" });
      setClip(t2s.frames);
      setAnswer(a => ({ ...a, gloss: t2s.plan.targets.find(t => t.kind === "sign")?.gloss || [] }));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={cx("grid grid-cols-1 gap-4 [&>*]:min-w-0", embed ? "md:grid-cols-2" : "lg:grid-cols-[1.1fr_1fr]")}>
      <BrowserFrame className={embed ? "h-[420px]" : "h-[520px]"}>
        <div ref={page} className="h-[calc(100%-45px)]">
          <DemoShop highlight={answer?.targets?.map(t => t.id) || []} />
        </div>
      </BrowserFrame>

      <div className="flex flex-col gap-3">
        <form className="card flex items-center gap-2 p-2 pl-4" onSubmit={e => { e.preventDefault(); ask(); }}>
          <ScanEye className="h-5 w-5 shrink-0 text-moss" aria-hidden="true" />
          <label className="sr-only" htmlFor={`glance-q-${variant}`}>Ask about this screen</label>
          <input id={`glance-q-${variant}`} value={question} onChange={e => setQuestion(e.target.value)}
            placeholder="What's happening on this page?" className="min-h-12 w-full bg-transparent text-base font-semibold outline-none placeholder:text-mute" />
          <button className="btn-primary shrink-0" disabled={busy} aria-label="Ask">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}</button>
        </form>

        <div className="grid grid-cols-3 gap-2">
          {ACTIONS.map(a => (
            <button key={a.intent} type="button" onClick={() => ask(a.q, a.intent)} disabled={busy}
              className="group flex min-h-24 flex-col items-start justify-between rounded-2xl bg-white p-3 text-left shadow-(--shadow-card) transition hover:-translate-y-0.5 hover:bg-ink hover:text-light disabled:opacity-50">
              <a.Icon className="h-5 w-5 text-coral-deep" aria-hidden="true" />
              <span className="text-sm font-extrabold leading-tight">{a.label}</span>
            </button>
          ))}
        </div>

        <AnimatePresence mode="wait">
          {answer ? (
            <motion.div key={answer.answer} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
              className="card grid flex-1 gap-3 overflow-hidden p-4 sm:grid-cols-[1fr_150px]" aria-live="polite">
              <div className="min-w-0">
                <p className="text-xs font-bold text-mute">“{answer.question}”</p>
                <p className="mt-2 text-2xl font-extrabold leading-tight">{answer.answer}</p>
                {answer.gloss?.length > 0 && <GlossStrip items={answer.gloss} size="sm" className="mt-3" />}
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <button className="btn-ghost min-h-11 px-3 text-sm" onClick={() => speak({ text: answer.answer, lang: "en" })}><Volume2 className="h-4 w-4" aria-hidden="true" /> Read aloud</button>
                  <span className="text-[11px] font-semibold text-mute">{answer.source === "local" || answer.source === "mock" ? "Read from the page structure on this device" : "Described by the server"}</span>
                </div>
              </div>
              <div className="relative hidden aspect-[3/4] overflow-hidden rounded-2xl bg-gradient-to-b from-sage-soft to-sage/70 sm:block">
                <MiniSigner clip={clip} loop label="Signer answering" className="absolute inset-0" />
                <span className="absolute left-2 top-2 inline-flex items-center gap-1 rounded-full bg-white/85 px-2 py-0.5 text-[10px] font-bold uppercase"><Hand className="h-3 w-3" aria-hidden="true" /> signing</span>
              </div>
            </motion.div>
          ) : (
            <motion.div key="empty" className="card grid flex-1 place-items-center p-6 text-center">
              <div>
                <p className="text-4xl" aria-hidden="true">👀</p>
                <p className="mt-2 text-lg font-bold">Ask what's on screen.</p>
                <p className="mt-1 text-sm text-mute">Answers stay short, give positions, and never press anything for you.</p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
