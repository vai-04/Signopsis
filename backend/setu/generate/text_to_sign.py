"""L3 + L4 for the sign direction: text -> ISL gloss -> round-trip gate -> RenderPlan.

    text -> [isl_rules (+ optional LLM reorder)] SemanticFrame
         -> [gloss_planner] SignTarget -> [roundtrip gate] -> [trust gate] RenderPlan
         -> (avatar landmark frames for the client)

Used by pipeline C (emitted speech captions, `serve/ws_session.py`) and
pipeline D (Compose: `compose.text` and `POST /api/text-to-sign`).
Pure CPU; callers run it off the event loop.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Optional

from .. import config
from ..clock import Stopwatch
from ..config import Settings
from ..fuse.gate import decide, thresholds
from ..resolve import highstakes
from ..resolve import isl_vocab as V
from ..resolve.gloss_llm import chat_call, reorder
from ..resolve.isl_rules import text_to_frame
from ..resolve.router import needs_llm_gloss
from ..schemas import (CaptionTarget, Grounding, LatticeSlot, PerceptEvent, RenderPlan, Repair, RepairOption,
                       SemanticFrame, SignTarget)
from . import roundtrip as RT
from .avatar2d import build_timeline, frames_json
from .gloss_planner import back_translate, fix_fingerspelled_durations, nonmanual_track, plan_sign

log = logging.getLogger("setu.text_to_sign")

# One CPU worker keeps sign plans in order and off the event loop and the GPU thread.
SIGN_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="setu-sign")

ADVISORY = ("Medical or legal words detected. SETU is not a certified interpreter: "
            "use a qualified ISL interpreter for consent, diagnosis or legal matters.")
EMPTY = "Nothing to sign — the text is empty"
NOTHING_SIGNABLE = "Nothing I can sign in this text"
FAILED = "I couldn't turn this into signs — showing the caption only"
ASL_MISSING = "ASL signing isn't available yet — showing the caption only"
BADGE = {"emit": "high", "repair": "medium", "hold": "low"}
SUPPORTED_SIGN_LANGS = {"isl"}


@dataclass
class SignResult:
    frame: SemanticFrame
    plan: RenderPlan
    readback: list[LatticeSlot] = field(default_factory=list)
    frames: Optional[dict] = None

    @property
    def sign(self) -> Optional[SignTarget]:
        return next((t for t in self.plan.targets if isinstance(t, SignTarget)), None)

    def to_json(self) -> dict:
        return {
            "frame": self.frame.model_dump(mode="json"),
            "plan": self.plan.model_dump(mode="json"),
            "readback": [s.model_dump(mode="json") for s in self.readback],
            "frames": self.frames,
        }


class _LRU:
    def __init__(self, size: int) -> None:
        self.size = size
        self._d: OrderedDict = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            if key in self._d:
                self._d.move_to_end(key)
                return self._d[key]
        return None

    def put(self, key, value) -> None:
        with self._lock:
            self._d[key] = value
            self._d.move_to_end(key)
            while len(self._d) > self.size:
                self._d.popitem(last=False)


class TextToSign:
    def __init__(self, settings: Settings, llm_call: Callable[[str, str], str] | None = None) -> None:
        self.settings = settings
        self._llm_call = llm_call
        if llm_call is None and settings.sign_resolver == "llm":
            self._llm_call = chat_call(settings.llm_url, settings.sign_llm_timeout_s)
        self._gate_cache = _LRU(config.SIGN_CACHE_SIZE)
        self._frames_cache = _LRU(config.SIGN_CACHE_SIZE)
        self.ready = False

    # ------------------------------------------------------------------ setup
    def warmup(self) -> float:
        """Build the recognizer template banks and run one dummy plan."""
        with Stopwatch() as sw:
            RT.warmup()
            self.run("Hello, thank you.", with_frames=True)
        self.ready = True
        return sw.ms

    # --------------------------------------------------------------- resolve
    def resolve(self, text: str, resolutions: dict[int, str], source: PerceptEvent | None,
                speaker_id: str | None, timings: dict[str, float]) -> SemanticFrame:
        with Stopwatch() as sw:
            frame, _ = text_to_frame(text, resolutions, source=source, speaker_id=speaker_id)
        timings["sign.resolve"] = sw.ms
        if self._llm_call is not None and needs_llm_gloss(frame):
            with Stopwatch() as sw:
                better = reorder(frame, self._llm_call)
            timings["sign.llm"] = sw.ms
            if better is not None:
                frame = better
        if highstakes.detect(text):
            frame.high_stakes = True
        return frame

    def _gate(self, target: SignTarget, threshold: float, seed: int):
        key = (target.model_dump_json(include={"gloss"}), threshold, seed)
        hit = self._gate_cache.get(key)
        if hit is not None:
            gloss, lattices, readback, degraded, score = hit
            target.gloss = [g.model_copy() for g in gloss]
            target.roundtrip_score = score
            return lattices, readback, degraded
        res = RT.roundtrip_gate(target, threshold=threshold, seed=seed)
        self._gate_cache.put(key, ([g.model_copy() for g in target.gloss], res.lattices,
                                   res.readback, res.degraded, res.score))
        return res.lattices, res.readback, res.degraded

    def _frames(self, target: SignTarget) -> dict:
        key = target.model_dump_json(include={"gloss", "nonmanual"})
        hit = self._frames_cache.get(key)
        if hit is None:
            hit = frames_json(target)
            self._frames_cache.put(key, hit)
        return hit

    # ------------------------------------------------------------------- run
    def run(self, text: str, *, resolutions: dict[int, str] | None = None, sign_lang: str = "isl",
            profile: str = "balanced", source: PerceptEvent | None = None, speaker_id: str | None = None,
            speaker_label: str | None = "You", with_frames: bool = True,
            seed: int = config.ROUNDTRIP_SEED) -> SignResult:
        timings: dict[str, float] = {}
        with Stopwatch() as total:
            result = self._run(text or "", resolutions or {}, sign_lang, profile, source, speaker_id,
                               speaker_label, with_frames, seed, timings)
        timings["sign.total"] = total.ms
        result.plan.timings_ms = {k: round(v, 2) for k, v in timings.items()}
        return result

    def _run(self, text, resolutions, sign_lang, profile, source, speaker_id, speaker_label,
             with_frames, seed, timings) -> SignResult:
        text = text.strip()
        if not text:
            return hold_result(text, EMPTY, source, speaker_id)
        if sign_lang not in SUPPORTED_SIGN_LANGS:
            return hold_result(text, ASL_MISSING, source, speaker_id)

        frame = self.resolve(text, resolutions, source, speaker_id, timings)

        with Stopwatch() as sw:
            target = plan_sign(frame, sign_lang)
            rt_threshold = RT.THRESHOLD_HIGH_STAKES if frame.high_stakes else RT.THRESHOLD
            lattices, readback, degraded = self._gate(target, rt_threshold, seed) if target.gloss else ([], [], [])
            fix_fingerspelled_durations(target)
            target.nonmanual = nonmanual_track(frame, target)
            target.total_ms = build_timeline(target)[1]
            target.back_translation = back_translate(target, readback, frame) if target.gloss else None
        timings["sign.plan_roundtrip"] = sw.ms

        # ---- trust + gate (Section 5): resolver confidence x round-trip read-back
        rt_score = target.roundtrip_score if target.gloss else 0.0
        trust = round(frame.trust * (rt_score or 0.0), 3)
        frame.trust = trust
        th = thresholds(self.settings, profile, frame.high_stakes)
        repair = None
        if not target.gloss:
            gate, reason = "hold", NOTHING_SIGNABLE
        elif frame.unresolved:
            gate = "repair"
            u = frame.unresolved[0]
            labels = [V.BACK_GLOSS.get(c, c.lower()) for c in u.cands]
            reason = f"Which did you mean by “{u.source_text}”: {' or '.join(labels)}?"
            repair = Repair(type="disambiguate", reason=reason, slot=u.slot, token_index=u.token_index,
                            options=[RepairOption(gloss_or_word=c, label=lab, score=round(1 / len(u.cands), 3),
                                                  clip=f"/api/sign/{c}")
                                     for c, lab in zip(u.cands, labels)])
        else:
            gate = decide(trust, th)
            if gate == "hold":
                reason = "The avatar can't sign this clearly — showing the caption only"
            elif gate == "repair":
                reason = "The signing may be unclear. Send it anyway?"
                repair = Repair(type="confirm", reason=reason, options=[
                    RepairOption(gloss_or_word="SEND", label="Send as shown", score=trust),
                    RepairOption(gloss_or_word="REPHRASE", label="Let me rephrase", score=round(1 - trust, 3)),
                ])
            else:
                reason = "Clear to sign"
        gate_reason = f"{reason} (trust {trust:.2f}; emit ≥ {th.emit:.2f}, hold < {th.repair:.2f})"
        if degraded:
            names = ", ".join(target.gloss[i].g for i in degraded)
            gate_reason += f" Fingerspelled after failed read-back: {names}."

        caption = CaptionTarget(lang=frame.lang, text=text, trust_badge=BADGE[gate],
                                speaker_label=speaker_label, forced=bool(degraded))
        if gate == "hold":
            targets = [caption]
            repair = Repair(type="hold", reason=reason)
        else:
            targets = [caption, target]
        plan = RenderPlan(frame_id=frame.id, gate=gate, targets=targets, repair=repair,
                          back_translation=target.back_translation, gate_reason=gate_reason,
                          advisory=ADVISORY if frame.high_stakes else None)
        frames = None
        if with_frames and target.gloss:
            with Stopwatch() as sw:
                frames = self._frames(target)
            timings["sign.frames"] = sw.ms
        return SignResult(frame=frame, plan=plan, readback=lattices, frames=frames)


def hold_result(text: str, reason: str, source: PerceptEvent | None = None,
                speaker_id: str | None = None) -> SignResult:
    """A hold plan that never shows a guess (empty input, unsupported language, failure)."""
    frame, _ = text_to_frame("", source=source, speaker_id=speaker_id)
    frame.utterance = text
    frame.grounding = [Grounding(span=(0, len(text)), percept_ids=frame.grounding[0].percept_ids,
                                 t=frame.grounding[0].t)]
    frame.trust = 0.0
    plan = RenderPlan(frame_id=frame.id, gate="hold", targets=[], repair=Repair(type="hold", reason=reason),
                      gate_reason=reason)
    return SignResult(frame=frame, plan=plan)


def safe_run(engine: TextToSign, text: str, **kw) -> SignResult:
    """`run` that turns any failure into a hold plan (the caption is still shown by the caller)."""
    try:
        return engine.run(text, **kw)
    except Exception as e:  # never let the sign direction break the session
        log.exception("text->sign failed: %r", e)
        return hold_result(text or "", FAILED, kw.get("source"), kw.get("speaker_id"))
