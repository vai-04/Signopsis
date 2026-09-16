// Speech in / speech out in the browser, plus automatic spoken-language detection.
// Pipeline C (ASR + diarization) runs on the GPU backend later; until then the Web Speech API
// provides transcripts and this module tags each utterance with its language.
import { detectLang } from "./mock/mockResolver.js";

export const SPOKEN_LANGS = [
  { code: "auto", label: "Auto-detect", asr: "en-IN" },
  { code: "en", label: "English", asr: "en-IN" },
  { code: "hi", label: "हिन्दी Hindi", asr: "hi-IN" },
  { code: "hi-en", label: "Hinglish", asr: "en-IN" },
  { code: "ta", label: "தமிழ் Tamil", asr: "ta-IN" },
  { code: "bn", label: "বাংলা Bengali", asr: "bn-IN" },
  { code: "te", label: "తెలుగు Telugu", asr: "te-IN" },
  { code: "mr", label: "मराठी Marathi", asr: "mr-IN" },
  { code: "es", label: "Español", asr: "es-ES" },
  { code: "fr", label: "Français", asr: "fr-FR" },
];

/** languages the backend resolver handles today (others are shown, flagged, and fingerspelled) */
export const RESOLVER_LANGS = new Set(["en", "hi", "hi-en"]);

export const SIGN_LANGS = [
  { code: "isl", label: "ISL", name: "Indian Sign Language", status: "ready" },
  { code: "asl", label: "ASL", name: "American Sign Language", status: "pack" },
  { code: "bsl", label: "BSL", name: "British Sign Language", status: "pack" },
  { code: "auslan", label: "Auslan", name: "Australian Sign Language", status: "pack" },
  { code: "lsf", label: "LSF", name: "Langue des Signes Française", status: "pack" },
];

const SCRIPTS = [
  ["ta", /[஀-௿]/], ["bn", /[ঀ-৿]/], ["te", /[ఀ-౿]/],
  ["gu", /[઀-૿]/], ["pa", /[਀-੿]/], ["kn", /[ಀ-೿]/],
  ["ml", /[ഀ-ൿ]/], ["ur", /[؀-ۿ]/],
];
const MARATHI_HINTS = /(आहे|आहेत|नाही|मला|तुम्ही|काय)/;
const LATIN_HINTS = {
  es: /\b(el|la|los|las|que|por|para|estoy|dónde|gracias|hola|quiero)\b/i,
  fr: /\b(le|la|les|je|vous|est|merci|bonjour|où|suis|pas)\b/i,
};

export function langLabel(code) {
  if (code === "hi-en") return "Hinglish";
  const l = SPOKEN_LANGS.find(x => x.code === code);
  return l ? l.label.replace(/^\S+\s(?=[A-Z])/, "") : code?.toUpperCase?.() || "Unknown";
}

/** @returns {{code: string, label: string, sure: boolean}} */
export function detectLanguage(text) {
  const t = (text || "").trim();
  if (!t) return { code: "en", label: "English", sure: false };
  for (const [code, re] of SCRIPTS) if (re.test(t)) return { code, label: langLabel(code), sure: true };
  if (/[ऀ-ॿ]/.test(t)) {
    const code = MARATHI_HINTS.test(t) ? "mr" : "hi";
    return { code, label: langLabel(code), sure: true };
  }
  for (const [code, re] of Object.entries(LATIN_HINTS)) {
    const hits = (t.match(new RegExp(re.source, "gi")) || []).length;
    if (hits >= 2) return { code, label: langLabel(code), sure: hits >= 3 };
  }
  const toks = t.split(/\s+/).map(w => ({ text: w.replace(/[^\p{L}']/gu, ""), kind: "word" })).filter(x => x.text);
  const code = detectLang(toks);
  return { code, label: langLabel(code), sure: toks.length >= 3 };
}

export const speechSupported = () => typeof window !== "undefined" && !!(window.SpeechRecognition || window.webkitSpeechRecognition);

/**
 * Continuous recognition with interim results.
 * @param {{lang?: string, onInterim?: Function, onFinal?: Function, onError?: Function, onEnd?: Function}} o
 */
export function startRecognition({ lang = "auto", onInterim, onFinal, onError, onEnd }) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { onError?.(new Error("Speech recognition isn't available in this browser. Try Chrome or Edge, or use the scripted speaker.")); return null; }
  const rec = new SR();
  rec.lang = (SPOKEN_LANGS.find(l => l.code === lang) || SPOKEN_LANGS[0]).asr;
  rec.continuous = true;
  rec.interimResults = true;
  let stopped = false;
  rec.onresult = e => {
    let interim = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const r = e.results[i];
      if (r.isFinal) onFinal?.(r[0].transcript.trim(), r[0].confidence);
      else interim += r[0].transcript;
    }
    if (interim) onInterim?.(interim.trim());
  };
  rec.onerror = e => { if (e.error !== "no-speech" && e.error !== "aborted") onError?.(new Error(`Microphone: ${e.error}`)); };
  rec.onend = () => { if (!stopped) { try { rec.start(); } catch { onEnd?.(); } } else onEnd?.(); };
  try { rec.start(); } catch (e) { onError?.(e); return null; }
  return { stop() { stopped = true; try { rec.stop(); } catch { /* already stopped */ } } };
}

/** speak a TTS target from a RenderPlan */
export function speak(target, { muted = false } = {}) {
  if (muted || !target?.text || typeof speechSynthesis === "undefined") return;
  const u = new SpeechSynthesisUtterance(target.text);
  u.lang = target.lang === "hi" ? "hi-IN" : "en-IN";
  u.rate = target.rate ?? 1;
  u.pitch = target.pitch ?? 1;
  u.volume = target.volume ?? 1;
  speechSynthesis.cancel();
  speechSynthesis.speak(u);
}
