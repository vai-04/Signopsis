import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Search, X, Hand, Trash2, Box, Type } from "lucide-react";
import V from "../mocks/vocab.json";
import { PageHeader } from "../components/PageHeader.jsx";
import { MiniSigner } from "../components/MiniSigner.jsx";
import { AvatarStage } from "../components/AvatarStage.jsx";
import { PlayerControls } from "../components/PlayerControls.jsx";
import { Segmented } from "../components/Bits.jsx";
import { usePlayer } from "../hooks/usePlayer.js";
import { backend } from "../services/backend.js";
import { config } from "../config.js";
import { cx } from "../utils/cx.js";

const CAT_LABEL = { PRON: "People", NOUN: "Things & places", TIME: "Time", WH: "Questions", NEG: "Yes / no", AFFIRM: "Yes / no", VERB: "Actions", ADJ: "Feelings", PHRASE: "Social", ASPECT: "Time" };
const clipCache = new Map();

function useClip(gloss, enabled) {
  const [clip, setClip] = useState(() => clipCache.get(gloss) || null);
  useEffect(() => {
    if (!enabled || clip) return;
    let alive = true;
    backend.sign(gloss).then(c => { clipCache.set(gloss, c); if (alive) setClip(c); }).catch(() => {});
    return () => { alive = false; };
  }, [gloss, enabled, clip]);
  return clip;
}

function SignCard({ g, onOpen }) {
  const ref = useRef(null);
  const [seen, setSeen] = useState(false);
  const [hover, setHover] = useState(false);
  useEffect(() => {
    const io = new IntersectionObserver(([e]) => e.isIntersecting && setSeen(true), { rootMargin: "200px" });
    io.observe(ref.current);
    return () => io.disconnect();
  }, []);
  const clip = useClip(g, seen);
  const cat = CAT_LABEL[V.CATEGORY[g]] || "Other";
  return (
    <motion.button layout ref={ref} type="button" onClick={() => onOpen(g)}
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)} onFocus={() => setHover(true)} onBlur={() => setHover(false)}
      className="group flex flex-col overflow-hidden rounded-3xl bg-white text-left shadow-(--shadow-card) transition hover:-translate-y-1 hover:shadow-(--shadow-lift)">
      <span aria-hidden="true" className="relative block aspect-square bg-gradient-to-b from-sage-soft to-sage/50">
        {seen && <MiniSigner clip={clip} animate={hover} className="absolute inset-0" />}
      </span>
      <span className="flex items-center justify-between gap-2 p-3">
        <span className="min-w-0">
          <span className="block truncate font-mono text-sm font-extrabold">{g}</span>
          <span className="text-[11px] font-semibold text-mute">{cat}</span>
        </span>
        <Box className="h-4 w-4 shrink-0 text-mute transition group-hover:text-coral-deep" aria-hidden="true" />
      </span>
    </motion.button>
  );
}

