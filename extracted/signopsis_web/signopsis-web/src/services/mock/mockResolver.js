// In-browser stand-in for the backend's rule resolver (setu/resolve/rules.py + pipeline.text_to_sign).
// ONLY used in mock mode, for sentences that aren't in the recorded fixtures. It follows the same ISL
// ordering rules (time first, verb last, NOT after the verb, wh-word last) and emits the exact
// response shape of POST /api/text-to-sign, so every screen behaves the same with or without a server.
import V from "../../mocks/vocab.json";
import BANK from "../../mocks/sign_bank.json";
import { composeClip } from "./clipComposer.js";

const DEVANAGARI = /[ऀ-ॿ]/;
const TOKEN_RE = /[ऀ-ॿ]+|[A-Za-z]+(?:'[A-Za-z]+)?|\d+|[?!.,]/g;
const EMIT_AT = 0.75, HOLD_BELOW = 0.40, HIGH_STAKES_AT = 0.85;
const DUR = g => (BANK.signs[g] ? Math.round((BANK.signs[g].length - 1) * (1000 / BANK.fps)) : 500);

let seq = 0;
const rid = p => `${p}_${(Date.now().toString(16) + (++seq).toString(16)).slice(-12).padStart(12, "0")}`;

function tokenize(text) {
  const toks = [];
  let m;
  TOKEN_RE.lastIndex = 0;
  while ((m = TOKEN_RE.exec(text))) {
    const t = m[0];
    const kind = /^[?!.,]$/.test(t) ? "punct" : /^\d+$/.test(t) ? "num" : "word";
    const low = t.toLowerCase();
    if (kind === "word" && V.CONTRACTIONS[low]) {
      const parts = V.CONTRACTIONS[low].split(" ");
      parts.forEach(p => toks.push({ text: p, kind, span: [m.index, m.index + t.length] }));
    } else toks.push({ text: t, kind, span: [m.index, m.index + t.length] });
  }
  return toks;
}

export function detectLang(toks) {
  let hi = 0, en = 0;
  for (const t of toks) {
    if (t.kind !== "word") continue;
    const w = t.text.toLowerCase();
    if (DEVANAGARI.test(w)) t.lang = "hi";
    else if ((w in V.HI || w in V.HI_AMBIGUOUS || V.STOP_HI.includes(w)) && !(w in V.EN) && !V.STOP_EN.includes(w)) t.lang = "hi";
    else t.lang = "en";
    hi += t.lang === "hi"; en += t.lang === "en";
  }
  if (hi && en) return Math.min(hi, en) / (hi + en) >= 0.2 ? "hi-en" : hi > en ? "hi" : "en";
  return hi ? "hi" : "en";
}

function lookup(toks, lang) {
  const out = [];
  for (let i = 0; i < toks.length; i++) {
    const t = toks[i];
    if (t.kind === "punct") { out.push({ punct: t.text, span: t.span }); continue; }
    if (t.kind === "num") { out.push({ g: `FS:${t.text}`, fs: true, span: t.span, word: t.text }); continue; }
    const w = t.text.toLowerCase();
    // multi-word English phrases
    const two = i + 1 < toks.length ? `${w} ${toks[i + 1].text.toLowerCase()}` : null;
    if (two && V.PHRASES_EN[two]) {
      V.PHRASES_EN[two].forEach(g => out.push({ g, span: [t.span[0], toks[i + 1].span[1]], word: two }));
      i++; continue;
    }
    if (V.PHRASES_EN[w]) { V.PHRASES_EN[w].forEach(g => out.push({ g, span: t.span, word: w })); continue; }
    const isHi = t.lang === "hi" || (lang !== "en" && DEVANAGARI.test(w));
    if (isHi && V.HI_AMBIGUOUS[w]) { out.push({ amb: V.HI_AMBIGUOUS[w], span: t.span, word: w }); continue; }
    const g = isHi ? (V.HI[w] ?? V.EN[w]) : (V.EN[w] ?? (lang !== "en" ? V.HI[w] : undefined));
    if (g === null) continue;                                   // explicit "drop"
    if (g) { out.push({ g, span: t.span, word: w, neg: g === "NOT" }); continue; }
    if ((isHi ? V.STOP_HI : V.STOP_EN).includes(w) || V.STOP_EN.includes(w) || V.YESNO_STARTERS.includes(w)
        || V.FUTURE_MARKERS.includes(w) || V.PAST_FORMS.includes(w) || V.HI_PAST.includes(w) || V.HI_FUTURE.includes(w)) {
      out.push({ marker: w, span: t.span }); continue;
    }
    // unknown content word -> fingerspell
    out.push({ g: `FS:${t.text.toUpperCase()}`, fs: true, span: t.span, word: w });
  }
  return out;
}

function orderClause(items) {
  const cat = g => (g.startsWith("FS:") ? "NOUN" : V.CATEGORY[g] || "NOUN");
  const phr = [], time = [], rest = [], verbs = [], neg = [], wh = [], aspect = [];
  for (const it of items) {
    const c = cat(it.g);
    if (c === "PHRASE" && it.g !== "PLEASE") phr.push(it);
    else if (c === "TIME") time.push(it);
    else if (c === "WH") wh.push(it);
    else if (c === "NEG" && it.g === "NOT") neg.push(it);
    else if (c === "VERB") verbs.push(it);
    else if (c === "ASPECT") aspect.push(it);
    else rest.push(it);
  }
  return [...phr, ...time, ...rest, ...verbs, ...aspect, ...neg, ...wh];
}

export function mockTextToSign({ text, resolutions = {}, sign_lang = "isl", src_lang }) {
  const t0 = performance.now();
  const toks = tokenize(text);
  const lang = src_lang && src_lang !== "auto" ? src_lang : detectLang(toks);
  const items = lookup(toks, lang);
  const lower = text.toLowerCase();
  const past = toks.some(t => V.PAST_FORMS.includes(t.text.toLowerCase()) || V.HI_PAST.includes(t.text.toLowerCase()));
  const future = toks.some(t => V.FUTURE_MARKERS.includes(t.text.toLowerCase()) || V.HI_FUTURE.includes(t.text.toLowerCase()));

  // ambiguity ("kal"): tense decides, otherwise ask
  const unresolved = [];
  items.forEach((it, i) => {
    if (!it.amb) return;
    const chosen = resolutions[i] ?? resolutions[String(i)] ?? (past ? it.amb[0] : future ? it.amb[1] : null);
    if (chosen) { it.g = chosen; it.ctx = !(i in resolutions || String(i) in resolutions); }
    else { it.g = it.amb[0]; unresolved.push({ slot: -1, cands: it.amb, reason: "lexical_ambiguity", source_text: it.word, token_index: i }); }
  });

  // clauses on sentence punctuation
  const clauses = [[]];
  for (const it of items) {
    if (it.punct) { if (".?!".includes(it.punct) && clauses.at(-1).length) clauses.push([]); continue; }
    if (it.g) clauses.at(-1).push(it);
  }
  const ordered = clauses.filter(c => c.length).flatMap(orderClause);
  const glossStr = ordered.map(o => o.g);
  unresolved.forEach(u => { u.slot = ordered.findIndex(o => o.amb && o.word === u.source_text); });

  const hasWh = ordered.some(o => V.CATEGORY[o.g] === "WH");
  const yesno = !hasWh && (/\?\s*$/.test(text) && V.YESNO_STARTERS.includes(toks[0]?.text.toLowerCase()) || lower.startsWith("kya "));
  const question_type = hasWh ? "wh" : yesno ? "yesno" : null;
  const negated = ordered.some(o => o.g === "NOT");
  const highStakes = ordered.some(o => V.HIGH_STAKES.includes(o.g)) || toks.some(t => V.HIGH_STAKES_WORDS.includes(t.text.toLowerCase()));

  // trust: fingerspelled content words and unresolved words cost confidence
  const fsCount = ordered.filter(o => o.fs).length;
  const fsRatio = ordered.length ? fsCount / ordered.length : 1;
  let trust = ordered.length ? 0.97 - 0.5 * Math.max(0, fsRatio - 0.2) : 0.1;
  if (unresolved.length) trust = Math.min(trust, 0.55);
  trust = Math.round(trust * 100) / 100;
  const need = highStakes ? HIGH_STAKES_AT : EMIT_AT;

  const glossItems = ordered.map(o => {
    const fs = !!o.fs || !BANK.signs[o.g];
    const letters = o.g.replace(/^FS:/, "");
    return {
      g: o.g, dur_ms: fs ? BANK.fs_ms * letters.length : DUR(o.g),
      fs_fallback: letters.split("").join("-"), fingerspelled: fs, conf: fs ? 0.8 : 1,
      roundtrip: fs ? 0.72 : 0.95 + ((o.g.length * 7) % 5) / 100, source_span: o.span,
    };
  });
  const rt = glossItems.length ? Math.min(...glossItems.map(g => g.roundtrip)) : 0;

  const frame_id = rid("sf");
  let gate = "emit", gate_reason = `Trust ${trust.toFixed(2)} ≥ ${need}.`, repair = null;
  if (!ordered.length) {
    gate = "hold"; gate_reason = "Nothing I can sign in that text.";
  } else if (unresolved.length) {
    const u = unresolved[0];
    gate = "repair"; gate_reason = `"${u.source_text}" could mean ${u.cands.join(" or ")}.`;
    repair = { type: "disambiguate", slot: u.slot, token_index: u.token_index, prompt: `Which did you mean by "${u.source_text}"?`,
      options: u.cands.map(g => ({ gloss: g, label: g.toLowerCase(), clip: `/api/sign/${g}` })) };
  } else if (trust < HOLD_BELOW) {
    gate = "hold"; gate_reason = `Trust ${trust.toFixed(2)} < ${HOLD_BELOW}.`;
  } else if (trust < need) {
    gate = "repair"; gate_reason = `Trust ${trust.toFixed(2)} < ${need}: confirm the preview before sending.`;
    repair = { type: "confirm", slot: -1, token_index: -1, prompt: "The signing may be unclear. Send anyway?",
      options: [{ gloss: "SEND", label: "Send as shown", clip: null }, { gloss: "REPHRASE", label: "Let me rephrase", clip: null }] };
  }

  const nonmanual = [{ t: 0, brow: question_type === "yesno" ? "raised" : "neutral", head: "neutral", mouth: "neutral" }];
  const clip = composeClip(glossItems, { question_type, negated });
  if (question_type === "wh") nonmanual.push({ t: Math.max(0, clip.total_ms - 900), brow: "furrowed", head: "tilt_fwd", mouth: null });
  const back = glossStr.map(g => (V.BACK_GLOSS[g] ?? (g.startsWith("FS:") ? g.slice(3).toLowerCase() : g.toLowerCase()))).join(" · ");
  const outLang = lang === "hi" ? "hi" : "en";
  const plan = {
    frame_id, gate, gate_reason,
    targets: [
      { kind: "caption", lang: outLang, text, trust_badge: trust >= need ? "high" : trust >= HOLD_BELOW ? "medium" : "low", forced: outLang !== "en", speaker_label: "You" },
      { kind: "sign", sign_lang, gloss: glossItems, nonmanual, affect: "neutral", roundtrip_score: Math.round(rt * 100) / 100, back_translation: back, total_ms: clip.total_ms },
    ],
    repair,
    advisory: highStakes ? "Medical / legal context: double-check anything important with a qualified interpreter." : null,
    timings_ms: { resolve: +(performance.now() - t0).toFixed(1), "plan+roundtrip": 0, total: +(performance.now() - t0).toFixed(1) },
  };
  const frame = {
    id: frame_id, utterance: text, lang, speech_act: question_type ? "question" : "statement", question_type, negated,
    entities: ordered.filter(o => o.ctx).map(o => ({ text: o.word, type: "time", resolved_from: "context", alternatives: o.amb || [], margin: 0.6 })),
    prosody: { affect: "neutral", intensity: 0.3, emphasis: [], pace: "normal", conf: 0.8 },
    grounding: ordered.map((o, i) => ({ span: o.span, percept_ids: [], t: [0, 0], gloss_index: i })),
    unresolved, gloss: glossStr, high_stakes: highStakes, trust, provenance: { resolver: "mock-rules-isl", escalated_to_cloud: false },
  };
  const readback = glossItems.map((g, i) => ({ slot: i, cands: [[g.g, g.roundtrip]] }));
  return { frame, plan, readback, frames: clip };
}
