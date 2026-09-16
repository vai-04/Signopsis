import { useCallback, useEffect, useRef, useState } from "react";
import { detectLanguage, speechSupported, startRecognition } from "../services/speech.js";

/**
 * Microphone -> utterances with automatic language detection.
 * onUtterance({text, lang:{code,label,sure}, confidence}) fires for every final result.
 */
export function useSpeechInput({ lang = "auto", onUtterance } = {}) {
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState("");
  const [detected, setDetected] = useState(null);
  const [error, setError] = useState(null);
  const rec = useRef(null);
  const cb = useRef(onUtterance);
  cb.current = onUtterance;

  const stop = useCallback(() => {
    rec.current?.stop();
    rec.current = null;
    setListening(false);
    setInterim("");
  }, []);

  const start = useCallback(() => {
    setError(null);
    rec.current?.stop();
    rec.current = startRecognition({
      lang,
      onInterim: t => { setInterim(t); setDetected(detectLanguage(t)); },
      onFinal: (text, confidence) => {
        if (!text) return;
        const l = lang === "auto" ? detectLanguage(text) : { code: lang, label: lang, sure: true };
        setDetected(l);
        setInterim("");
        cb.current?.({ text, lang: l, confidence });
      },
      onError: e => { setError(e.message); setListening(false); },
      onEnd: () => setListening(false),
    });
    setListening(!!rec.current);
  }, [lang]);

  useEffect(() => () => rec.current?.stop(), []);
  useEffect(() => { if (listening) start(); }, [lang]); // eslint-disable-line react-hooks/exhaustive-deps

  return { listening, interim, detected, error, start, stop, supported: speechSupported() };
}
