"""Live sign -> text session (pipelines A and B up to the RenderPlan).

One SignSession per connected camera. It is transport-agnostic: the
WebSocket endpoint, the OpenCV client and the tests all drive it with
the same JSON messages.

  client -> session                     session -> client
  ----------------                      -----------------
  {"type":"frame", ...WireFrame}        {"type":"live", ...}         every few frames
  {"type":"repair_choice", ...}         {"type":"phrase_start"}
  {"type":"enroll_start", label}        {"type":"partial", gloss}    while signing
  {"type":"enroll_from_unknown", label} {"type":"result", percept, frame, plan, slots}
  {"type":"enroll_cancel"}              {"type":"enroll_progress" | "enrolled"}
  {"type":"forget_sign", label}         {"type":"teach_offer", ...}
  {"type":"config", out_lang, dominant} {"type":"signs", signs}
  {"type":"flush"} {"type":"reset"}     {"type":"error", message}
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from setu.fuse.trust import (COVERAGE_HOLD, COVERAGE_REPAIR, SlotSignals, TrustModel, gate_for, hold_reason,
                             thresholds)
from setu.memory.store import MemoryStore
from setu.perceive.landmarks import Normalizer, Obs
from setu.perceive.nonmanual import Baseline, analyse
from setu.perceive.recognizer import K, Index, dtw_many, dtw_open, resample, resample_batch
from setu.perceive.segment import (PhraseTracker, Prepared, Seg, decode_phrase, is_active, noise_floor,
                                   prepare, trim_edges, trim_travel)
from setu.resolve import vocab as V
from setu.resolve.sign_to_text import SlotIn, decode_context, high_stakes, realize
from setu.schemas import (CaptionTarget, Entity, Grounding, LatticeSlot, NonManual, PerceptEvent, Prosody,
                          Provenance, RenderPlan, Repair, RepairOption, SemanticFrame, TTSTarget,
                          Unresolved, WireFrame, new_id)

ENROLL_SHOTS = 4
PARTIAL_EVERY_MS = 900
LIVE_EVERY = 3
TEACH_SAME = 0.25            # above the noise floor
HOLD_BELOW_AMBIG = 0.40      # an unresolved slot's trust is capped at 0.40 + its context margin
ADVISORY = ("Medical / legal words detected. SETU is a supplement, not a replacement: "
            "please use a certified ISL interpreter for consent, diagnosis or legal matters.")


def normalise_label(text: str) -> str:
    t = re.sub(r"\s+", "-", text.strip().upper())
    t = re.sub(r"[^A-Z0-9\-]", "", t)
    if not t:
        raise ValueError("empty label")
    if t in V.CATEGORY:
        return t
    word = V.EN.get(text.strip().lower())
    if word:
        return word
    return "FS:" + t.replace("-", "")


def display_label(label: str) -> str:
    return label[3:].title() if label.startswith("FS:") else label


@dataclass
class Slot:
    seg: Optional[Seg]
    cands: list[tuple[str, float]]
    kind: str
    signals: SlotSignals
    visual_trust: float
    t: tuple[float, float]
    letters: str = ""
    negated: bool = False
    locked: Optional[str] = None
    span: tuple[int, int] = (0, 0)


def coverage(P: Prepared, slots: list[Slot]) -> float:
    """Share of active signing time explained by recognised slots (short transitions count)."""
    act = P.active.copy()
    if act.sum() == 0:
        return 1.0
    cov = np.zeros(len(act), dtype=bool)
    spans = sorted(sl.span for sl in slots if sl.kind != "unknown")
    for a, b in spans:
        cov[a:b] = True
    dt = float(np.median(np.diff(P.t))) if len(P.t) > 1 else 33.3
    gap = int(round(260 / dt))
    for (a0, b0), (a1, b1) in zip(spans, spans[1:]):
        if 0 < a1 - b0 <= gap:
            cov[b0:a1] = True
    # hands rising into / falling out of the signing space are not content
    idx = np.where(act)[0]
    a, b = trim_edges(P, int(idx[0]), int(idx[-1]) + 1, min_len=1)
    act[:a] = False
    act[b:] = False
    if act.sum() == 0:
        return 1.0
    return float((cov & act).sum() / act.sum())


@dataclass
class Pending:
    frame_id: str
    percept: PerceptEvent
    slots: list[Slot]
    nm: object
    lux: Optional[float]
    t_end: float
    extra: dict = field(default_factory=dict)


class SignSession:
    def __init__(self, user: str = "default", store: Optional[MemoryStore] = None,
                 trust: Optional[TrustModel] = None, out_lang: str = "en", dominant: str = "right"):
        self.user = user
        self.store = store or MemoryStore()
        self.trust = trust or TrustModel()
        self.out_lang = out_lang
        self.dominant = dominant
        self.baseline = Baseline()
        self.history: list[list[str]] = []
        self.pending: Optional[Pending] = None
        self.unknowns: list[tuple[np.ndarray, float, float, np.ndarray]] = []   # (Q, dur, t, raw F)
        self.enroll: Optional[dict] = None
        self.last_partial_t = -1e9
        self.n_frames = 0
        self.reset()
        self._reload_index()

    # ------------------------------------------------------------ plumbing
    def reset(self):
        self.norm = Normalizer(dominant=self.dominant)
        self.tracker = PhraseTracker()
        self.pending = None

    def _reload_index(self):
        self.index = Index().with_user(self.store.load_prototypes(self.user))

    def hello(self) -> dict:
        return {"type": "hello", "user": self.user, "signs": self.store.list_signs(self.user),
                "config": {"out_lang": self.out_lang, "dominant": self.dominant},
                "vocabulary": sorted(g for g in self.index.labels if self.index.kind_of[g] == "sign")}

    def handle(self, msg: dict) -> list[dict]:
        try:
            kind = msg.get("type")
            if kind == "frame":
                return self._on_frame(WireFrame.model_validate(msg))
            if kind == "repair_choice":
                return self._on_repair(msg)
            if kind == "enroll_start":
                return self._enroll_start(msg.get("label", ""), [])
            if kind == "enroll_from_unknown":
                pre = [(q, d) for q, d, _, _ in self.unknowns[-2:]]
                self.unknowns.clear()
                return self._enroll_start(msg.get("label", ""), pre)
            if kind == "enroll_cancel":
                self.enroll = None
                return [{"type": "enroll_progress", "label": None, "have": 0, "need": ENROLL_SHOTS, "cancelled": True}]
            if kind == "forget_sign":
                n = self.store.delete_sign(self.user, normalise_label(msg.get("label", "")))
                self._reload_index()
                return [{"type": "signs", "signs": self.store.list_signs(self.user), "removed": n}]
            if kind == "list_signs":
                return [{"type": "signs", "signs": self.store.list_signs(self.user)}]
            if kind == "config":
                if msg.get("out_lang") in ("en", "hi"):
                    self.out_lang = msg["out_lang"]
                if msg.get("dominant") in ("right", "left") and msg["dominant"] != self.dominant:
                    self.dominant = msg["dominant"]
                    self.norm = Normalizer(dominant=self.dominant)
                return [{"type": "config", "out_lang": self.out_lang, "dominant": self.dominant}]
            if kind == "flush":
                ph = self.tracker.flush()
                return self._on_phrase(ph) if ph else []
            if kind == "reset":
                self.reset()
                self.history.clear()
                return [{"type": "reset"}]
            if kind == "hello":
                return [self.hello()]
            return [{"type": "error", "message": f"unknown message type {kind!r}"}]
        except ValueError as e:
            return [{"type": "error", "message": str(e)}]

    # ------------------------------------------------------------ frames
    def _on_frame(self, f: WireFrame) -> list[dict]:
        out = []
        obs = self.norm(f)
        self.n_frames += 1
        was = self.tracker.in_phrase
        ph = self.tracker.push(obs)
        if not self.tracker.in_phrase and not is_active(obs):
            self.baseline.update_face(obs)
        if self.tracker.in_phrase and not was:
            out.append({"type": "phrase_start", "t": obs.t, "enrolling": bool(self.enroll)})
            self.last_partial_t = obs.t
        if self.n_frames % LIVE_EVERY == 0:
            out.append(self._live(obs))
        if ph:
            out += self._on_phrase(ph)
        elif (self.tracker.in_phrase and not self.enroll and obs.t - self.last_partial_t >= PARTIAL_EVERY_MS
              and len(self.tracker.buf) <= 150):
            self.last_partial_t = obs.t
            segs = decode_phrase(prepare(self.tracker.buf), self.index, self.trust.tau)
            out.append({"type": "partial", "gloss": [s.labels[0][0] if s.kind != "unknown" else "?" for s in segs],
                        "t": obs.t})
        return out

    def _live(self, o: Obs) -> dict:
        hint = None
        if o.lux is not None and o.lux < 40:
            hint = "Too dark"
        elif not o.anchor_ok:
            hint = "Move back so your shoulders are visible"
        elif o.hands_present == 0 and self.tracker.in_phrase:
            hint = "Hands out of view"
        return {"type": "live", "t": o.t, "signing": self.tracker.in_phrase, "enrolling": bool(self.enroll),
                "hands": {"R": o.R is not None, "L": o.L is not None}, "anchor": o.anchor_ok,
                "lux": o.lux, "hint": hint,
                "brow": ("raised" if (o.brow_up or 0) - self.baseline.brow_up > 0.25 else
                         "furrowed" if (o.brow_down or 0) - self.baseline.brow_down > 0.25 else "neutral")}

    # ------------------------------------------------------------ phrases
    def _on_phrase(self, frames: list[Obs]) -> list[dict]:
        if self.enroll:
            return self._enroll_sample(frames)
        t0 = time.perf_counter()
        P = prepare(frames)
        segs = decode_phrase(P, self.index, self.trust.tau)
        t_dec = (time.perf_counter() - t0) * 1000
        nm = analyse(frames, self.baseline)
        luxes = [f.lux for f in frames if f.lux is not None]
        lux = float(np.mean(luxes)) if luxes else None
        anchor = np.array([f.anchor_ok for f in frames], dtype=float)
        active_ms = float(sum(1 for f in frames if is_active(f)) * (np.median(np.diff(P.t)) if len(P.t) > 1 else 33))

        slots = self._slots(P, segs, anchor, lux, nm)
        if not slots:
            span_ms = float(P.t[-1] - P.t[0]) if len(P.t) > 1 else 0.0
            bad_view = (lux is not None and lux < 40) or float(P.r_missing.mean()) > 0.4
            if active_ms < 400 and not (bad_view and span_ms >= 500):
                return []
            sig = self._signals(P, 0, len(P.t), anchor, lux, 0.0, 0.0, 0.0)
            code, msg = hold_reason(sig, lux)
            return [self._hold_only(msg, code, P, frames)]

        percept = PerceptEvent(
            t0=int(P.t[0]), t1=int(P.t[-1]), channel="sign", source="mediapipe+dtw-proto", lang_hint="isl",
            lattice=[LatticeSlot(slot=i, cands=[(g, round(p, 4)) for g, p in s.cands]) for i, s in enumerate(slots)],
            nonmanual=nm.phrase,
            quality={"landmark_vis": round(float(np.mean([s.signals.vis for s in slots])), 3),
                     "hand_overlap": round(float(np.mean([s.signals.overlap for s in slots])), 3),
                     "jitter": round(P.noise, 3), "lux_est": round(lux, 1) if lux is not None else -1,
                     "anchor": round(float(anchor.mean()), 3)},
            trust=round(min(s.visual_trust for s in slots), 4), partial=False)
        percept.quality["coverage"] = round(coverage(P, slots), 3)
        self.pending = Pending(new_id("sf"), percept, slots, nm, lux, float(P.t[-1]),
                               {"t_decode": t_dec, "t0": t0})
        # unknown sign bookkeeping -> teach offer
        extra = self._track_unknowns(slots, P)
        return [self._resolve(self.pending)] + extra

    def _signals(self, P: Prepared, a: int, b: int, anchor, lux, margin, dis, nov) -> SlotSignals:
        ov = P.overlap[a:b]
        ov = float(np.nanmean(ov)) if np.any(~np.isnan(ov)) else 0.0
        dark = float(np.clip((80 - lux) / 60, 0, 1)) if lux is not None else 0.0
        return SlotSignals(margin=float(margin), vis=float(1 - P.r_missing[a:b].mean()), overlap=ov,
                           jitter=float(P.noise), dark=dark, anchor=float(anchor[a:b].mean()),
                           disagreement=float(dis), novelty=float(nov))

    def _slots(self, P, segs: list[Seg], anchor, lux, nm) -> list[Slot]:
        slots: list[Slot] = []
        i = 0
        while i < len(segs):
            s = segs[i]
            if s.kind == "letter":
                run = [s]
                while i + 1 < len(segs) and segs[i + 1].kind == "letter":
                    i += 1
                    run.append(segs[i])
                word = "".join(r.labels[0][0] for r in run)
                p = float(min(r.labels[0][1] for r in run))
                a, b = run[0].a, run[-1].b
                margin = float(np.mean([r.labels[0][1] - (r.labels[1][1] if len(r.labels) > 1 else 0) for r in run]))
                sig = self._signals(P, a, b, anchor, lux, margin,
                                    float(np.mean([r.disagreement for r in run])),
                                    float(max(r.d_best / r.extra["novel_d"] for r in run)))
                sig.fs = 1.0
                known = V.EN.get(word.lower())          # fingerspelled a word we have a gloss for
                cands = [(known if known else "FS:" + word, p)]
                if len(run) == 1:          # a lone "letter" is more often a mis-segmented sign
                    sig.margin = 0.0
                    sig.novelty = max(sig.novelty, 0.95)
                slots.append(Slot(None, cands, "fs", sig, self.trust.trust(sig), (run[0].t0, run[-1].t1), word,
                                  span=(a, b)))
            else:
                margin = s.labels[0][1] - (s.labels[1][1] if len(s.labels) > 1 else 0.0)
                sig = self._signals(P, s.a, s.b, anchor, lux, margin, s.disagreement, s.d_best / s.extra["novel_d"])
                cands = [(g, p) for g, p in s.labels if self.index.kind_of.get(g) != "letter"] or s.labels
                slots.append(Slot(s, cands, s.kind, sig, self.trust.trust(sig), (s.t0, s.t1), span=(s.a, s.b)))
            i += 1
        # an "unknown" span that is mostly dropout, or a short one at the phrase edge,
        # is noise (hands coming up / going down), not a sign we should ask about
        keep = []
        for k, sl in enumerate(slots):
            if sl.kind == "unknown":
                beside_fs = any(0 <= j < len(slots) and slots[j].kind == "fs" for j in (k - 1, k + 1))
                if beside_fs:
                    keep.append(sl)
                    continue
                dur = sl.t[1] - sl.t[0]
                if sl.signals.vis < 0.7:      # mostly dropout: not worth a "teach me" (coverage still counts it)
                    continue
            keep.append(sl)
        slots = keep
        for sl in slots:
            sl.negated = any(a <= (sl.t[0] + sl.t[1]) / 2 <= b for a, b in nm.shake_spans)
        return slots

    def _track_unknowns(self, slots: list[Slot], P: Prepared) -> list[dict]:
        out = []
        nu = noise_floor(P.noise)
        for sl in slots:
            if sl.kind != "unknown" or sl.seg is None:
                continue
            Q, dur, F = sl.seg.extra["Q"], sl.seg.extra["dur"], sl.seg.extra["F"]
            if self.unknowns:
                D = np.array([dtw_open(F, u[3]) for u in self.unknowns])
                self._last_unknown_d = (float(D.min()), nu)
                if D.min() < 2 * nu + TEACH_SAME:
                    j = int(D.argmin())
                    keep = self.unknowns[j]
                    self.unknowns = [keep, (Q, dur, sl.t[0], F)]
                    out.append({"type": "teach_offer", "samples": 2, "need": ENROLL_SHOTS,
                                "prompt": "You've used a sign I don't know twice. Teach it to me?"})
                    continue
            self.unknowns = (self.unknowns + [(Q, dur, sl.t[0], F)])[-6:]
        return out

    # ------------------------------------------------------------ resolution + gate
    def _resolve(self, pend: Pending) -> dict:
        t1 = time.perf_counter()
        slots = pend.slots
        hist = [g for fr in self.history[-2:] for g in fr]
        ins = [SlotIn(cands=s.cands if s.kind != "unknown" else [("?", 1.0)], percept_id=pend.percept.id,
                      t=s.t, kind=s.kind, negated=s.negated, locked=s.locked) for s in slots]
        ctx = decode_context(ins, hist, jargon=lambda c, l, r: self.store.jargon_bonus(self.user, c, l, r))
        trusts = []
        for i, s in enumerate(slots):
            if s.locked:
                trusts.append(1.0)
            elif s.kind == "unknown":
                trusts.append(min(0.25, self.trust.trust(s.signals, margin=ctx.margins[i])))
            else:
                t = self.trust.trust(s.signals, margin=ctx.margins[i])
                if i in ctx.unresolved:
                    # still ambiguous after context: never let it through as if it were sure
                    t = min(t, HOLD_BELOW_AMBIG + ctx.margins[i])
                trusts.append(t)
        gloss = ctx.gloss
        neg_slots = {i for i, s in enumerate(slots) if s.negated}
        face_q = pend.nm.question
        text, spans, info = realize(gloss, face_q, neg_slots, self.out_lang)
        hs = high_stakes(gloss)
        emit_at, hold_at = thresholds(hs)
        weakest = int(np.argmin(trusts))
        min_t = trusts[weakest]
        gate = gate_for(min_t, hs)
        repair = None
        reason = ""
        cov = pend.percept.quality.get("coverage", 1.0)
        unknown_i = next((i for i, s in enumerate(slots) if s.kind == "unknown" and not s.locked), None)
        bad_view = None
        if unknown_i is not None:
            code, msg = hold_reason(slots[unknown_i].signals, pend.lux)
            if code not in ("unknown", "unsure"):
                bad_view = msg                 # can't tell "new sign" from "bad view": fix the view first
        if bad_view:
            gate, weakest, reason = "hold", unknown_i, bad_view
            repair = Repair(type="resign", slot=unknown_i, prompt=bad_view,
                            options=[RepairOption(gloss="__none__", label="OK")])
        elif unknown_i is not None:
            gate = "hold"
            weakest = unknown_i
            reason = "I don't know one of those signs yet."
            repair = Repair(type="resign", slot=weakest, prompt=reason + " Sign it again, fingerspell it, or teach it to me.",
                            options=[RepairOption(gloss="__teach__", label="Teach me this sign"),
                                     RepairOption(gloss="__none__", label="Dismiss")])
        elif cov < COVERAGE_HOLD and not any(s.locked for s in slots):
            gate = "hold"
            code, msg = hold_reason(slots[weakest].signals, pend.lux)
            reason = msg if code not in ("unknown", "unsure") else \
                f"I only caught part of that ({cov:.0%}). Please sign it again."
            repair = Repair(type="resign", slot=-1, prompt=reason, options=[RepairOption(gloss="__none__", label="OK")])
        elif gate == "hold":
            code, msg = hold_reason(slots[weakest].signals, pend.lux)
            reason = msg
            repair = Repair(type="resign", slot=weakest, prompt=msg,
                            options=[RepairOption(gloss="__none__", label="OK")])
        elif gate == "repair":
            post = ctx.post[weakest]
            if slots[weakest].kind != "fs" and len(post) >= 2 and post[1][1] > 0.02:
                a, b = post[0][0], post[1][0]
                reason = f"Slot {weakest + 1} could be {display_label(a)} or {display_label(b)} (trust {min_t:.2f})."
                repair = Repair(type="disambiguate", slot=weakest, prompt="Which sign did you mean?",
                                options=[RepairOption(gloss=a, label=_opt_label(a), clip=_clip(a)),
                                         RepairOption(gloss=b, label=_opt_label(b), clip=_clip(b)),
                                         RepairOption(gloss="__none__", label="Neither")])
            else:
                reason = f"Not sure about slot {weakest + 1} (trust {min_t:.2f})."
                repair = Repair(type="resign", slot=weakest, prompt="I'm not sure I got that. Please sign it again.",
                                options=[RepairOption(gloss="__accept__", label="It's right"),
                                         RepairOption(gloss="__none__", label="Sign again")])
        elif cov < COVERAGE_REPAIR and not any(s.locked for s in slots):
            gate = "repair"
            reason = f"I may have missed a sign ({cov:.0%} of the signing understood)."
            repair = Repair(type="resign", slot=-1, prompt="Did I get all of that?",
                            options=[RepairOption(gloss="__accept__", label="Yes, that's everything"),
                                     RepairOption(gloss="__none__", label="No, I'll sign it again")])
        else:
            reason = f"All {len(slots)} signs trusted (min {min_t:.2f} ≥ {emit_at:.2f}), coverage {cov:.0%}."

        # grounding: every output span points at percept + slot time range
        grounding = []
        for a, b, ids in spans:
            if not ids:
                continue
            tt = (int(min(slots[i].t[0] for i in ids)), int(max(slots[i].t[1] for i in ids)))
            grounding.append(Grounding(span=(a, b), percept_ids=[pend.percept.id], t=tt, gloss_index=ids[0]))
        entities = []
        for i, s in enumerate(slots):
            alts = [g for g, _ in ctx.post[i][1:]]
            if ctx.sources[i] != "lattice" or s.kind == "fs" or (alts and ctx.margins[i] < 0.9):
                entities.append(Entity(text=display_label(gloss[i]), type="proper" if s.kind == "fs" else "sign",
                                       resolved_from={"user": "user", "context": "context"}.get(
                                           ctx.sources[i], "fingerspell" if s.kind == "fs" else "lattice"),
                                       alternatives=[display_label(a) for a in alts], margin=round(ctx.margins[i], 3)))
        unresolved = [Unresolved(slot=i, cands=[g for g, _ in ctx.post[i][:2]], reason="low_margin",
                                 token_index=i) for i in ctx.unresolved if trusts[i] < emit_at]
        prosody = pend.nm.prosody
        if gate != "emit" or prosody.conf < 0.5:
            prosody = Prosody(affect="neutral", intensity=prosody.intensity, pace=prosody.pace, conf=prosody.conf)
        frame = SemanticFrame(
            id=pend.frame_id, utterance=text, lang=self.out_lang, speech_act=info["speech_act"],
            question_type=info["question_type"], negated=info["negated"], entities=entities,
            prosody=prosody, grounding=grounding, unresolved=unresolved, gloss=gloss, high_stakes=hs,
            trust=round(min_t, 4), provenance=Provenance(resolver=f"ctx-viterbi+rules-{self.out_lang}"))
        badge = "high" if min_t >= emit_at else "medium" if min_t >= hold_at else "low"
        targets = [CaptionTarget(lang=self.out_lang, text=text if gate != "hold" else "", trust_badge=badge,
                                 speaker_label="Signer")]
        if gate == "emit":
            rate = {"fast": 1.15, "slow": 0.9}.get(prosody.pace, 1.0)
            pitch = 1.1 if prosody.affect == "urgent" else 1.0
            targets.append(TTSTarget(lang=self.out_lang, text=text, rate=rate, pitch=pitch,
                                     volume=min(1.0, 0.8 + 0.2 * prosody.intensity)))
        timings = {"decode": round(pend.extra.get("t_decode", 0), 1),
                   "resolve": round((time.perf_counter() - t1) * 1000, 1),
                   "total": round((time.perf_counter() - pend.extra["t0"]) * 1000, 1)}
        plan = RenderPlan(frame_id=frame.id, gate=gate, gate_reason=reason, targets=targets, repair=repair,
                          advisory=ADVISORY if hs else None, timings_ms=timings)
        if gate == "emit":
            self.history.append(gloss)
            self.history = self.history[-5:]
        slot_view = [{"gloss": gloss[i], "display": display_label(gloss[i]), "kind": s.kind,
                      "trust": round(trusts[i], 3), "visual_trust": round(s.visual_trust, 3),
                      "source": ctx.sources[i], "post": [(g, round(p, 3)) for g, p in ctx.post[i]],
                      "ctx_margin": round(ctx.margins[i], 4),
                      "visual": [(g, round(p, 3)) for g, p in s.cands], "negated": s.negated,
                      "t": [int(s.t[0]), int(s.t[1])], "signals": s.signals.to_dict()}
                     for i, s in enumerate(slots)]
        return {"type": "result", "text": text if gate != "hold" else "", "draft": text, "gate": gate,
                "slots": slot_view,
                "percept": pend.percept.model_dump(mode="json"),
                "frame": frame.model_dump(mode="json"), "plan": plan.model_dump(mode="json")}

    def _hold_only(self, msg, code, P, frames) -> dict:
        fid = new_id("sf")
        plan = RenderPlan(frame_id=fid, gate="hold", gate_reason=msg,
                          targets=[CaptionTarget(lang=self.out_lang, text="", trust_badge="low", speaker_label="Signer")],
                          repair=Repair(type="resign", slot=-1, prompt=msg, options=[RepairOption(gloss="__none__", label="OK")]))
        return {"type": "result", "text": "", "gate": "hold", "slots": [], "reason_code": code,
                "percept": None, "frame": None, "plan": plan.model_dump(mode="json")}

    # ------------------------------------------------------------ repair
    def _on_repair(self, msg: dict) -> list[dict]:
        pend = self.pending
        if pend is None or (msg.get("frame_id") and msg["frame_id"] != pend.frame_id):
            return [{"type": "error", "message": "nothing to repair (the phrase has expired)"}]
        slot = int(msg.get("slot", -1))
        choice = msg.get("choice")
        if choice == "__none__":
            self.pending = None
            return [{"type": "repair_done", "frame_id": pend.frame_id, "outcome": "dismissed"}]
        if choice == "__teach__":
            s = pend.slots[slot] if 0 <= slot < len(pend.slots) else None
            if s is not None and s.seg is not None:
                self.unknowns = [(s.seg.extra["Q"], s.seg.extra["dur"], s.t[0], s.seg.extra["F"])]
            return [{"type": "teach_offer", "samples": len(self.unknowns), "need": ENROLL_SHOTS,
                     "prompt": "What does this sign mean?"}]
        if choice == "__accept__" and slot == -1:
            for x in pend.slots:
                x.locked = x.locked or x.cands[0][0]
            pend.extra["t0"] = time.perf_counter()
            return [self._resolve(pend)]
        if not (0 <= slot < len(pend.slots)):
            return [{"type": "error", "message": "bad slot"}]
        s = pend.slots[slot]
        if choice == "__accept__":
            s.locked = s.cands[0][0]
        else:
            s.locked = normalise_label(choice) if not str(choice).startswith("FS:") else choice
            # remember the choice in context so next time it isn't asked
            ins = [SlotIn(cands=x.cands, percept_id="", t=x.t, kind=x.kind, locked=x.locked) for x in pend.slots]
            ctx = decode_context(ins)
            left = ctx.gloss[slot - 1] if slot > 0 else None
            right = ctx.gloss[slot + 1] if slot + 1 < len(ctx.gloss) else None
            cands = [g for g, _ in s.cands[:2]]
            if s.locked not in cands:
                cands = [s.locked] + cands[:1]
            self.store.record_choice(self.user, cands, s.locked, left, right)
        pend.extra["t0"] = time.perf_counter()
        pend.extra["t_decode"] = 0.0
        return [self._resolve(pend)]

    # ------------------------------------------------------------ enrollment (section 09)
    def _enroll_start(self, label: str, pre: list) -> list[dict]:
        norm = normalise_label(label)
        self.enroll = {"label": norm, "display": label.strip(), "samples": list(pre)}
        return [{"type": "enroll_progress", "label": norm, "display": label.strip(),
                 "have": len(pre), "need": ENROLL_SHOTS}]

    def _enroll_sample(self, frames: list[Obs]) -> list[dict]:
        P = prepare(frames)
        act = np.where(P.active)[0]
        if len(act) < 5:
            return [{"type": "enroll_progress", "label": self.enroll["label"], "have": len(self.enroll["samples"]),
                     "need": ENROLL_SHOTS, "warning": "That was too short. Please sign it again."}]
        a, b = int(act[0]), int(act[-1]) + 1
        a, b = trim_travel(P, a, b, min_len=6)    # skip hands coming up / going down
        # a teaching sample must be ONE sign: reject phrases the recognizer reads as several known signs
        known = [sg for sg in decode_phrase(P, self.index, self.trust.tau)
                 if sg.kind != "unknown" and sg.labels[0][1] > 0.8]
        too_long = (P.t[b - 1] - P.t[a]) > 2500
        if len(known) >= 2 or too_long:
            return [{"type": "enroll_progress", "label": self.enroll["label"], "display": self.enroll["display"],
                     "have": len(self.enroll["samples"]), "need": ENROLL_SHOTS,
                     "warning": "That looked like more than one sign. Sign only the new sign, then lower your hands."}]
        Q = resample_batch(P.F, np.array([a]), np.array([b]), K)[0]
        dur = float(P.t[b - 1] - P.t[a] + 33.3)
        self.enroll["samples"].append((Q, dur))
        have = len(self.enroll["samples"])
        if have < ENROLL_SHOTS:
            return [{"type": "enroll_progress", "label": self.enroll["label"], "display": self.enroll["display"],
                     "have": have, "need": ENROLL_SHOTS}]
        e = self.enroll
        self.enroll = None
        # consistency check: samples should agree with each other
        S = np.stack([q for q, _ in e["samples"]])
        D = dtw_many(S, S)
        spread = float(D[np.triu_indices(len(S), 1)].mean())
        n = self.store.add_sign(self.user, e["label"], [q for q, _ in e["samples"]], [d for _, d in e["samples"]],
                                display=e["display"])
        self._reload_index()
        return [{"type": "enrolled", "label": e["label"], "display": e["display"], "prototypes": n,
                 "consistency": round(spread, 3),
                 "warning": "Your four samples looked quite different from each other." if spread > 0.6 else None},
                {"type": "signs", "signs": self.store.list_signs(self.user)}]


def _opt_label(g: str) -> str:
    if g.startswith("FS:"):
        return g[3:].title()
    return V.BACK_GLOSS.get(g, g.lower().replace("-", " "))


def _clip(g: str) -> Optional[str]:
    from setu.generate.signs import LEXICON
    return f"/api/sign/{g}" if g in LEXICON else None
