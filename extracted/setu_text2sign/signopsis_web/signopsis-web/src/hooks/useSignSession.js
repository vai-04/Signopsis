import { useCallback, useEffect, useRef, useState } from "react";
import { backend } from "../services/backend.js";
import { captionFromResult } from "../services/adapters.js";
import { speak } from "../services/speech.js";
import { metrics } from "../services/metrics.js";

/**
 * Pipeline A (sign -> text/voice) over WS /ws/sign.
 * Exposes everything the Converse / Enroll screens render, plus actions that map 1:1 to client messages.
 */
export function useSignSession({ enabled = true, lang = "en", dominant = "right", speakResults = false, speaker = "Signer" } = {}) {
  const [status, setStatus] = useState("idle");
  const [hello, setHello] = useState(null);
  const [live, setLive] = useState(null);
  const [partial, setPartial] = useState(null);
  const [signing, setSigning] = useState(false);
  const [captions, setCaptions] = useState([]);
  const [pending, setPending] = useState(null);       // caption with an open repair
  const [teachOffer, setTeachOffer] = useState(null);
  const [enroll, setEnroll] = useState(null);         // enroll_progress / enrolled
  const [signs, setSigns] = useState([]);
  const [lastError, setLastError] = useState(null);
  const [simInfo, setSimInfo] = useState(null);
  const sock = useRef(null);
  const repairing = useRef(false);
  const simTimer = useRef(null);
  const onFrameCb = useRef(null);
  const opts = useRef({ speakResults, speaker });
  opts.current = { speakResults, speaker };

  useEffect(() => {
    if (!enabled) return undefined;
    let alive = true;
    const offs = [];
    backend.openSignSession({ lang, dominant }).then(s => {
      if (!alive) { s.close(); return; }
      sock.current = s;
      setStatus(s.status);
      offs.push(
        s.on("status", e => setStatus(e.status)),
        s.on("hello", e => { setHello(e); setSigns(e.signs || []); }),
        s.on("live", e => setLive(e)),
        s.on("phrase_start", () => { setSigning(true); setPartial({ gloss: [] }); }),
        s.on("partial", e => setPartial(e)),
        s.on("result", e => {
          setSigning(false);
          setPartial(null);
          const card = captionFromResult(e, { speaker: opts.current.speaker, repaired: repairing.current });
          repairing.current = false;
          setCaptions(c => [...c.slice(-40), card]);
          metrics.record("result", { state: card.state, channel: "sign", latency: card.timings?.total ?? null });
          setPending(card.repair && card.state !== "high" && card.state !== "enhanced" ? card : null);
          if (card.tts && opts.current.speakResults && card.text) speak(card.tts);
        }),
        s.on("repair_done", e => {
          setPending(null);
          setCaptions(c => c.map(x => (x.id === e.frame_id ? { ...x, dismissed: true } : x)));
        }),
        s.on("teach_offer", e => setTeachOffer(e)),
        s.on("enroll_progress", e => { setSigning(false); setPartial(null); setEnroll(e.cancelled ? null : { ...e, done: false }); }),
        s.on("enrolled", e => { setSigning(false); setPartial(null); setEnroll({ ...e, have: 4, need: 4, done: true }); setTeachOffer(null); }),
        s.on("signs", e => setSigns(e.signs || [])),
        s.on("error", e => setLastError(e.message)),
      );
    }).catch(e => { setStatus("error"); setLastError(e.message); });
    return () => {
      alive = false;
      offs.forEach(f => f && f());
      clearTimeout(simTimer.current);
      sock.current?.close();
      sock.current = null;
    };
  }, [enabled, lang, dominant]);

  const send = useCallback(msg => sock.current?.send(msg), []);
  const sendFrame = useCallback(frame => sock.current?.send(frame), []);

  const answerRepair = useCallback((card, option) => {
    if (!card?.repair) return;
    repairing.current = option.gloss !== "__none__";
    if (option.gloss === "__teach__") setTeachOffer({ samples: 1, need: 4, prompt: "What does this sign mean?" });
    send({ type: "repair_choice", frame_id: card.id, slot: card.repair.slot, choice: option.gloss });
    setCaptions(c => c.map(x => (x.id === card.id ? { ...x, answered: option.label } : x)));
    setPending(null);
  }, [send]);

  const startEnroll = useCallback((label, fromUnknown = false, meta = {}) => {
    send({ type: fromUnknown ? "enroll_from_unknown" : "enroll_start", label, ...meta });
    setTeachOffer(null);
  }, [send]);
  const cancelEnroll = useCallback(() => { send({ type: "enroll_cancel" }); setEnroll(null); }, [send]);
  const undoSample = useCallback(() => send({ type: "enroll_undo" }), [send]);
  const forgetSign = useCallback(label => send({ type: "forget_sign", label }), [send]);
  const setConfig = useCallback(cfg => send({ type: "config", ...cfg }), [send]);
  const reset = useCallback(() => { send({ type: "reset" }); setCaptions([]); setPending(null); setPartial(null); }, [send]);
  const dismissTeach = useCallback(() => setTeachOffer(null), []);

  /** stream a simulated signer (GET /api/simcam) through the session in real time */
  const simulate = useCallback(async (params = {}) => {
    clearTimeout(simTimer.current);
    try {
      const t0 = Math.round(performance.now());
      const sim = await backend.simcam({ severity: 0, seed: Math.floor(Math.random() * 1000), ...params, t0 });
      setSimInfo({ ...sim.info, degrade: sim.degrade, playing: true });
      const frames = sim.frames;
      const start = performance.now(), base = frames[0].t;
      let i = 0;
      const tick = () => {
        const now = performance.now() - start;
        while (i < frames.length && frames[i].t - base <= now) {
          const f = { ...frames[i], t: start + (frames[i].t - base) };
          sock.current?.send(f);
          onFrameCb.current?.(f);
          i++;
        }
        if (i < frames.length) simTimer.current = setTimeout(tick, 15);
        else simTimer.current = setTimeout(() => { sock.current?.send({ type: "flush" }); setSimInfo(s => (s ? { ...s, playing: false } : s)); onFrameCb.current?.(null); }, 700);
      };
      tick();
      return sim;
    } catch (e) {
      setLastError(e.message);
      return null;
    }
  }, []);

  const onFrame = useCallback(fn => { onFrameCb.current = fn; }, []);

  return {
    status, hello, live, partial, signing, captions, pending, teachOffer, enroll, signs, lastError, simInfo,
    sendFrame, paint: f => onFrameCb.current?.(f), answerRepair, startEnroll, cancelEnroll, undoSample, forgetSign, setConfig, reset, simulate, onFrame, dismissTeach,
    clearError: () => setLastError(null),
  };
}
