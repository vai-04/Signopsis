import { useEffect, useMemo, useRef, useState } from "react";
import { useSignLangs } from "../hooks/useSignLangs.js";
import { AnimatePresence, motion } from "framer-motion";
import { Eye, Hand, Languages, Loader2, RotateCcw, Sparkles, Undo2, AlertTriangle, Mic, Check } from "lucide-react";
import { AvatarStage, VIEWS } from "./AvatarStage.jsx";
import { GlossStrip } from "./GlossStrip.jsx";
import { RepairCard, humanReason } from "./RepairCard.jsx";
import { TrustBadge } from "./TrustBadge.jsx";
import { PlayerControls } from "./PlayerControls.jsx";
import { Segmented, Toast } from "./Bits.jsx";
import { useTextToSign } from "../hooks/useTextToSign.js";
import { usePlayer } from "../hooks/usePlayer.js";
import { useSpeechInput } from "../hooks/useSpeechInput.js";
import { detectLanguage, RESOLVER_LANGS } from "../services/speech.js";
import { glossLabel } from "../services/adapters.js";
import { cx } from "../utils/cx.js";

export const COMPOSE_EXAMPLES = [
  "Your appointment is moved to Thursday at 4.",
  "I went to the bank yesterday.",
  "Please help me, I need a doctor.",
  "mujhe kal bank jaana hai",
  "मुझे पानी चाहिए",
  "Hello, my name is Priya. What is your name?",
  "I don't understand.",
];

/**
 * S03 Compose (pipeline D): write it, preview the signing and its read-back, then sign it.
 * "Preview" translates without committing; "Sign it" plays and adds to the sent list.
 */
