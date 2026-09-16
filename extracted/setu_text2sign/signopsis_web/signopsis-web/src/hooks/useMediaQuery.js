import { useEffect, useState } from "react";

export function useMediaQuery(q) {
  const [m, set] = useState(() => typeof window !== "undefined" && window.matchMedia(q).matches);
  useEffect(() => {
    const mq = window.matchMedia(q);
    const on = () => set(mq.matches);
    mq.addEventListener("change", on);
    on();
    return () => mq.removeEventListener("change", on);
  }, [q]);
  return m;
}

import { usePrefs } from "../services/prefs.js";

/** OS setting, overridable in Settings → Accessibility */
export function usePrefersReducedMotion() {
  const os = useMediaQuery("(prefers-reduced-motion: reduce)");
  const [p] = usePrefs();
  return p.motion === "reduce" ? true : p.motion === "full" ? false : os;
}
