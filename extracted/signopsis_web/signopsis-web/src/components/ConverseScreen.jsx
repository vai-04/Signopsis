import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Camera, CameraOff, Mic, MicOff, Hand, Keyboard, FileText, Users, FlipHorizontal2, Send, Volume2, VolumeX,
  GraduationCap, X, Sparkles, Copy, Download, Plus, ChevronDown, Trash2,
} from "lucide-react";
import { AvatarStage } from "./AvatarStage.jsx";
import { CameraStage } from "./CameraStage.jsx";
import { CaptionStack } from "./CaptionStack.jsx";
import { RepairCard } from "./RepairCard.jsx";
import { TrustBar, TrustBadge } from "./TrustBadge.jsx";
import { GlossStrip } from "./GlossStrip.jsx";
import { PipelineChip, SpeakerDot, Toast } from "./Bits.jsx";
import { useConsent } from "./ConsentSheet.jsx";
import { useSignSession } from "../hooks/useSignSession.js";
import { useCamera } from "../hooks/useCamera.js";
import { useSpeechInput } from "../hooks/useSpeechInput.js";
import { usePlayer } from "../hooks/usePlayer.js";
import { backend } from "../services/backend.js";
import { composeFromResponse, glossLabel, TRUST } from "../services/adapters.js";
import { detectLanguage, langLabel } from "../services/speech.js";
import { cx, fmtTime } from "../utils/cx.js";
import { usePrefs } from "../services/prefs.js";

export const SIM_SCRIPTS = [
  { label: "I went to the bank yesterday.", params: { text: "I went to the bank yesterday." }, tag: "clear" },
  { label: "What is your name?", params: { text: "What is your name?" }, tag: "question" },
  { label: "ME · RIVER · GO", params: { gloss: "ME,RIVER,GO" }, tag: "look-alike signs" },
  { label: "MY · NAME · (name sign)", params: { gloss: "MY,NAME,DEMO-NAMESIGN" }, tag: "unknown sign" },
  { label: "I have pain, I need medicine.", params: { text: "I have pain, I need medicine." }, tag: "medical" },
  { label: "Bank, in a dark room", params: { text: "I went to the bank yesterday.", severity: 0.9 }, tag: "too dark" },
];

const HEARING_LINES = ["Hello, my name is Priya. What is your name?", "Where is the hospital?", "Do you want water?", "mujhe kal bank jaana hai", "Thank you! See you tomorrow."];

function DockButton({ on, onClick, Icon, OffIcon, label, hint, tone = "ink", disabled, badge, pressed = true }) {
  const I = on || !OffIcon ? Icon : OffIcon;
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={pressed ? !!on : undefined}
      title={hint || label}
      className={cx(
        "relative flex min-h-14 min-w-14 flex-col items-center justify-center gap-0.5 rounded-2xl px-2.5 text-[10.5px] font-bold uppercase tracking-wide transition sm:min-w-[4.5rem]",
        on ? (tone === "coral" ? "bg-coral text-ink" : tone === "moss" ? "bg-moss text-ink" : "bg-ink text-light") : "bg-white text-ink-soft hover:text-ink hover:shadow-md",
        disabled && "opacity-40",
      )}
    >
      <I className="h-5 w-5" aria-hidden="true" />
      <span>{label}</span>
      {badge != null && badge > 0 && (
        <span className="absolute -right-1 -top-1 grid h-5 min-w-5 place-items-center rounded-full bg-coral px-1 text-[10px] text-ink">{badge}</span>
      )}
    </button>
  );
}

