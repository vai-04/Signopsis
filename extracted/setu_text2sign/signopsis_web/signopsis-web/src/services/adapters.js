// Backend output -> UI view models. The UI never reads raw trust numbers; it reads these.
/** @typedef {import("../contracts/contracts").RenderPlan} RenderPlan */
/** @typedef {import("../contracts/contracts").TrustState} TrustState */

export const TRUST = {
  high: {
    key: "high", label: "Clear", verb: "Shown",
    blurb: "Every sign checked out. The caption goes straight through.",
    color: "var(--color-moss)", ink: "var(--color-ink)",
  },
  enhanced: {
    key: "enhanced", label: "Enhanced", verb: "Shown, with help",
    blurb: "Clear because context, your answer or your own signs filled a gap.",
    color: "var(--color-sage)", ink: "var(--color-ink)",
  },
  repair: {
    key: "repair", label: "Checking", verb: "Asking you",
    blurb: "One part is uncertain. SIGNOPSIS asks instead of guessing.",
    color: "var(--color-coral)", ink: "var(--color-ink)",
  },
  hold: {
    key: "hold", label: "Held", verb: "Not shown",
    blurb: "Too little to go on. Nothing is shown until it can be read properly.",
    color: "var(--color-ink)", ink: "var(--color-light)",
  },
};

/** qualitative fill level for the trust bar (never displayed as a number) */
export const TRUST_LEVEL = { hold: 0.18, repair: 0.52, enhanced: 0.86, high: 1 };

/**
 * Map a backend gate + evidence to one of the four UI trust states.
 * ENHANCED is a UI state: the backend emitted, but only because context decoding,
 * a personal sign, or a user repair answer resolved something.
 * @param {"emit"|"repair"|"hold"} gate
 * @param {{slots?: any[], repaired?: boolean, frame?: any}} [ev]
 * @returns {TrustState}
 */
export function trustStateOf(gate, ev = {}) {
  if (gate === "hold") return "hold";
  if (gate === "repair") return "repair";
  const helped = ev.repaired
    || (ev.slots || []).some(s => s.source === "context" || s.source === "user" || s.kind === "personal")
    || (ev.frame?.entities || []).some(e => e.resolved_from === "context" || e.resolved_from === "user");
  return helped ? "enhanced" : "high";
}

export const captionOf = plan => plan?.targets?.find(t => t.kind === "caption") || null;
export const signOf = plan => plan?.targets?.find(t => t.kind === "sign") || null;
export const ttsOf = plan => plan?.targets?.find(t => t.kind === "tts") || null;

/** Friendly label for a gloss token (FS:PRIYA -> P-R-I-Y-A) */
export function glossLabel(item) {
  if (typeof item === "string") return item.startsWith("FS:") ? item.slice(3).split("").join("-") : item;
  if (item.fingerspelled) return (item.fs_fallback || item.g.replace(/^FS:/, "")).toUpperCase();
  return item.g;
}

/** qualitative confidence words for a single gloss (no percentages in the main UI) */
export function certaintyWord(p) {
  if (p == null) return "unchecked";
  if (p >= 0.85) return "solid";
  if (p >= 0.6) return "likely";
  return "shaky";
}

/**
 * A result event from /ws/sign -> caption card model.
 * @param {any} ev  `{type:"result", ...}`
 * @param {{speaker?: string, repaired?: boolean}} [opt]
 */
export function captionFromResult(ev, opt = {}) {
  const plan = ev.plan;
  const cap = captionOf(plan);
  const state = trustStateOf(ev.gate, { slots: ev.slots, repaired: opt.repaired, frame: ev.frame });
  return {
    id: plan.frame_id,
    speaker: opt.speaker || cap?.speaker_label || "Signer",
    channel: "sign",
    text: ev.text || "",
    draft: ev.draft || "",
    state,
    reason: plan.gate_reason,
    advisory: plan.advisory || null,
    repair: plan.repair || null,
    gloss: ev.frame?.gloss || ev.slots?.map(s => s.gloss) || [],
    slots: ev.slots || [],
    timings: plan.timings_ms || {},
    tts: ttsOf(plan),
    at: Date.now(),
  };
}

/** A /api/text-to-sign response -> compose/preview model */
export function composeFromResponse(res, text) {
  const plan = res.plan;
  const sign = signOf(plan);
  return {
    id: plan.frame_id,
    text,
    state: trustStateOf(plan.gate, { frame: res.frame }),
    gate: plan.gate,
    reason: plan.gate_reason,
    advisory: plan.advisory || null,
    repair: plan.repair || null,
    gloss: sign?.gloss || [],
    backTranslation: sign?.back_translation || "",
    readbackWord: certaintyWord(sign?.roundtrip_score),
    signLang: sign?.sign_lang || "isl",
    totalMs: sign?.total_ms || res.frames?.total_ms || 0,
    clip: res.frames,
    frame: res.frame,
    timings: plan.timings_ms || {},
  };
}

/** Human text for `live` HUD events */
export function liveHint(ev) {
  if (!ev) return null;
  if (ev.hint) return ev.hint;
  if (!ev.hands?.R && !ev.hands?.L) return "Hands not in view";
  return null;
}