export function ComposeScreen({ variant = "page", initialText = COMPOSE_EXAMPLES[0] }) {
  const embed = variant === "embed";
  const [text, setText] = useState(initialText);
  const [signLang, setSignLang] = useState("isl");
  const [view, setView] = useState("front");
  const [sent, setSent] = useState([]);
  const [toast, setToast] = useState(null);
  const [mode, setMode] = useState("idle");       // idle | preview | signed
  const { result, loading, error, translate, answerRepair } = useTextToSign();
  const [player, snap] = usePlayer();
  const SIGN_LANGS = useSignLangs();
  const input = useRef(null);
  const lang = useMemo(() => detectLanguage(text), [text]);
  const speech = useSpeechInput({ lang: "auto", onUtterance: ({ text: t }) => setText(prev => (prev ? `${prev} ${t}` : t)) });

  const modeRef = useRef(mode);
  modeRef.current = mode;
  const run = async (how) => {
    setMode(how);
    modeRef.current = how;
    const r = await translate(text, { sign_lang: signLang, src_lang: lang.code });
    if (r && how === "signed" && r.gate === "emit") {
      setSent(s => [{ id: r.id, text: r.text, state: r.state, gloss: r.gloss, at: Date.now() }, ...s].slice(0, 6));
    }
  };

  // first preview on mount so the screen is never empty
  useEffect(() => { run("preview"); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // every new plan (including ones produced by answering a repair) is loaded into the player;
  // only cleared plans auto-play
  useEffect(() => {
    if (!result?.clip) return;
    player.load(result.clip, { autoplay: result.gate === "emit", meta: { gloss: result.gloss } });
  }, [result?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // "Send as shown" / "Let me rephrase"
  useEffect(() => {
    if (result?.rephrase) input.current?.focus();
    if (result?.confirmed) {
      player.play();
      setSent(s => [{ id: result.id, text: result.text, state: result.state, gloss: result.gloss, at: Date.now() }, ...s].slice(0, 6));
    }
  }, [result?.rephrase, result?.confirmed]); // eslint-disable-line react-hooks/exhaustive-deps

  const sl = SIGN_LANGS.find(s => s.code === signLang);
  const unsupported = !RESOLVER_LANGS.has(lang.code);

  return (
    <div className={cx("grid grid-cols-1 gap-4 [&>*]:min-w-0", embed ? "lg:grid-cols-[1fr_1.05fr]" : "lg:grid-cols-[1fr_1.15fr]")}>
      {/* author side */}
      <div className="flex flex-col gap-4">
        <div className="card relative overflow-hidden p-4 sm:p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <label htmlFor={`compose-${variant}`} className="eyebrow">Write it</label>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-light px-2.5 py-1 text-xs font-bold text-ink-soft" aria-live="polite">
              <Languages className="h-3.5 w-3.5" aria-hidden="true" /> {text.trim() ? `Detected: ${lang.label}` : "Language: auto"}
            </span>
          </div>
          <textarea
            id={`compose-${variant}`}
            ref={input}
            value={text}
            onChange={e => { setText(e.target.value); setMode("idle"); }}
            onKeyDown={e => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) run("signed"); }}
            rows={embed ? 3 : 4}
            maxLength={500}
            className="paper-lines mt-2 w-full resize-none rounded-2xl bg-transparent text-2xl font-bold leading-[2.2rem] tracking-tight text-ink outline-none placeholder:text-mute sm:text-[1.7rem]"
            placeholder="Type what you want signed…"
          />
          {unsupported && text.trim() && (
            <p className="mt-2 flex items-center gap-1.5 text-xs font-semibold text-coral-deep">
              <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" /> {lang.label} isn't in the resolver yet; unknown words will be fingerspelled or held.
            </p>
          )}
          <div className="no-scrollbar -mx-1 mt-3 flex gap-1.5 overflow-x-auto px-1 pb-1">
            {COMPOSE_EXAMPLES.map(ex => (
              <button key={ex} type="button" className={cx("chip shrink-0", ex === text && "border-ink bg-ink text-light hover:text-light")}
                onClick={() => { setText(ex); setMode("idle"); }}>{ex}</button>
            ))}
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <button type="button" className="btn-ghost" onClick={() => run("preview")} disabled={loading || !text.trim()}>
              {loading && mode !== "signed" ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Eye className="h-4 w-4" aria-hidden="true" />} Preview
            </button>
            <button type="button" className="btn-coral" onClick={() => run("signed")} disabled={loading || !text.trim()}>
              <Hand className="h-4 w-4" aria-hidden="true" /> Sign it
            </button>
            {speech.supported && (
              <button type="button" className={cx("btn-icon", speech.listening ? "bg-coral text-ink" : "bg-light")} aria-pressed={speech.listening}
                onClick={() => (speech.listening ? speech.stop() : speech.start())} aria-label="Dictate">
                <Mic className="h-5 w-5" />
              </button>
            )}
            <span className="ml-auto hidden text-xs text-mute sm:inline">Ctrl + Enter signs it</span>
          </div>
        </div>

        <div className="card p-4 sm:p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="eyebrow">Sign language</p>
            {sl.status !== "ready" && <span className="text-[11px] font-bold text-coral-deep">Pack not installed: ISL motions shown</span>}
          </div>
          <Segmented className="mt-2" label="Sign language" value={signLang} onChange={setSignLang}
            options={SIGN_LANGS.map(s => ({ value: s.code, label: s.label }))} />
        </div>

        <AnimatePresence mode="wait">
          {error && (
            <motion.p key="err" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="rounded-2xl bg-coral-soft p-4 font-semibold text-ink" role="alert">{error}</motion.p>
          )}
          {result?.repair && (
            <RepairCard key={result.id} repair={result.repair} reason={result.reason} compact={embed} autoFocus={!embed} hotkeys={!embed}
              onAnswer={o => answerRepair(result.repair, o)} />
          )}
        </AnimatePresence>

        {!embed && sent.length > 0 && (
          <div className="card p-4">
            <p className="eyebrow">Signed this session</p>
            <ul className="mt-2 divide-y divide-ink/5">
              {sent.map(s => (
                <li key={s.id + s.at} className="flex items-center gap-3 py-2">
                  <Check className="h-4 w-4 text-moss" aria-hidden="true" />
                  <span className="min-w-0 flex-1 truncate font-semibold">{s.text}</span>
                  <button className="btn-icon" aria-label={`Sign again: ${s.text}`} onClick={() => { setText(s.text); run("signed"); }}><RotateCcw className="h-4 w-4" /></button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* signer side */}
      <div className="flex flex-col gap-3">
        <AvatarStage player={player} view={view} background="sage" className={cx("rounded-[1.8rem]", embed ? "h-[360px]" : "h-[min(62vh,560px)] min-h-[380px]")}>
          <div className="absolute left-3 top-3 flex flex-wrap gap-1.5">
            {result && <TrustBadge state={result.state} />}
            <span className="rounded-full bg-white/85 px-2.5 py-1 text-[11px] font-bold uppercase text-ink">{mode === "signed" ? "Signing" : "Preview"} · {sl.label}</span>
          </div>
          <AnimatePresence>
            {snap.playing && result?.gloss?.[snap.gi] && (
              <motion.span key={snap.gi} initial={{ y: 8, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ opacity: 0 }}
                className="absolute bottom-4 left-1/2 -translate-x-1/2 rounded-2xl bg-ink px-4 py-2 font-mono text-2xl font-extrabold text-light shadow-lg">
                {glossLabel(result.gloss[snap.gi])}
              </motion.span>
            )}
          </AnimatePresence>
          {snap.ch && snap.playing && <span className="absolute right-5 top-4 font-mono text-6xl font-extrabold text-white drop-shadow-[0_3px_8px_rgba(0,0,0,.35)]">{snap.ch}</span>}
          <div className="absolute right-3 top-3 hidden flex-col gap-1 sm:flex">
            {Object.entries(VIEWS).map(([k, v]) => (
              <button key={k} type="button" onClick={() => setView(k)} aria-pressed={view === k}
                className={cx("min-h-10 min-w-12 rounded-xl px-2 text-xs font-bold backdrop-blur", view === k ? "bg-ink text-light" : "bg-white/70 text-ink hover:bg-white")}>{v.label}</button>
            ))}
          </div>
        </AvatarStage>
        <PlayerControls player={player} snap={snap} />
        <div className="card p-4 sm:p-5">
          <div className="flex items-center justify-between gap-2">
            <p className="eyebrow">ISL gloss · tap a sign to replay it</p>
            {result && <span className="text-xs font-semibold text-mute">{result.gloss.length} signs · {(result.totalMs / 1000).toFixed(1)} s</span>}
          </div>
          {loading && !result ? (
            <div className="mt-3 flex gap-2">{[1, 2, 3, 4].map(i => <span key={i} className="h-8 w-20 animate-pulse rounded-xl bg-light" />)}</div>
          ) : (
            <GlossStrip items={result?.gloss || []} active={snap.playing ? snap.gi : -1} onPick={i => player.seekToGloss(i)} size="lg" className="mt-3" showCertainty={!embed} />
          )}
          {result && (
            <div className="mt-4 grid gap-3 border-t border-ink/5 pt-4 sm:grid-cols-2">
              <div>
                <p className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-mute"><Undo2 className="h-3.5 w-3.5" aria-hidden="true" /> Reads back as</p>
                <p className="mt-1 text-lg font-bold">{result.backTranslation || "—"}</p>
              </div>
              <div>
                <p className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-mute"><Sparkles className="h-3.5 w-3.5" aria-hidden="true" /> Round-trip check</p>
                <p className="mt-1 text-lg font-bold capitalize">{result.readbackWord}{result.confirmed ? " · you confirmed" : ""}</p>
                {!embed && <p className="text-xs text-mute">{humanReason(result.reason)}</p>}
              </div>
              {result.advisory && (
                <p className="flex items-start gap-2 rounded-xl bg-coral-soft p-3 text-sm font-semibold sm:col-span-2">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-coral-deep" aria-hidden="true" />{result.advisory}
                </p>
              )}
            </div>
          )}
        </div>
      </div>
      <Toast message={toast} onClose={() => setToast(null)} />
    </div>
  );
}
