import { useCallback, useEffect, useRef, useState } from "react";
import { useSignLangs } from "../hooks/useSignLangs.js";
import { AnimatePresence, motion } from "framer-motion";
import {
  Mic, MicOff, Play, Square, Maximize2, Minimize2, PanelRightClose, PanelRightOpen, Radio, Languages, Keyboard, Send, Gauge, Sparkles, AlertTriangle,
} from "lucide-react";
import { AvatarStage } from "../components/AvatarStage.jsx";
import { CaptionStack } from "../components/CaptionStack.jsx";
import { RepairCard } from "../components/RepairCard.jsx";
import { TrustBadge } from "../components/TrustBadge.jsx";
import { GlossStrip } from "../components/GlossStrip.jsx";
import { Segmented, Toast, ModeBadge } from "../components/Bits.jsx";
import { useConsent } from "../components/ConsentSheet.jsx";
import { usePlayer } from "../hooks/usePlayer.js";
import { useSpeechInput } from "../hooks/useSpeechInput.js";
import { backend } from "../services/backend.js";
import { composeFromResponse, glossLabel } from "../services/adapters.js";
import { detectLanguage, SPOKEN_LANGS, RESOLVER_LANGS, langLabel } from "../services/speech.js";
import { cx } from "../utils/cx.js";

const SCRIPT = [
  { text: "Good morning, welcome to school.", who: "Principal" },
  { text: "Namaste, aap kaise ho?", who: "Principal" },
  { text: "मुझे पानी चाहिए", who: "Guest" },
  { text: "main kal ghar gaya tha", who: "Guest" },
  { text: "Please help me, I need a doctor.", who: "Guest" },
  { text: "mujhe kal bank jaana hai", who: "Guest" },
  { text: "வணக்கம் எல்லோருக்கும்", who: "Guest" },
  { text: "Thank you! See you tomorrow.", who: "Principal" },
];
const DETECT_SHOW = ["en", "hi", "hi-en", "ta", "bn", "mr", "es"];
const sleep = ms => new Promise(r => setTimeout(r, ms));

function LangRadar({ detected, forced }) {
  return (
    <div className="flex flex-wrap gap-1.5" aria-live="polite" aria-label={detected ? `Detected ${langLabel(detected.code)}` : "Listening for language"}>
      {DETECT_SHOW.map(code => {
        const on = detected?.code === code;
        return (
          <motion.span key={code} layout
            className={cx("relative inline-flex min-h-8 items-center rounded-full px-3 text-xs font-bold transition-colors",
              on ? "bg-sage text-ink" : "bg-white/8 text-light/70")}>
            {on && !forced && <motion.span layoutId="radar" className="absolute inset-0 rounded-full ring-2 ring-sage" transition={{ type: "spring", stiffness: 300, damping: 26 }} />}
            {on && <span className="mr-1" aria-hidden="true">●</span>}
            {langLabel(code)}
          </motion.span>
        );
      })}
    </div>
  );
}

/**
 * S07 Live stage: a person speaks, the avatar signs it for the room, live.
 * Spoken language is detected per sentence; the operator picks the sign language.
 */
