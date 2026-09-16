import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Camera, Check, CircleDot, Hand, Loader2, Trash2, Undo2, Save, Sparkles, X } from "lucide-react";
import { CameraStage } from "./CameraStage.jsx";
import { ShotProgress, Segmented, Toast } from "./Bits.jsx";
import { useConsent } from "./ConsentSheet.jsx";
import { useSignSession } from "../hooks/useSignSession.js";
import { useCamera } from "../hooks/useCamera.js";
import { cx } from "../utils/cx.js";

const STEPS = ["Name it", "Record 4×", "Check", "Saved"];
const PROMPTS = [
  "Sign it once, at your normal pace.",
  "Nice. Sign it again.",
  "Sign it once more, the same way.",
  "Last one. Same as before.",
];
const KINDS = [
  { value: "name", label: "Name sign" },
  { value: "variant", label: "Local variant" },
  { value: "jargon", label: "Work word" },
];
const SCOPES = [
  { value: "me", label: "Only me" },
  { value: "team", label: "My team" },
];

/**
 * S09 Enrollment: teach SIGNOPSIS a sign with four samples (no retraining; prototypes are added to the index).
 * Messages: enroll_start → (phrases) → enroll_progress ×n → enrolled; enroll_undo; enroll_cancel; forget_sign.
 */
