// Per-device UI preferences (localStorage, with safe fallbacks).
import { useEffect, useState } from "react";

const KEY = "signopsis.prefs";
const DEFAULTS = { motion: "system", textSize: "normal", dominant: "right", captionLang: "en", voice: true, contrast: false };
const listeners = new Set();

function load() {
  try { return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) || "{}") }; } catch { return { ...DEFAULTS }; }
}
let prefs = load();

export function applyPrefs(p = prefs) {
  const el = document.documentElement;
  el.dataset.textsize = p.textSize;
  el.dataset.contrast = p.contrast ? "high" : "normal";
}

export function setPrefs(patch) {
  prefs = { ...prefs, ...patch };
  try { localStorage.setItem(KEY, JSON.stringify(prefs)); } catch { /* storage blocked */ }
  applyPrefs();
  listeners.forEach(f => f(prefs));
}

export function getPrefs() { return prefs; }

export function usePrefs() {
  const [p, set] = useState(prefs);
  useEffect(() => { listeners.add(set); return () => listeners.delete(set); }, []);
  return [p, setPrefs];
}

export function resetPrefs() {
  try { localStorage.removeItem(KEY); } catch { /* ignore */ }
  prefs = { ...DEFAULTS };
  applyPrefs();
  listeners.forEach(f => f(prefs));
}
