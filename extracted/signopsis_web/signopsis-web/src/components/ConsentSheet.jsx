import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Camera, Mic, Monitor, ShieldCheck, X } from "lucide-react";
import { cx } from "../utils/cx.js";

const KINDS = {
  camera: {
    Icon: Camera, title: "Use your camera?",
    points: [
      "Hand, body and face landmarks are computed on this device.",
      "Only those points (no video, no images) go to the SIGNOPSIS server.",
      "One brightness number is sent so it can tell you when it's too dark.",
    ],
  },
  mic: {
    Icon: Mic, title: "Use your microphone?",
    points: [
      "Speech is turned into text by your browser's speech service.",
      "Only the text is sent to SIGNOPSIS to be signed.",
      "Stop listening at any time with the mic button.",
    ],
  },
  screen: {
    Icon: Monitor, title: "Let SIGNOPSIS read this screen?",
    points: [
      "Only the page you choose is described, and only when you ask.",
      "Nothing on screen is stored after the answer.",
      "Form fields marked private are never read aloud.",
    ],
  },
};

/** Bottom sheet asking for a capability; `onAllow` runs only after an explicit yes. */
export function ConsentSheet({ open, kind = "camera", onAllow, onClose }) {
  const k = KINDS[kind];
  const btn = useRef(null);
  const [remember, setRemember] = useState(true);
  useEffect(() => { if (open) setTimeout(() => btn.current?.focus(), 50); }, [open]);
  useEffect(() => {
    if (!open) return undefined;
    const esc = e => e.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [open, onClose]);
  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-[90] flex items-end justify-center bg-ink/40 p-0 backdrop-blur-sm sm:items-center sm:p-6"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
          <motion.div
            role="dialog" aria-modal="true" aria-labelledby="consent-title"
            initial={{ y: 60 }} animate={{ y: 0 }} exit={{ y: 60 }} transition={{ type: "spring", stiffness: 300, damping: 30 }}
            onClick={e => e.stopPropagation()}
            className="w-full max-w-md rounded-t-[2rem] bg-white p-6 pb-8 shadow-(--shadow-lift) sm:rounded-[2rem]"
          >
            <div className="flex items-start justify-between">
              <span className="grid h-14 w-14 place-items-center rounded-2xl bg-sage-soft text-moss-deep"><k.Icon className="h-7 w-7" aria-hidden="true" /></span>
              <button className="btn-icon -mr-2 -mt-2" onClick={onClose} aria-label="Close"><X className="h-5 w-5" /></button>
            </div>
            <h2 id="consent-title" className="mt-4 text-2xl font-extrabold">{k.title}</h2>
            <ul className="mt-3 space-y-2">
              {k.points.map(p => (
                <li key={p} className="flex gap-2 text-[15px] text-ink-soft">
                  <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-moss" aria-hidden="true" />{p}
                </li>
              ))}
            </ul>
            <label className="mt-4 flex min-h-12 cursor-pointer items-center gap-3 text-sm font-semibold">
              <input type="checkbox" checked={remember} onChange={e => setRemember(e.target.checked)} className="h-5 w-5 accent-[#689D4B]" />
              Don't ask again on this device
            </label>
            <div className="mt-4 grid grid-cols-2 gap-2">
              <button className="btn-ghost" onClick={onClose}>Not now</button>
              <button ref={btn} className={cx("btn-moss")} onClick={() => { if (remember) rememberConsent(kind); onAllow(); }}>Allow</button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

const KEY = "signopsis.consent";
export function hasConsent(kind) {
  try { return JSON.parse(localStorage.getItem(KEY) || "{}")[kind] === true; } catch { return false; }
}
export function rememberConsent(kind, v = true) {
  try {
    const o = JSON.parse(localStorage.getItem(KEY) || "{}");
    o[kind] = v;
    localStorage.setItem(KEY, JSON.stringify(o));
  } catch { /* ignore */ }
}
export function clearConsent() {
  try { localStorage.removeItem(KEY); } catch { /* ignore */ }
}

/** hook: ask(kind).then(ok => ...) */
export function useConsent() {
  const [req, setReq] = useState(null);
  const ask = kind => new Promise(resolve => {
    if (hasConsent(kind)) return resolve(true);
    setReq({ kind, resolve });
  });
  const sheet = (
    <ConsentSheet
      open={!!req}
      kind={req?.kind}
      onAllow={() => { req.resolve(true); setReq(null); }}
      onClose={() => { req?.resolve(false); setReq(null); }}
    />
  );
  return { ask, sheet };
}
