import { useEffect, useState } from "react";
import { backend } from "../services/backend.js";
import { SIGN_LANGS } from "../services/speech.js";
import { useBackend } from "./useBackend.js";

/** Sign languages with their live status: "ready" if the server has a lexicon pack (GET /api/lexicon → sign_langs). */
export function useSignLangs() {
  const b = useBackend();
  const [ready, setReady] = useState(["isl"]);
  useEffect(() => {
    let alive = true;
    backend.lexicon().then(l => alive && setReady(l.sign_langs?.length ? l.sign_langs : ["isl"])).catch(() => {});
    return () => { alive = false; };
  }, [b.resolved]);
  return SIGN_LANGS.map(s => ({ ...s, status: ready.includes(s.code) ? "ready" : "pack" }));
}