function Viewer({ gloss, onClose }) {
  const [player, snap] = usePlayer();
  const [view, setView] = useState("front");
  useEffect(() => {
    if (!gloss) return undefined;
    let alive = true;
    const c = clipCache.get(gloss);
    const go = clip => alive && player.load(clip, { autoplay: true, meta: { gloss: [gloss] } });
    if (c) go(c); else backend.sign(gloss).then(x => { clipCache.set(gloss, x); go(x); }).catch(() => {});
    player.setLoop(true);
    const k = e => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => { alive = false; window.removeEventListener("keydown", k); };
  }, [gloss, player, onClose]);
  return (
    <AnimatePresence>
      {gloss && (
        <motion.div className="fixed inset-0 z-[85] grid place-items-center bg-ink/50 p-3 backdrop-blur-sm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
          <motion.div role="dialog" aria-modal="true" aria-label={`Sign ${gloss}`} onClick={e => e.stopPropagation()}
            initial={{ scale: 0.94, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.96, y: 10 }}
            className="w-full max-w-2xl rounded-[2rem] bg-light p-4 shadow-(--shadow-lift) sm:p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="eyebrow">{CAT_LABEL[V.CATEGORY[gloss]] || "Sign"}</p>
                <h2 className="font-mono text-3xl font-extrabold">{gloss}</h2>
              </div>
              <button className="btn-icon" onClick={onClose} aria-label="Close"><X className="h-5 w-5" /></button>
            </div>
            <AvatarStage player={player} view={view} className="mt-3 h-[min(56vh,460px)] rounded-3xl" />
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Segmented label="Camera" value={view} onChange={setView} options={[{ value: "front", label: "Front" }, { value: "three", label: "¾" }, { value: "hands", label: "Hands" }, { value: "side", label: "Side" }]} />
            </div>
            <PlayerControls player={player} snap={snap} className="mt-2" />
            <p className="mt-2 text-xs text-mute">Placeholder motion from the prototype lexicon. Real ISL recordings replace these without UI changes.</p>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/** S12 Library: every sign the avatar knows, fingerspelling, and your own signs. */
export default function Library() {
  const [lex, setLex] = useState(null);
  const [mine, setMine] = useState([]);
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("all");
  const [open, setOpen] = useState(null);
  const close = useCallback(() => setOpen(null), []);

  useEffect(() => {
    backend.lexicon().then(setLex).catch(() => setLex({ signs: [], vocab_without_sign: [] }));
    backend.userSigns().then(r => setMine(r.signs || [])).catch(() => {});
  }, []);

  const cats = ["all", ...new Set(Object.values(CAT_LABEL))];
  const list = useMemo(() => (lex?.signs || []).filter(g =>
    (cat === "all" || CAT_LABEL[V.CATEGORY[g]] === cat) && g.toLowerCase().includes(q.trim().toLowerCase())), [lex, q, cat]);

  return (
    <div className="mx-auto max-w-7xl px-4 pb-10 sm:px-6">
      <PageHeader n="S12" eyebrow="Library" title="Every sign it knows, and the ones you taught it."
        lead={lex ? `${lex.signs.length} signs in the lexicon · ${lex.vocab_without_sign.length} more ${lex.vocab_without_sign.length === 1 ? "word is" : "words are"} fingerspelled · hover a card to play it.` : "Loading the lexicon…"} />

      <div className="sticky top-[72px] z-20 -mx-4 flex flex-wrap items-center gap-3 bg-light/90 px-4 py-3 backdrop-blur sm:-mx-6 sm:px-6">
        <label className="relative min-w-60 flex-1">
          <span className="sr-only">Search signs</span>
          <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-mute" aria-hidden="true" />
          <input className="field pl-10" placeholder="Search: water, doctor, thank…" value={q} onChange={e => setQ(e.target.value)} />
        </label>
        <div className="no-scrollbar flex gap-1.5 overflow-x-auto">
          {cats.map(c => (
            <button key={c} className={cx("chip shrink-0", cat === c && "border-ink bg-ink text-light hover:text-light")} aria-pressed={cat === c} onClick={() => setCat(c)}>
              {c === "all" ? "All" : c}
            </button>
          ))}
        </div>
      </div>

      <section aria-label="Your signs" className="mt-6">
        <h2 className="flex items-center gap-2 text-xl font-extrabold"><Hand className="h-5 w-5 text-moss" aria-hidden="true" /> Your signs <span className="text-sm font-semibold text-mute">({config.user})</span></h2>
        {mine.length === 0 ? (
          <p className="mt-2 text-mute">None yet. <a className="font-bold text-ink underline underline-offset-4" href="#/enroll">Teach one →</a></p>
        ) : (
          <ul className="mt-3 flex flex-wrap gap-2">
            {mine.map(s => (
              <li key={s.label} className="flex items-center gap-2 rounded-full bg-sage-soft py-1 pl-4 pr-1 font-bold text-moss-deep">
                {s.display || s.label} <span className="text-xs font-semibold text-moss">{s.samples} samples</span>
                <button className="grid h-10 w-10 place-items-center rounded-full hover:bg-white" aria-label={`Forget ${s.display || s.label}`}
                  onClick={async () => { await backend.forgetSign(s.label); setMine(m => m.filter(x => x.label !== s.label)); }}>
                  <Trash2 className="h-4 w-4" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <motion.div layout className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
        {!lex && Array.from({ length: 12 }, (_, i) => <div key={i} className="aspect-[4/5] animate-pulse rounded-3xl bg-white" />)}
        {list.map(g => <SignCard key={g} g={g} onOpen={setOpen} />)}
      </motion.div>
      {lex && list.length === 0 && <p className="mt-8 text-center text-mute">No sign matches “{q}”. It would be fingerspelled.</p>}

      {lex?.vocab_without_sign?.length > 0 && (
        <section className="mt-12">
          <h2 className="flex items-center gap-2 text-xl font-extrabold"><Type className="h-5 w-5 text-coral-deep" aria-hidden="true" /> Known words without a sign yet</h2>
          <p className="mt-1 text-mute">These are understood, then fingerspelled letter by letter.</p>
          <ul className="mt-3 flex flex-wrap gap-2">
            {lex.vocab_without_sign.map(w => <li key={w} className="gloss-token border-dashed">{w}</li>)}
          </ul>
        </section>
      )}
      <Viewer gloss={open} onClose={close} />
    </div>
  );
}