export default function LiveStage() {
  const [player, snap] = usePlayer();
  const SIGN_LANGS = useSignLangs();
  const [spokenLang, setSpokenLang] = useState("auto");
  const [signLang, setSignLang] = useState("isl");
  const [policy, setPolicy] = useState("ask");
  const [items, setItems] = useState([]);
  const [pending, setPending] = useState(null);
  const [detected, setDetected] = useState(null);
  const [panel, setPanel] = useState(true);
  const [full, setFull] = useState(false);
  const [scripted, setScripted] = useState(false);
  const [interim, setInterim] = useState("");
  const [typed, setTyped] = useState("");
  const [toast, setToast] = useState(null);
  const [speed, setSpeed] = useState(1);
  const root = useRef(null);
  const stopScript = useRef(false);
  const consent = useConsent();
  const opts = useRef({});
  opts.current = { spokenLang, signLang, policy };

  const handle = useCallback(async (text, who = "Speaker", resolutions, replaceId) => {
    const { spokenLang: sl, signLang: sg, policy: pol } = opts.current;
    const lang = sl === "auto" ? detectLanguage(text) : { code: sl, label: langLabel(sl), sure: true };
    setDetected(lang);
    const t0 = performance.now();
    let res;
    try {
      res = await backend.textToSign({ text, src_lang: lang.code, sign_lang: sg, resolutions: resolutions || {} });
    } catch (e) { setToast(e.message); return; }
    const vm = composeFromResponse(res, text);
    const supported = RESOLVER_LANGS.has(lang.code);
    const card = {
      id: vm.id, speaker: who, speakerIndex: who === "Guest" ? 1 : 0, channel: "speech", text,
      state: resolutions ? (vm.gate === "emit" ? "enhanced" : vm.state) : vm.state,
      reason: supported ? vm.reason : `${lang.label} isn't in the resolver yet.`, advisory: vm.advisory, gloss: vm.gloss,
      lang: lang.label, signLang: SIGN_LANGS.find(s => s.code === sg)?.label, at: Date.now(), repair: vm.repair,
      ms: Math.round(performance.now() - t0),
    };
    if (!supported && vm.gate !== "emit") {
      card.state = "hold";
      card.repair = { type: "resign", slot: -1, token_index: -1, prompt: `${lang.label} detected. Captions only until a ${lang.label} resolver pack is installed.`, options: [] };
    }
    setItems(list => [...list.filter(x => x.id !== replaceId), card].slice(-60));
    if (vm.gate === "emit") {
      player.enqueue(vm.clip, { text, gloss: vm.gloss, lang: lang.label });
      return;
    }
    if (vm.repair?.type === "disambiguate") {
      if (pol === "auto") {
        const pick = vm.repair.options[0];
        handle(text, who, { [vm.repair.token_index]: pick.gloss }, card.id);
      } else {
        setPending({ vm, card, who });
      }
      return;
    }
    if (vm.repair?.type === "confirm") {
      // live: fingerspelling-heavy lines are signed anyway but marked "checking"
      player.enqueue(vm.clip, { text, gloss: vm.gloss, lang: lang.label });
    }
  }, [player]);

  const speech = useSpeechInput({
    lang: spokenLang,
    onUtterance: ({ text }) => handle(text, "Speaker"),
  });
  useEffect(() => { if (speech.detected && spokenLang === "auto") setDetected(speech.detected); }, [speech.detected, spokenLang]);
  useEffect(() => { setInterim(speech.interim); }, [speech.interim]);
  useEffect(() => { player.setSpeed(speed); }, [speed, player]);

  const waitForSigner = async () => {
    for (let i = 0; i < 400; i++) {
      const s = player.snapshot();
      if (!s.playing && s.queued === 0) return;
      await sleep(100);
    }
  };

  const playScript = async () => {
    if (scripted) { stopScript.current = true; return; }
    stopScript.current = false;
    setScripted(true);
    for (const line of SCRIPT) {
      if (stopScript.current) break;
      // the words arrive as they're "spoken"
      const words = line.text.split(" ");
      for (let i = 1; i <= words.length; i++) {
        if (stopScript.current) break;
        setInterim(words.slice(0, i).join(" "));
        setDetected(detectLanguage(words.slice(0, i).join(" ")));
        await sleep(170);
      }
      setInterim("");
      if (stopScript.current) break;
      await handle(line.text, line.who);
      await sleep(400);
      await waitForSigner();
      await sleep(700);
    }
    setScripted(false);
  };
  useEffect(() => () => { stopScript.current = true; }, []);

  const toggleMic = async () => {
    if (speech.listening) return speech.stop();
    if (!speech.supported) { setToast("This browser has no speech recognition. Use the demo speech or type instead."); return; }
    if (await consent.ask("mic")) speech.start();
  };

  const toggleFull = async () => {
    try {
      if (!document.fullscreenElement) { await root.current?.requestFullscreen(); setFull(true); setPanel(false); }
      else { await document.exitFullscreen(); setFull(false); setPanel(true); }
    } catch { setFull(f => !f); }
  };
  useEffect(() => {
    const on = () => { if (!document.fullscreenElement) { setFull(false); } };
    document.addEventListener("fullscreenchange", on);
    const key = e => {
      if (e.target.closest?.("input,textarea,select")) return;
      if (e.key === "h" || e.key === "H") setPanel(p => !p);
      if (e.key === "f" || e.key === "F") toggleFull();
    };
    window.addEventListener("keydown", key);
    return () => { document.removeEventListener("fullscreenchange", on); window.removeEventListener("keydown", key); };
  }); // eslint-disable-line react-hooks/exhaustive-deps

  const current = snap.meta;
  const last = items[items.length - 1];
  const sl = SIGN_LANGS.find(s => s.code === signLang);
  const listening = speech.listening || scripted;

  return (
    <div ref={root} className={cx("relative bg-ink text-light", full ? "h-screen" : "min-h-[calc(100svh-72px)]")}>
      <h1 className="sr-only">Live stage</h1>
      <div className={cx("mx-auto grid h-full max-w-[1600px] gap-4 p-3 sm:p-4", panel ? "lg:grid-cols-[minmax(0,1fr)_400px]" : "grid-cols-1")}>
        {/* stage */}
        <div className="flex min-h-0 flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className={cx("inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-extrabold uppercase tracking-widest",
              listening ? "bg-coral text-ink" : "bg-white/10 text-light/70")}>
              <span className={cx("h-2 w-2 rounded-full", listening ? "animate-pulse bg-ink" : "bg-light/40")} />
              {listening ? "Live" : "Standby"}
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1.5 text-xs font-bold">
              <Languages className="h-3.5 w-3.5" aria-hidden="true" /> {detected ? langLabel(detected.code) : "Auto-detect"} → {sl.label}
            </span>
            <div className="ml-auto flex items-center gap-2">
              <button className="btn-icon bg-white/10 text-light hover:bg-white/20" onClick={toggleFull} aria-label={full ? "Exit presenter mode" : "Presenter mode (F)"}>
                {full ? <Minimize2 className="h-5 w-5" /> : <Maximize2 className="h-5 w-5" />}
              </button>
              <button className="btn-icon bg-white/10 text-light hover:bg-white/20" onClick={() => setPanel(p => !p)} aria-label={panel ? "Hide controls (H)" : "Show controls (H)"} aria-pressed={panel}>
                {panel ? <PanelRightClose className="h-5 w-5" /> : <PanelRightOpen className="h-5 w-5" />}
              </button>
            </div>
          </div>

          <AvatarStage player={player} background="sage" className={cx("relative rounded-[2rem]", full ? "h-[calc(100vh-15rem)]" : "h-[min(64vh,720px)] min-h-[360px]")}>
            <div className="pointer-events-none absolute left-4 top-4 flex flex-col items-start gap-2">
              <span className="rounded-full bg-ink/80 px-3 py-1 text-xs font-extrabold uppercase tracking-widest text-light">{sl.name}</span>
              {sl.status !== "ready" && <span className="rounded-full bg-coral px-3 py-1 text-[11px] font-bold text-ink">{sl.label} pack not installed · ISL motions</span>}
            </div>
            <AnimatePresence>
              {snap.playing && current?.gloss?.[snap.gi] && (
                <motion.div key={`${snap.t > 0}-${snap.gi}-${current.text}`} initial={{ y: 10, opacity: 0, scale: 0.9 }} animate={{ y: 0, opacity: 1, scale: 1 }} exit={{ opacity: 0 }}
                  className="pointer-events-none absolute right-4 top-4 rounded-2xl bg-ink px-4 py-2 font-mono text-3xl font-extrabold text-light shadow-xl sm:text-4xl">
                  {glossLabel(current.gloss[snap.gi])}
                </motion.div>
              )}
            </AnimatePresence>
            {snap.ch && snap.playing && <span className="pointer-events-none absolute right-6 top-24 font-mono text-7xl font-extrabold text-white drop-shadow-[0_4px_10px_rgba(0,0,0,.4)]">{snap.ch}</span>}
            {snap.queued > 0 && <span className="absolute bottom-4 right-4 rounded-full bg-ink/80 px-3 py-1 text-xs font-bold">+{snap.queued} waiting</span>}
          </AvatarStage>

          {/* audience caption */}
          <div className="relative min-h-[7.5rem] overflow-hidden rounded-[1.6rem] bg-white/6 px-5 py-4" aria-live="polite">
            <p className="text-xs font-bold uppercase tracking-widest text-light/70">{interim ? "hearing…" : current?.text ? "signing now" : "caption"}</p>
            <AnimatePresence mode="wait">
              <motion.p key={interim ? "interim" : current?.text || "none"} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}
                className={cx("mt-1 font-extrabold leading-tight tracking-tight", full ? "text-4xl sm:text-6xl" : "text-3xl sm:text-5xl", interim && "text-light/60")}>
                {interim || current?.text || <span className="text-light/70">Waiting for the speaker…</span>}
              </motion.p>
            </AnimatePresence>
            {current?.gloss && !interim && <GlossStrip items={current.gloss} active={snap.playing ? snap.gi : -1} size="sm" className="mt-3 [&_.gloss-token]:border-light/40 [&_.gloss-token]:bg-white/5 [&_.gloss-token]:text-light" />}
          </div>
        </div>

        {/* operator panel */}
        <AnimatePresence>
          {panel && (
            <motion.aside initial={{ opacity: 0, x: 30 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 30 }}
              className="flex min-h-0 flex-col gap-3 lg:max-h-[calc(100svh-104px)] lg:overflow-y-auto" aria-label="Operator controls">
              <section className="rounded-[1.6rem] bg-white/6 p-4">
                <p className="eyebrow text-light/70">Speaker input</p>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <button onClick={toggleMic} aria-pressed={speech.listening}
                    className={cx("btn min-h-14", speech.listening ? "bg-coral text-ink" : "bg-light text-ink")}>
                    {speech.listening ? <MicOff className="h-5 w-5" aria-hidden="true" /> : <Mic className="h-5 w-5" aria-hidden="true" />}
                    {speech.listening ? "Stop mic" : "Live mic"}
                  </button>
                  <button onClick={playScript} aria-pressed={scripted}
                    className={cx("btn min-h-14", scripted ? "bg-sage text-ink" : "bg-white/10 text-light hover:bg-white/20")}>
                    {scripted ? <Square className="h-5 w-5" aria-hidden="true" /> : <Play className="h-5 w-5" aria-hidden="true" />}
                    {scripted ? "Stop demo" : "Demo speech"}
                  </button>
                </div>
                <form className="mt-2 flex gap-2" onSubmit={e => { e.preventDefault(); if (typed.trim()) { handle(typed.trim(), "Speaker"); setTyped(""); } }}>
                  <label htmlFor="live-type" className="sr-only">Type a line</label>
                  <div className="relative flex-1">
                    <Keyboard className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-light/65" aria-hidden="true" />
                    <input id="live-type" value={typed} onChange={e => setTyped(e.target.value)} placeholder="…or type a line"
                      className="min-h-12 w-full rounded-2xl border-2 border-white/10 bg-white/5 pl-9 pr-3 text-light placeholder:text-light/65 focus:border-sage focus:outline-none" />
                  </div>
                  <button className="btn-icon bg-sage text-ink" aria-label="Sign this line"><Send className="h-4 w-4" /></button>
                </form>
                {speech.error && <p className="mt-2 text-xs text-coral">{speech.error}</p>}
              </section>

              <section className="rounded-[1.6rem] bg-white/6 p-4">
                <div className="flex items-center justify-between">
                  <p className="eyebrow text-light/70">Spoken language</p>
                  <label className="sr-only" htmlFor="spoken-lang">Spoken language</label>
                  <select id="spoken-lang" value={spokenLang} onChange={e => setSpokenLang(e.target.value)}
                    className="min-h-10 rounded-full border-2 border-white/10 bg-ink px-3 text-xs font-bold text-light">
                    {SPOKEN_LANGS.map(l => <option key={l.code} value={l.code}>{l.label}</option>)}
                  </select>
                </div>
                <div className="mt-3"><LangRadar detected={detected} forced={spokenLang !== "auto"} /></div>
                <p className="mt-2 flex items-center gap-1.5 text-[11px] text-light/70">
                  <Radio className="h-3 w-3" aria-hidden="true" />{spokenLang === "auto" ? "Detected per sentence, from script and vocabulary." : "Fixed by the operator."}
                </p>
              </section>

              <section className="rounded-[1.6rem] bg-white/6 p-4">
                <p className="eyebrow text-light/70">Sign language for the room</p>
                <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3" role="radiogroup" aria-label="Output sign language">
                  {SIGN_LANGS.map(s => (
                    <button key={s.code} role="radio" aria-checked={signLang === s.code} onClick={() => setSignLang(s.code)}
                      className={cx("flex min-h-16 flex-col items-start justify-center rounded-2xl border-2 px-3 text-left transition",
                        signLang === s.code ? "border-sage bg-sage text-ink" : "border-white/10 hover:border-white/30")}>
                      <span className="font-mono text-base font-extrabold">{s.label}</span>
                      <span className={cx("text-[10px] font-bold uppercase", signLang === s.code ? "text-ink" : "text-light/65")}>{s.status === "ready" ? "ready" : "needs pack"}</span>
                    </button>
                  ))}
                </div>
              </section>

              <section className="rounded-[1.6rem] bg-white/6 p-4">
                <p className="eyebrow text-light/70">When something is unclear</p>
                <Segmented className="mt-3 bg-white/10 [&_button]:text-light/70" label="Unclear policy" value={policy} onChange={setPolicy}
                  options={[{ value: "ask", label: "Ask me" }, { value: "auto", label: "Pick the likelier one" }]} />
                <div className="mt-3 flex items-center gap-2">
                  <Gauge className="h-4 w-4 text-light/70" aria-hidden="true" />
                  <label htmlFor="live-speed" className="text-xs font-bold text-light/60">Signing speed</label>
                  <input id="live-speed" type="range" min={0.5} max={1.5} step={0.25} value={speed} onChange={e => setSpeed(+e.target.value)} className="flex-1 accent-[#91AE6E]" />
                  <span className="w-10 text-right text-xs font-bold">{speed}×</span>
                </div>
              </section>

              <AnimatePresence>
                {pending && (
                  <div className="text-ink">
                    <RepairCard key={pending.card.id} repair={pending.vm.repair} reason={pending.vm.reason} hotkeys autoFocus={false}
                      onAnswer={o => { const p = pending; setPending(null); if (o.gloss !== "__none__") handle(p.card.text, p.who, { [p.vm.repair.token_index]: o.gloss }, p.card.id); }}
                      onDismiss={() => setPending(null)} />
                  </div>
                )}
              </AnimatePresence>

              <section className="rounded-[1.6rem] bg-light p-3 text-ink">
                <div className="flex items-center justify-between px-1">
                  <p className="eyebrow">Transcript</p>
                  {last && <TrustBadge state={last.state} size="sm" />}
                </div>
                <CaptionStack items={items} className="mt-2 max-h-[340px]" emptyHint="Press “Demo speech” to hear a multilingual welcome." />
              </section>
              <div className="flex items-center justify-between px-1 text-[11px] text-light/65">
                <span className="flex items-center gap-1"><Sparkles className="h-3 w-3" aria-hidden="true" /> H hides controls · F presenter mode</span>
                <ModeBadge className="border-white/15 bg-white/5 text-light" />
              </div>
              {signLang !== "isl" && (
                <p className="flex items-start gap-2 rounded-2xl bg-coral/15 p-3 text-xs text-light/80">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-coral" aria-hidden="true" />
                  The request carries <code className="font-mono">sign_lang: "{signLang}"</code>. The v1 server signs ISL only; installing a {sl.label} lexicon pack makes this real without UI changes.
                </p>
              )}
            </motion.aside>
          )}
        </AnimatePresence>
      </div>
      {consent.sheet}
      <Toast message={toast} onClose={() => setToast(null)} />
    </div>
  );
}
