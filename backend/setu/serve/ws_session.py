"""/ws/session — one conversation session over a localhost WebSocket.

Speech -> text runs in `SpeechPipeline`. Every emitted caption (and every
caption fixed by a repair pick) is queued for the sign stage, which turns the
text into an ISL RenderPlan on the sign thread and sends `render.plan`.
`compose.text` (pipeline D) goes through the same queue.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from functools import partial

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ValidationError

from .. import config
from ..clock import SessionClock
from ..fuse.trust import TrustWeights
from ..generate.text_to_sign import SIGN_POOL, SignResult, safe_run
from ..perceive.audio.base import pcm16_to_float
from ..perceive.audio.pipeline import FinalCaption, SpeechPipeline
from ..perceive.audio.vad import make_vad
from ..resolve.router import join_slots
from ..schemas import Candidate, CaptionTarget, PerceptEvent, RenderPlan, new_id
from ..schemas.session import SessionConfig
from ..schemas.ws import (CaptionFinal, ErrorMsg, LatencyMsg, ModeState, RenderPlanMsg, SessionReady, TrustTick,
                          client_message)
from ..tracing import Tracer
from .modes import ModeManager

log = logging.getLogger("setu.ws")

PENDING_MAX = 32                     # open repairs remembered per session


@dataclass
class SignJob:
    text: str
    origin: str                      # "speech" | "compose" | "repair"
    sign_lang: str = "isl"
    resolutions: dict[int, str] = field(default_factory=dict)
    source: PerceptEvent | None = None
    segment_id: str | None = None
    source_frame_id: str | None = None
    speaker_id: str | None = None
    speaker_label: str | None = "You"
    speech_end_ms: int | None = None


class _Pending(OrderedDict):
    def remember(self, key, value) -> None:
        self[key] = value
        while len(self) > PENDING_MAX:
            self.popitem(last=False)


class Session:
    def __init__(self, ws: WebSocket, modes: ModeManager) -> None:
        self.ws = ws
        self.modes = modes
        self.settings = modes.settings
        self.id = new_id("ss")
        self.clock = SessionClock()
        self.tracer = Tracer(self.id, self.settings.trace_dir, self.settings.store_transcripts)
        self.cfg = SessionConfig()
        self.pipeline: SpeechPipeline | None = None
        self.closed = False
        self._send_lock = asyncio.Lock()
        self._tick: asyncio.Task | None = None
        self.sign = modes.sign
        self._sign_q: asyncio.Queue[SignJob | None] = asyncio.Queue()
        self._sign_task: asyncio.Task | None = None
        self._speech_repairs: _Pending = _Pending()   # caption frame_id -> FinalCaption
        self._sign_repairs: _Pending = _Pending()     # sign frame_id -> (SignJob, SignResult)

    async def emit(self, msg: BaseModel) -> None:
        if self.closed:
            return
        try:
            async with self._send_lock:
                await self.ws.send_text(msg.model_dump_json())
        except Exception:
            self.closed = True

    async def run(self) -> None:
        await self.ws.accept()
        self._sign_task = asyncio.create_task(self._sign_worker())
        try:
            while True:
                raw = await self.ws.receive_text()
                try:
                    msg = client_message.validate_json(raw)
                except ValidationError as e:
                    await self.emit(ErrorMsg(code="bad_message", message=str(e)[:300]))
                    continue
                if msg.type == "session.end":
                    break
                await self.handle(msg)
        except WebSocketDisconnect:
            pass
        finally:
            self.closed = True
            await self.shutdown()

    async def handle(self, msg) -> None:
        t = msg.type
        if t == "session.start":
            await self.start(msg)
        elif t == "audio.chunk":
            if self.pipeline is None:
                await self.emit(ErrorMsg(code="not_started", message="Send session.start first"))
                return
            await self.pipeline.push(pcm16_to_float(base64.b64decode(msg.pcm16_b64)))
        elif t == "mode.set":
            await self.emit(self.modes.state(requested=msg.mode))
        elif t == "verbatim.toggle":
            if self.pipeline:
                self.pipeline.verbatim = msg.on
            self.tracer.event("verbatim", on=msg.on)
        elif t == "repair.pick":
            # Phase 3 also writes picks to jargon memory; for now the choice is traced and applied.
            self.tracer.event(t, frame_id=msg.frame_id, choice=msg.choice)
            await self.repair_pick(msg.frame_id, msg.choice)
        elif t == "repair.neither":
            self.tracer.event(t, frame_id=msg.frame_id)
            self._speech_repairs.pop(msg.frame_id, None)
            self._sign_repairs.pop(msg.frame_id, None)
        elif t == "compose.text":
            await self._sign_q.put(SignJob(text=msg.text, origin="compose", sign_lang=msg.target_sign_lang,
                                           resolutions=dict(msg.resolutions)))
        else:
            await self.emit(ErrorMsg(code="not_implemented", message=f"{t} arrives in a later layer"))

    async def start(self, msg) -> None:
        if self.modes.warming or self.modes.asr is None:
            await self.emit(ModeState(mode="LISTEN", vram_mb=None, cloud=False, warming=True))
            await self.emit(ErrorMsg(code="warming_up", message="Warming up… try again in a moment"))
            return
        if self.pipeline is not None:
            await self.pipeline.close()
        self.cfg = SessionConfig(**msg.model_dump(exclude={"type"}))
        vad = await asyncio.to_thread(make_vad, self.settings.vad)
        self.pipeline = SpeechPipeline(
            asr=self.modes.asr, diarizer=self.modes.new_diarizer(), vad=vad, clock=self.clock,
            tracer=self.tracer, settings=self.settings, emit=self.emit,
            profile=lambda: self.cfg.ask_when_unsure, on_final=self.on_caption,
        )
        self.tracer.event("session.start", mode=self.cfg.mode, asr=self.modes.asr.name,
                          diarizer=self.modes.diarizer_name, vad=self.settings.vad,
                          sign_output=self.signing_on, sign_resolver=self.settings.sign_resolver)
        await self.emit(SessionReady(session_id=self.id, asr=self.modes.asr.name, diarizer=self.modes.diarizer_name,
                                     vad=self.settings.vad, trust_calibrated=TrustWeights().calibrated))
        await self.emit(self.modes.state(requested=self.cfg.mode if self.cfg.mode != "LISTEN" else None))
        if self._tick is None:
            self._tick = asyncio.create_task(self._trust_ticks())

    # ------------------------------------------------------------ sign stage
    @property
    def signing_on(self) -> bool:
        return self.settings.sign_output and self.cfg.sign_output

    async def on_caption(self, fc: FinalCaption) -> None:
        """Speech pipeline hook: sign emitted captions, remember repair-gated ones."""
        if fc.gate == "repair":
            self._speech_repairs.remember(fc.frame.id, fc)
        if fc.gate != "emit" or not self.signing_on:
            return                     # repair/hold frames are never signed or spoken
        await self._sign_q.put(self._speech_job(fc, fc.event, fc.frame.utterance, "speech"))

    def _speech_job(self, fc: FinalCaption, event: PerceptEvent, text: str, origin: str) -> SignJob:
        return SignJob(text=text, origin=origin, sign_lang=self.cfg.sign_lang, source=event,
                       segment_id=fc.segment_id, source_frame_id=fc.frame.id,
                       speaker_id=fc.frame.speaker_id, speaker_label=fc.speaker_label,
                       speech_end_ms=fc.speech_end_ms if origin == "speech" else None)

    async def repair_pick(self, frame_id: str, choice: str) -> None:
        if frame_id in self._sign_repairs:
            job, result = self._sign_repairs.pop(frame_id)
            await self._resolve_sign_repair(job, result, choice)
        elif frame_id in self._speech_repairs:
            await self._resolve_speech_repair(self._speech_repairs.pop(frame_id), choice)

    async def _resolve_sign_repair(self, job: SignJob, result: SignResult, choice: str) -> None:
        rep = result.plan.repair
        if rep is not None and rep.type == "disambiguate" and rep.token_index is not None:
            job.resolutions = {**job.resolutions, rep.token_index: choice}
            job.origin, job.speech_end_ms = "repair", None
            await self._sign_q.put(job)
        elif rep is not None and rep.type == "confirm" and choice == "SEND":
            plan = result.plan.model_copy(update={"gate": "emit", "repair": None,
                                                  "gate_reason": "Confirmed by the author"})
            await self.emit(RenderPlanMsg(plan=plan, origin="repair", segment_id=job.segment_id,
                                          source_frame_id=job.source_frame_id, frame=result.frame,
                                          readback=result.readback, frames=result.frames))
        # "REPHRASE" (or an unknown choice): nothing is signed; the client lets the author edit.

    async def _resolve_speech_repair(self, fc: FinalCaption, choice: str) -> None:
        """The listener picked the word they heard: fix the caption, then sign it."""
        slot_id = fc.frame.unresolved[0].slot if fc.frame.unresolved else None
        event = fc.event.model_copy(deep=True)
        for slot in event.lattice:
            if slot.slot == slot_id:
                rest = [c for c in slot.cands if c.value != choice]
                slot.cands = [Candidate(value=choice, score=1.0)] + rest
        text, _ = join_slots(event)
        caption = CaptionTarget(lang=fc.frame.lang, text=text, trust_badge="high", speaker_label=fc.speaker_label)
        plan = RenderPlan(frame_id=fc.frame.id, gate="emit", targets=[caption],
                          gate_reason="Word chosen by the listener")
        await self.emit(CaptionFinal(segment_id=fc.segment_id, plan=plan, t0=event.t0, t1=event.t1, percept=event))
        if self.signing_on:
            await self._sign_q.put(self._speech_job(fc, event, text, "repair"))

    async def _sign_worker(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            job = await self._sign_q.get()
            if job is None:
                return
            try:
                await self._sign_one(loop, job)
            except Exception as e:
                self.tracer.event("error", stage="sign", message=repr(e))
                await self.emit(ErrorMsg(code="sign_failed", message="Couldn't sign that — the caption is still shown"))

    async def _sign_one(self, loop, job: SignJob) -> None:
        run = partial(safe_run, self.sign, job.text, resolutions=job.resolutions, sign_lang=job.sign_lang,
                      profile=self.cfg.ask_when_unsure, source=job.source, speaker_id=job.speaker_id,
                      speaker_label=job.speaker_label, with_frames=self.cfg.avatar_frames)
        result: SignResult = await loop.run_in_executor(SIGN_POOL, run)
        plan = result.plan
        for stage, ms in plan.timings_ms.items():
            self.tracer.latency(stage, ms)
        await self.emit(LatencyMsg(stage="sign.total", ms=round(plan.timings_ms.get("sign.total", 0.0), 1)))
        if job.speech_end_ms is not None:
            after = self.clock.now_ms() - job.speech_end_ms
            self.tracer.latency("sign.after_speech_end", after)
            await self.emit(LatencyMsg(stage="sign.after_speech_end", ms=float(after)))
        if plan.gate == "repair":
            self._sign_repairs.remember(plan.frame_id, (job, result))
        sign = result.sign
        self.tracer.event("sign", origin=job.origin, gate=plan.gate, trust=result.frame.trust,
                          segment=job.segment_id, source_frame=job.source_frame_id,
                          n_gloss=len(sign.gloss) if sign else 0,
                          n_fingerspelled=sum(g.fingerspelled for g in sign.gloss) if sign else 0,
                          roundtrip=sign.roundtrip_score if sign else None,
                          high_stakes=result.frame.high_stakes, resolver=result.frame.provenance.get("resolver"),
                          text=job.text, gloss=result.frame.gloss)
        await self.emit(RenderPlanMsg(plan=plan, origin=job.origin, segment_id=job.segment_id,
                                      source_frame_id=job.source_frame_id, frame=result.frame,
                                      readback=result.readback, frames=result.frames))

    async def _trust_ticks(self) -> None:
        period = 1.0 / config.TRUST_TICK_HZ
        while not self.closed:
            p = self.pipeline
            if p is not None:
                await self.emit(TrustTick(value=round(p.trust_value, 3), gate=p.trust_gate))
            await asyncio.sleep(period)

    async def shutdown(self) -> None:
        if self._tick:
            self._tick.cancel()
        if self.pipeline is not None:
            try:
                await self.pipeline.close()
            except Exception as e:
                log.warning("pipeline close failed: %r", e)
        if self._sign_task is not None:
            await self._sign_q.put(None)
            try:
                await asyncio.wait_for(self._sign_task, timeout=5)
            except Exception as e:
                log.warning("sign worker close failed: %r", e)
        self.tracer.event("session.end", duration_ms=self.clock.now_ms())
        self.tracer.close()


async def session_endpoint(ws: WebSocket, modes: ModeManager) -> None:
    await Session(ws, modes).run()