export function EnrollmentScreen({ variant = "page" }) {
  const embed = variant === "embed";
  const [label, setLabel] = useState("Priya");
  const [kind, setKind] = useState("name");
  const [scope, setScope] = useState("me");
  const [counting, setCounting] = useState(0);
  const [saved, setSaved] = useState(null);
  const [toast, setToast] = useState(null);
  const session = useSignSession({ speaker: label });
  const cam = useCamera({ onFrame: f => { session.sendFrame(f); session.paint(f); } });
  const consent = useConsent();
  const timer = useRef(null);

  const e = session.enroll;
  const have = saved ? 4 : e?.have ?? 0;
  const step = saved ? 3 : e?.done ? 2 : e ? 1 : 0;
  const recording = counting > 0 || session.signing || !!session.simInfo?.playing;

  useEffect(() => { if (e?.warning) setToast(e.warning); }, [e?.warning]);
  useEffect(() => { if (session.lastError) { setToast(session.lastError); session.clearError(); } }, [session.lastError]); // eslint-disable-line
  useEffect(() => () => clearInterval(timer.current), []);

  const begin = () => {
    if (!label.trim()) return;
    setSaved(null);
    session.startEnroll(label.trim(), false, { kind, scope });
  };

  const record = async () => {
    if (!e) begin();
    // countdown, then capture one phrase (camera) or play one simulated sample
    let n = 3;
    setCounting(n);
    clearInterval(timer.current);
    timer.current = setInterval(() => {
      n -= 1;
      setCounting(n);
      if (n <= 0) {
        clearInterval(timer.current);
        if (cam.state !== "on") session.simulate({ gloss: "DEMO-NAMESIGN", seed: Math.floor(Math.random() * 1e4) });
      }
    }, 650);
  };

  const useCam = async () => {
    if (cam.state === "on") return cam.stop();
    if (await consent.ask("camera")) cam.start();
  };

  const save = () => {
    setSaved({ label: e?.display || label, kind, scope, at: Date.now() });
    setToast(`“${e?.display || label}” saved. SIGNOPSIS will recognise it from now on.`);
  };

  return (
    <div className={cx("grid grid-cols-1 gap-4 [&>*]:min-w-0", embed ? "md:grid-cols-[1fr_1fr]" : "lg:grid-cols-[1.1fr_1fr]")}>
      <div className="relative">
        <CameraStage cam={cam} session={session} simulated={!!session.simInfo} compact={embed}
          className={cx("rounded-[1.8rem]", embed ? "h-[340px]" : "aspect-[4/3] w-full")}
          emptyActions={<button className="btn-moss mt-4" onClick={useCam}><Camera className="h-4 w-4" aria-hidden="true" /> Use my camera</button>} />
        <AnimatePresence>
          {counting > 0 && (
            <motion.div key={counting} initial={{ scale: 1.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ opacity: 0 }}
              className="pointer-events-none absolute inset-0 grid place-items-center" aria-live="assertive">
              <span className="grid h-32 w-32 place-items-center rounded-full bg-coral text-7xl font-extrabold text-white shadow-2xl">{counting}</span>
            </motion.div>
          )}
        </AnimatePresence>
        {!embed && (
          <div className="mt-3 flex flex-wrap gap-2">
            <button className={cx("btn", cam.state === "on" ? "bg-ink text-light" : "btn-ghost")} onClick={useCam} aria-pressed={cam.state === "on"}>
              <Camera className="h-4 w-4" aria-hidden="true" /> {cam.state === "on" ? "Camera on" : "Use camera"}
            </button>
            <p className="self-center text-sm text-mute">No camera? Record plays a simulated signer doing a made-up name sign.</p>
          </div>
        )}
      </div>

      <div className="card flex flex-col p-5 sm:p-6">
        {/* step indicator */}
        <ol className="grid grid-cols-4 gap-1.5" aria-label="Steps">
          {STEPS.map((s, i) => (
            <li key={s} aria-current={i === step ? "step" : undefined}>
              <span className={cx("block h-1.5 rounded-full", i < step ? "bg-moss" : i === step ? "bg-ink" : "bg-ink/10")} />
              <span className={cx("mt-1.5 block text-[11px] font-bold uppercase tracking-wider", i === step ? "text-ink" : "text-mute")}>
                {i < step ? "✓ " : `${i + 1}. `}{s}
              </span>
            </li>
          ))}
        </ol>

        <div className="mt-6 flex items-end justify-between gap-3">
          <div>
            <p className="eyebrow">Teach a sign</p>
            <p className="mt-1 text-5xl font-extrabold tabular-nums tracking-tight">{Math.min(have + (e && !e.done ? 1 : 0), 4) || 1} <span className="text-mute">of 4</span></p>
          </div>
          <ShotProgress have={have} need={4} />
        </div>
        <AnimatePresence mode="wait">
          <motion.p key={`${have}-${step}`} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            className="mt-3 text-2xl font-bold leading-tight" aria-live="polite">
            {saved ? "Saved. It's yours now." : e?.done ? "All four look consistent. Save it?" : e ? PROMPTS[Math.min(have, 3)] : "Give the sign a name, then record it four times."}
          </motion.p>
        </AnimatePresence>
        {e?.done && e.warning && <p className="mt-1 text-sm font-semibold text-coral-deep">{e.warning}</p>}

        <div className="mt-5 grid gap-4">
          <div>
            <label htmlFor={`enroll-label-${variant}`} className="text-xs font-bold uppercase tracking-wider text-mute">What does it mean?</label>
            <input id={`enroll-label-${variant}`} className="field mt-1.5 font-mono text-xl font-extrabold uppercase tracking-wider" value={label}
              disabled={!!e && !e.done} onChange={ev => setLabel(ev.target.value)} maxLength={32} />
          </div>
          <div className="flex flex-wrap gap-4">
            <div>
              <p className="text-xs font-bold uppercase tracking-wider text-mute">Type</p>
              <Segmented className="mt-1.5" label="Sign type" value={kind} onChange={setKind} options={KINDS} />
            </div>
            <div>
              <p className="text-xs font-bold uppercase tracking-wider text-mute">Who can use it</p>
              <Segmented className="mt-1.5" label="Scope" value={scope} onChange={setScope} options={SCOPES} />
            </div>
          </div>
        </div>

        <div className="mt-6 grid grid-cols-3 gap-2 sm:mt-auto sm:pt-6">
          <button className="btn-ghost" onClick={session.undoSample} disabled={!e || e.done || have === 0 || recording}>
            <Undo2 className="h-4 w-4" aria-hidden="true" /> Redo last
          </button>
          <button className="btn-coral" onClick={record} disabled={recording || e?.done || !label.trim() || !!saved}>
            {recording ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <CircleDot className="h-4 w-4" aria-hidden="true" />}
            {recording ? "Recording" : "Record"}
          </button>
          <button className="btn-moss" onClick={save} disabled={!e?.done || !!saved}>
            <Save className="h-4 w-4" aria-hidden="true" /> Save
          </button>
        </div>
        {(e || saved) && (
          <button className="mt-2 min-h-11 text-sm font-semibold text-mute underline underline-offset-4 hover:text-ink"
            onClick={() => { session.cancelEnroll(); setSaved(null); }}>
            <X className="mr-1 inline h-3.5 w-3.5" aria-hidden="true" />{saved ? "Teach another sign" : "Cancel"}
          </button>
        )}

        {!embed && (
          <div className="mt-6 border-t border-ink/5 pt-4">
            <p className="eyebrow flex items-center gap-1.5"><Sparkles className="h-3.5 w-3.5" aria-hidden="true" /> Your signs</p>
            {session.signs.length === 0 ? (
              <p className="mt-2 text-sm text-mute">None yet.</p>
            ) : (
              <ul className="mt-2 flex flex-wrap gap-2">
                {session.signs.map(s => (
                  <li key={s.label} className="flex items-center gap-1 rounded-full bg-sage-soft py-1 pl-3 pr-1 text-sm font-bold text-moss-deep">
                    <Hand className="h-3.5 w-3.5" aria-hidden="true" />{s.display || s.label}
                    <button className="grid h-9 w-9 place-items-center rounded-full hover:bg-white" aria-label={`Forget ${s.display || s.label}`}
                      onClick={() => session.forgetSign(s.label)}><Trash2 className="h-3.5 w-3.5" /></button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
        {saved && (
          <p className="mt-3 flex items-center gap-2 rounded-2xl bg-sage-soft p-3 text-sm font-semibold text-moss-deep">
            <Check className="h-4 w-4" aria-hidden="true" /> {saved.label} · {KINDS.find(k => k.value === saved.kind).label} · {SCOPES.find(k => k.value === saved.scope).label}
          </p>
        )}
      </div>
      {consent.sheet}
      <Toast message={toast} onClose={() => setToast(null)} />
    </div>
  );
}