function Sheet({ open, title, onClose, children, wide }) {
  useEffect(() => {
    if (!open) return undefined;
    const k = e => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [open, onClose]);
  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-[85] flex items-end justify-center bg-ink/40 backdrop-blur-sm sm:items-center sm:p-6"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
          <motion.div role="dialog" aria-modal="true" aria-label={title} onClick={e => e.stopPropagation()}
            initial={{ y: 40, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 40, opacity: 0 }}
            className={cx("max-h-[88vh] w-full overflow-y-auto rounded-t-[2rem] bg-light p-5 shadow-(--shadow-lift) sm:rounded-[2rem] sm:p-6", wide ? "max-w-2xl" : "max-w-md")}>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-2xl font-extrabold">{title}</h2>
              <button className="btn-icon" onClick={onClose} aria-label="Close"><X className="h-5 w-5" /></button>
            </div>
            {children}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/**
 * S01 Converse: a signer and a hearing person, both directions at once.
 *   signer  -> camera -> WS /ws/sign      -> captions (+ voice)
 *   hearing -> mic/keyboard -> /api/text-to-sign -> avatar signs it
 */
export function ConverseScreen({ variant = "page", className = "" }) {
  const embed = variant === "embed";
  const [speakers, setSpeakers] = useState([
    { id: "s", name: "Priya", role: "signer" },
    { id: "h", name: "Dr. Rao", role: "hearing" },
  ]);
  const [prefs] = usePrefs();
  const [voice, setVoice] = useState(!embed && prefs.voice);
  const [outLang, setOutLang] = useState(prefs.captionLang);
  const [flip, setFlip] = useState(false);
  const [keyboard, setKeyboard] = useState(embed);
  const [draft, setDraft] = useState("");
  const [simOpen, setSimOpen] = useState(false);
  const [summaryOpen, setSummaryOpen] = useState(false);
  const [speakersOpen, setSpeakersOpen] = useState(false);
  const [spoken, setSpoken] = useState([]);
  const [t2sPending, setT2sPending] = useState(null);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState(null);
  const [teachName, setTeachName] = useState("");
  const [player, snap] = usePlayer();
  const consent = useConsent();

  const signer = speakers[0], hearing = speakers[1];
  const session = useSignSession({ lang: outLang, speakResults: voice, speaker: signer.name, dominant: prefs.dominant });
  const cam = useCamera({ onFrame: f => { session.sendFrame(f); session.paint(f); } });

  const say = useCallback(async (text, { lang, channel = "text", resolutions, replaceId } = {}) => {
    const clean = text.trim();
    if (!clean) return;
    const l = lang || detectLanguage(clean);
    setBusy(true);
    try {
      const res = await backend.textToSign({ text: clean, resolutions: resolutions || {}, src_lang: l.code });
      const vm = composeFromResponse(res, clean);
      const card = {
        id: vm.id, speaker: hearing.name, speakerIndex: 1, channel, text: clean, state: resolutions ? (vm.gate === "emit" ? "enhanced" : vm.state) : vm.state,
        reason: vm.reason, advisory: vm.advisory, gloss: vm.gloss, lang: l.label, signLang: vm.signLang, at: Date.now(), repair: vm.repair,
      };
      setSpoken(s => [...s.filter(x => x.id !== replaceId), card].slice(-40));
      if (vm.gate === "emit") {
        player.enqueue(vm.clip, { text: clean, gloss: vm.gloss });
        setT2sPending(null);
      } else if (vm.repair) {
        setT2sPending({ ...vm, card, lang: l, channel });
      }
    } catch (e) {
      setToast(e.message);
    } finally {
      setBusy(false);
    }
  }, [hearing.name, player]);

  const speech = useSpeechInput({ lang: "auto", onUtterance: ({ text, lang }) => say(text, { lang, channel: "speech" }) });

  const toggleCam = async () => {
    if (cam.state === "on" || cam.state === "loading") return cam.stop();
    if (await consent.ask("camera")) cam.start();
  };
  const toggleMic = async () => {
    if (speech.listening) return speech.stop();
    if (!speech.supported) { setToast("Speech input needs Chrome or Edge. Use the keyboard or a scripted line instead."); setKeyboard(true); return; }
    if (await consent.ask("mic")) speech.start();
  };

  useEffect(() => { if (session.lastError) { setToast(session.lastError); session.clearError(); } }, [session.lastError]); // eslint-disable-line

  const signerCards = session.captions.map(c => ({ ...c, speaker: signer.name, speakerIndex: 0, lang: outLang === "hi" ? "हिन्दी" : "English" }));
  const all = useMemo(() => [...signerCards, ...spoken].sort((a, b) => a.at - b.at), [signerCards, spoken]);
  const latest = all[all.length - 1];
  const stageState = session.signing || busy ? "pending" : latest?.state || "pending";

  const live = session.signing
    ? { speaker: signer.name, speakerIndex: 0, channel: "sign", gloss: (session.partial?.gloss || []).map(g => (g === "?" ? "?" : g)) }
    : speech.interim ? { speaker: hearing.name, speakerIndex: 1, channel: "speech", text: speech.interim, lang: speech.detected?.label } : null;

  const repairs = all.filter(c => c.repair && (c.state === "repair" || c.answered)).length;
  const held = all.filter(c => c.state === "hold").length;
  const simulating = !!session.simInfo?.playing;
  const nowGloss = snap.meta?.gloss?.[snap.gi];

  const summaryText = useMemo(() => all.map(c => `[${fmtTime(c.at)}] ${c.speaker} (${TRUST[c.state]?.label}): ${c.state === "hold" ? "(held) " + (c.repair?.prompt || c.reason) : c.text}`).join("\n"), [all]);

  const signerPane = (
    <CameraStage cam={cam} session={session} simulated={simulating || !!session.simInfo} className="h-full w-full" compact={embed}
      emptyActions={flip ? null : (
        <div className="mt-4 flex flex-wrap justify-center gap-2">
          <button className="btn-moss" onClick={toggleCam}><Camera className="h-4 w-4" aria-hidden="true" /> Turn on camera</button>
          <button className="btn bg-white/10 text-light hover:bg-white/20" onClick={() => session.simulate(SIM_SCRIPTS[2].params)}><Hand className="h-4 w-4" aria-hidden="true" /> Play a signer</button>
        </div>
      )} />
  );
  const avatarPane = (
    <AvatarStage player={player} className="h-full w-full" background="sage" onPick={() => say("Hello", { channel: "text" })}>
      <div className="pointer-events-none absolute left-3 top-3 flex flex-col items-start gap-1">
        <span className="rounded-full bg-white/85 px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider text-ink">Signing for {signer.name}</span>
        {nowGloss && snap.playing && (
          <motion.span key={snap.gi} initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
            className="rounded-xl bg-ink px-2.5 py-1 font-mono text-lg font-extrabold text-light">{glossLabel(nowGloss)}</motion.span>
        )}
      </div>
      {snap.ch && snap.playing && <span className="pointer-events-none absolute right-4 top-3 font-mono text-5xl font-extrabold text-white drop-shadow-lg">{snap.ch}</span>}
    </AvatarStage>
  );
  const big = flip ? avatarPane : signerPane;
  const small = flip ? signerPane : avatarPane;

  return (
    <section className={cx("relative flex flex-col", embed ? "h-full" : "h-[calc(100svh-72px)]", className)} aria-label="Converse">
      {/* top bar */}
      <div className={cx("flex flex-wrap items-center gap-2 border-b border-ink/10 px-3 py-2 sm:px-4", embed && "py-2")}>
        <div className="flex min-w-0 items-center gap-2">
          <div className="flex -space-x-1.5">
            {speakers.map((s, i) => <SpeakerDot key={s.id} name={s.name} index={i} channel={i === 0 ? "sign" : "speech"} size={30} />)}
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-extrabold leading-tight">{signer.name} ⇄ {hearing.name}</p>
            <p className="truncate text-[11px] font-semibold text-mute">Clinic desk · {session.status === "open" ? "connected" : session.status}</p>
          </div>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {!embed && <span className="hidden md:block"><PipelineChip mode="CONVERSE" /></span>}
          <label className="relative">
            <span className="sr-only">Caption language</span>
            <select value={outLang} onChange={e => setOutLang(e.target.value)}
              className="min-h-10 appearance-none rounded-full border-2 border-ink/10 bg-white py-1 pl-3 pr-8 text-xs font-bold">
              <option value="en">Captions: English</option>
              <option value="hi">Captions: हिन्दी</option>
            </select>
            <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2" aria-hidden="true" />
          </label>
        </div>
      </div>

      {/* body */}
      <div className={cx("grid min-h-0 flex-1 gap-3 p-3 sm:p-4", embed ? "grid-cols-1 md:grid-cols-[1.25fr_1fr]" : "grid-cols-1 lg:grid-cols-[1.35fr_1fr]")}>
        {/* stage */}
        <div className="flex min-h-0 flex-col gap-3">
          <div
            className={cx("relative min-h-[240px] flex-1 overflow-hidden rounded-[1.6rem] ring-4 transition-[box-shadow,--tw-ring-color] duration-500",
              stageState === "repair" ? "ring-coral" : stageState === "hold" ? "ring-ink" : stageState === "high" ? "ring-moss" : stageState === "enhanced" ? "ring-sage" : "ring-transparent")}
          >
            <div className="absolute inset-0">{big}</div>
            <motion.div layout className="absolute bottom-3 right-3 z-10 aspect-[4/3] w-[44%] min-w-[150px] max-w-[280px] sm:w-[36%] overflow-hidden rounded-2xl shadow-(--shadow-lift) ring-2 ring-white">
              {small}
            </motion.div>
            {simulating && (
              <div className="absolute bottom-3 left-3 z-10 max-w-[55%] rounded-2xl bg-white/90 px-3 py-2 text-xs font-semibold text-ink backdrop-blur">
                <span className="eyebrow block text-[10px]">Simulated signer</span>
                {session.simInfo.signed?.map(g => g.replace("DEMO-NAMESIGN", "name sign")).join(" · ")}
              </div>
            )}
          </div>
          <div className="rounded-2xl bg-white p-3 shadow-(--shadow-card)">
            <div className="mb-2 flex items-center gap-2 text-xs font-bold">
              <span className="text-mute">Latest</span>
              {latest ? <><span>{latest.speaker}</span><TrustBadge state={stageState} size="sm" /></> : <span className="text-mute">waiting for someone to sign or speak</span>}
              {snap.queued > 0 && <span className="ml-auto text-mute">{snap.queued} queued for the signer</span>}
            </div>
            <TrustBar state={stageState} compact={embed} />
          </div>
        </div>

        {/* conversation */}
        <div className="flex min-h-0 flex-col gap-3">
          <CaptionStack items={all} live={live} big={!embed && all.length < 3} className={cx("min-h-[180px] flex-1 rounded-[1.6rem] bg-light/60 p-2", embed && "max-h-[340px]")}
            emptyHint={
              <span className="flex flex-col items-center gap-3">
                <span className="text-4xl" aria-hidden="true">🤟 ⇄ 🗣️</span>
                <span className="max-w-xs">Sign to the camera, speak, or type. Both sides of the conversation land here, each with how sure SIGNOPSIS is.</span>
                <span className="flex flex-wrap justify-center gap-2">
                  <button className="chip" onClick={() => session.simulate(SIM_SCRIPTS[0].params)}>▶ Priya signs</button>
                  <button className="chip" onClick={() => say(HEARING_LINES[0])}>▶ Dr. Rao speaks</button>
                </span>
              </span>
            } />

          <AnimatePresence>
            {session.pending && (
              <RepairCard key={session.pending.id} repair={session.pending.repair} reason={session.pending.reason}
                compact={embed} autoFocus={!embed} hotkeys={!embed}
                onAnswer={o => {
                  if (o.gloss === "__teach__") { session.answerRepair(session.pending, o); return; }
                  session.answerRepair(session.pending, o);
                }}
                onDismiss={() => session.answerRepair(session.pending, { gloss: "__none__", label: "Dismissed" })} />
            )}
            {t2sPending && !session.pending && (
              <RepairCard key={t2sPending.id} repair={t2sPending.repair} reason={t2sPending.reason} compact={embed} autoFocus={!embed} hotkeys={!embed}
                onAnswer={o => {
                  const p = t2sPending;
                  setT2sPending(null);
                  if (p.repair.type === "confirm") {
                    if (o.gloss === "SEND") { player.enqueue(p.clip, { text: p.text, gloss: p.gloss }); setSpoken(s => s.map(c => (c.id === p.card.id ? { ...c, state: "enhanced", answered: o.label } : c))); }
                    else { setDraft(p.text); setKeyboard(true); }
                    return;
                  }
                  if (o.gloss === "__none__") return;
                  say(p.text, { lang: p.lang, channel: p.channel, resolutions: { [p.repair.token_index]: o.gloss }, replaceId: p.card.id });
                }}
                onDismiss={() => setT2sPending(null)} />
            )}
            {session.teachOffer && (
              <motion.form key="teach" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                onSubmit={e => { e.preventDefault(); if (teachName.trim()) { session.startEnroll(teachName.trim(), true); setToast(`Now sign "${teachName}" a few more times, the same way.`); } }}
                className="rounded-[1.6rem] border-2 border-moss bg-white p-4">
                <p className="flex items-center gap-2 font-extrabold"><GraduationCap className="h-5 w-5 text-moss" aria-hidden="true" /> {session.teachOffer.prompt}</p>
                <div className="mt-3 flex gap-2">
                  <label className="sr-only" htmlFor="teach-name">What does it mean?</label>
                  <input id="teach-name" className="field" placeholder="e.g. Priya" value={teachName} onChange={e => setTeachName(e.target.value)} />
                  <button className="btn-moss shrink-0" type="submit">Teach</button>
                  <button className="btn-icon shrink-0" type="button" onClick={session.dismissTeach} aria-label="Not now"><X className="h-5 w-5" /></button>
                </div>
              </motion.form>
            )}
            {session.enroll && !session.enroll.done && (
              <motion.div key="enrolling" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                className="flex flex-wrap items-center gap-3 rounded-2xl bg-moss px-4 py-3 text-ink">
                <GraduationCap className="h-5 w-5" aria-hidden="true" />
                <span className="font-bold">Teaching “{session.enroll.display}”: {session.enroll.have} of {session.enroll.need}</span>
                {session.enroll.warning && <span className="w-full text-sm">{session.enroll.warning}</span>}
                <button className="btn ml-auto min-h-10 bg-white/15 px-3 text-sm" onClick={() => session.simulate({ gloss: "DEMO-NAMESIGN" })}>Sign it (sim)</button>
                <button className="btn min-h-10 bg-white/15 px-3 text-sm" onClick={session.cancelEnroll}>Cancel</button>
              </motion.div>
            )}
          </AnimatePresence>

          {keyboard && (
            <form className="flex gap-2" onSubmit={e => { e.preventDefault(); say(draft, { channel: "text" }); setDraft(""); }}>
              <label className="sr-only" htmlFor={`say-${variant}`}>Type for {hearing.name}</label>
              <input id={`say-${variant}`} className="field" value={draft} onChange={e => setDraft(e.target.value)}
                placeholder={`${hearing.name} says…`} autoComplete="off" />
              <button className="btn-primary shrink-0" disabled={!draft.trim() || busy} aria-label="Send to signer"><Send className="h-4 w-4" /></button>
            </form>
          )}
          {keyboard && (
            <div className="no-scrollbar -mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1">
              {HEARING_LINES.map(l => <button key={l} className="chip shrink-0" onClick={() => say(l)}>{l}</button>)}
            </div>
          )}
        </div>
      </div>

      {/* dock */}
      <div className={cx("relative z-20 border-t border-ink/10 bg-light/90 px-2 py-2 backdrop-blur", !embed && "pb-[max(.5rem,env(safe-area-inset-bottom))]")}>
        <AnimatePresence>
          {simOpen && (
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }}
              className="absolute bottom-[calc(100%+8px)] left-1/2 z-30 w-[min(20rem,calc(100vw-1.5rem))] -translate-x-1/2 rounded-2xl bg-white p-2 shadow-(--shadow-lift)" role="menu">
              <p className="eyebrow px-2 pb-1 pt-1">Simulated signer</p>
              {SIM_SCRIPTS.map(s => (
                <button key={s.label} role="menuitem" className="flex min-h-12 w-full items-center justify-between gap-2 rounded-xl px-2 text-left text-sm font-semibold hover:bg-light"
                  onClick={() => { setSimOpen(false); session.simulate(s.params); }}>
                  <span>{s.label}</span><span className="shrink-0 rounded-full bg-light px-2 py-0.5 text-[10px] font-bold uppercase text-mute">{s.tag}</span>
                </button>
              ))}
            </motion.div>
          )}
        </AnimatePresence>

        <div className="no-scrollbar mx-auto flex max-w-4xl items-center justify-start gap-1.5 overflow-x-auto sm:justify-center">
          <DockButton on={cam.state === "on"} onClick={toggleCam} Icon={Camera} OffIcon={CameraOff} label="Camera" tone="moss" hint="Sign to the camera" />
          <DockButton on={speech.listening} onClick={toggleMic} Icon={Mic} OffIcon={MicOff} label="Mic" tone="coral" hint={`${hearing.name} speaks; language is detected automatically`} />
          <DockButton on={simOpen || simulating} onClick={() => setSimOpen(o => !o)} Icon={Hand} label="Signing" hint="Play a simulated signer" pressed={false} />
          <DockButton on={keyboard} onClick={() => setKeyboard(k => !k)} Icon={Keyboard} label="Type" />
          <DockButton on={summaryOpen} onClick={() => setSummaryOpen(true)} Icon={FileText} label="Summary" badge={all.length} pressed={false} />
          {!embed && <DockButton on={speakersOpen} onClick={() => setSpeakersOpen(true)} Icon={Users} label="Speakers" pressed={false} />}
          <DockButton on={flip} onClick={() => setFlip(f => !f)} Icon={FlipHorizontal2} label="Flip" hint="Swap the big and small views" />
          <DockButton on={voice} onClick={() => setVoice(v => !v)} Icon={Volume2} OffIcon={VolumeX} label="Voice" hint="Read the signer's captions aloud" />
        </div>
      </div>

      <Sheet open={summaryOpen} title="Conversation summary" onClose={() => setSummaryOpen(false)} wide>
        <div className="grid grid-cols-3 gap-2">
          {[["Turns", all.length], ["Questions asked", repairs], ["Held", held]].map(([k, v]) => (
            <div key={k} className="rounded-2xl bg-white p-3 text-center"><p className="text-3xl font-extrabold">{v}</p><p className="text-xs font-semibold text-mute">{k}</p></div>
          ))}
        </div>
        <ol className="mt-4 space-y-2">
          {all.length === 0 && <li className="text-mute">Nothing yet.</li>}
          {all.map(c => (
            <li key={c.id} className="flex items-start gap-2 rounded-2xl bg-white p-3">
              <SpeakerDot name={c.speaker} index={c.speakerIndex} size={24} />
              <div className="min-w-0 flex-1">
                <p className="text-sm"><b>{c.speaker}</b> <span className="text-mute">· {fmtTime(c.at)}</span></p>
                <p className="font-semibold">{c.state === "hold" ? <i className="text-mute">Held: {c.repair?.prompt}</i> : c.text}</p>
                {c.gloss?.length > 0 && <GlossStrip items={c.gloss} size="sm" className="mt-1" />}
              </div>
              <TrustBadge state={c.state} size="sm" />
            </li>
          ))}
        </ol>
        <div className="mt-4 flex gap-2">
          <button className="btn-ghost" onClick={() => { navigator.clipboard?.writeText(summaryText); setToast("Copied"); }}><Copy className="h-4 w-4" aria-hidden="true" /> Copy</button>
          <a className="btn-primary" download="signopsis-conversation.txt" href={`data:text/plain;charset=utf-8,${encodeURIComponent(summaryText)}`}><Download className="h-4 w-4" aria-hidden="true" /> Download</a>
          <button className="btn-ghost ml-auto" onClick={() => { session.reset(); setSpoken([]); player.stop(); setSummaryOpen(false); }}><Trash2 className="h-4 w-4" aria-hidden="true" /> Clear</button>
        </div>
      </Sheet>

      <Sheet open={speakersOpen} title="Speakers" onClose={() => setSpeakersOpen(false)}>
        <p className="text-sm text-mute">Each person gets a colour <b>and</b> a shape, so captions stay readable without colour.</p>
        <ul className="mt-4 space-y-2">
          {speakers.map((s, i) => (
            <li key={s.id} className="flex items-center gap-3 rounded-2xl bg-white p-3">
              <SpeakerDot name={s.name} index={i} channel={i === 0 ? "sign" : "speech"} size={36} />
              <div className="flex-1">
                <label className="text-xs font-bold text-mute" htmlFor={`spk-${s.id}`}>{s.role === "signer" ? "Signs (camera)" : "Speaks or types"}</label>
                <input id={`spk-${s.id}`} className="field mt-1 min-h-11" value={s.name}
                  onChange={e => setSpeakers(list => list.map(x => (x.id === s.id ? { ...x, name: e.target.value || "?" } : x)))} />
              </div>
            </li>
          ))}
        </ul>
        <button className="btn-ghost mt-3 w-full" onClick={() => setToast("Multi-party diarization arrives with the ASR pipeline (LISTEN mode).")}>
          <Plus className="h-4 w-4" aria-hidden="true" /> Add a speaker
        </button>
        <p className="mt-4 flex items-center gap-2 text-xs text-mute"><Sparkles className="h-4 w-4" aria-hidden="true" /> Spoken language is detected per sentence{speech.detected ? `; last: ${langLabel(speech.detected.code)}` : ""}.</p>
      </Sheet>

      {consent.sheet}
      <Toast message={toast} onClose={() => setToast(null)} />
    </section>
  );
}
