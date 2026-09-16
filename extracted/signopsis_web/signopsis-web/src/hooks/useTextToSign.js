import { useCallback, useRef, useState } from "react";
import { backend } from "../services/backend.js";
import { composeFromResponse } from "../services/adapters.js";

/**
 * Pipeline D (text -> sign). Wraps POST /api/text-to-sign.
 *   const { result, loading, error, translate, answerRepair } = useTextToSign();
 *   translate("Hello", { sign_lang: "isl", src_lang: "auto" })
 */
export function useTextToSign() {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const last = useRef({ text: "", opts: {} });
  const reqId = useRef(0);
  const abort = useRef(null);

  const translate = useCallback(async (text, opts = {}) => {
    const clean = (text || "").trim();
    if (!clean) return null;
    abort.current?.abort();
    const ctrl = new AbortController();
    abort.current = ctrl;
    const my = ++reqId.current;
    last.current = { text: clean, opts };
    setLoading(true);
    setError(null);
    try {
      const t0 = performance.now();
      const res = await backend.textToSign({
        text: clean,
        resolutions: opts.resolutions || {},
        src_lang: opts.src_lang && opts.src_lang !== "auto" ? opts.src_lang : undefined,
        sign_lang: opts.sign_lang || "isl",
      }, ctrl.signal);
      if (my !== reqId.current) return null;
      const vm = { ...composeFromResponse(res, clean), roundTripMs: Math.round(performance.now() - t0), raw: res };
      if (opts.resolutions && Object.keys(opts.resolutions).length && vm.gate === "emit") vm.state = "enhanced";
      setResult(vm);
      return vm;
    } catch (e) {
      if (e.name === "AbortError" || my !== reqId.current) return null;
      setError(e.message || String(e));
      return null;
    } finally {
      if (my === reqId.current) setLoading(false);
    }
  }, []);

  /** answer a repair card from the RenderPlan */
  const answerRepair = useCallback((repair, option) => {
    const { text, opts } = last.current;
    if (repair.type === "confirm") {
      // confirm is decided by the author on the client: SEND plays the preview as shown, REPHRASE hands back the pen
      if (option.gloss === "SEND") {
        setResult(r => (r ? { ...r, gate: "emit", state: "enhanced", confirmed: true, repair: null, reason: "Sent as shown after you confirmed the preview." } : r));
      } else {
        setResult(r => (r ? { ...r, repair: null, rephrase: true } : r));
      }
      return null;
    }
    if (option.gloss === "__none__") { setResult(r => (r ? { ...r, repair: null, dismissed: true } : r)); return null; }
    return translate(text, { ...opts, resolutions: { ...(opts.resolutions || {}), [repair.token_index]: option.gloss } });
  }, [translate]);

  const clear = useCallback(() => { setResult(null); setError(null); }, []);

  return { result, loading, error, translate, answerRepair, clear };
}
