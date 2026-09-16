"""Pipeline C, first half: audio -> VAD -> ASR (partial + final) -> speaker -> L2 -> caption.

Every final caption frame is also handed to `on_final` (the session), which
drives the second half: emitted text -> ISL signing (generate/text_to_sign.py).

All GPU work runs on one worker thread so partials, finals and diarization
never contend for the device. Audio lives only in memory.
"""

from __future__ import annotations

import asyncio
import bisect
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Awaitable, Callable

import numpy as np

from ... import config
from ...clock import SessionClock, Stopwatch
from ...config import Settings
from ...fuse.gate import decide, thresholds
from ...fuse.trust import compute_trust
from ...generate.caption import plan_caption
from ...repair.hold_reasons import NO_WORDS
from ...resolve import highstakes
from ...resolve.router import frame_from_percept
from ...schemas import Gate, PerceptEvent, Quality, SemanticFrame, Speaker
from ...schemas.ws import CaptionFinal, CaptionPartial, HoldMsg, LatencyMsg, RepairRequest, SpeakerUpdate
from ...tracing import Tracer
from .base import ASREngine
from .diarize import NullDiarizer, bind_speaker
from .nbest import hyps_to_lattice
from .vad import SegEvent, VADSegmenter

GPU = ThreadPoolExecutor(max_workers=1, thread_name_prefix="setu-gpu")
_FILLER = re.compile(r"(?i)(h?m+|u+h*m*|a+h+|oh|mm-?hmm)[.,!?]*")

Emit = Callable[[object], Awaitable[None]]


@dataclass
class FinalCaption:
    """A finalized speech frame, as handed to the sign stage."""

    segment_id: str
    event: PerceptEvent
    frame: SemanticFrame
    gate: Gate
    speaker_label: str | None
    speech_end_ms: int              # session clock, for voice -> first sign latency


def _timed(fn, *args):
    with Stopwatch() as sw:
        out = fn(*args)
    return out, sw.ms


class SpeechPipeline:
    def __init__(self, *, asr: ASREngine, diarizer, vad, clock: SessionClock, tracer: Tracer,
                 settings: Settings, emit: Emit, profile: Callable[[], str] = lambda: "balanced",
                 on_final: Callable[[FinalCaption], Awaitable[None]] | None = None) -> None:
        self.asr = asr
        self.diar = diarizer or NullDiarizer()
        self.seg = VADSegmenter(vad)
        self.clock = clock
        self.tracer = tracer
        self.settings = settings
        self.emit = emit
        self.profile = profile
        self.on_final = on_final
        self.verbatim = False

        self._samples_in = 0
        self._arrival_samples: list[int] = []   # cumulative sample count after each chunk
        self._arrival_ms: list[int] = []        # session-clock ms that chunk arrived
        self.trust_value = 0.0
        self.trust_gate = "hold"
        self.active = False                     # speech in progress or being finalized

        self._loop = asyncio.get_running_loop()
        self._finals: asyncio.Queue[SegEvent | None] = asyncio.Queue()
        self._worker = asyncio.create_task(self._final_worker())
        self._partial_busy = False
        self._last_partial_at = 0               # samples of segment audio at last partial
        self._first_partial_sent: set[str] = set()
        self._partial_text: dict[str, str] = {}
        self._onset_sample: dict[str, int] = {}
        self._diar_buf: list[np.ndarray] = []
        self._diar_busy = False
        self._known_speakers: dict[int, float] = {}
        self._vad_ms: list[float] = []

    # ------------------------------------------------------------------ input
    def ms_at(self, sample: int) -> int:
        """Session-clock time at which `sample` reached the server."""
        i = bisect.bisect_left(self._arrival_samples, sample)
        if i < len(self._arrival_samples):
            return self._arrival_ms[i]
        return self._arrival_ms[-1] if self._arrival_ms else 0

    def _note_arrival(self, n: int) -> None:
        self._samples_in += n
        self._arrival_samples.append(self._samples_in)
        self._arrival_ms.append(self.clock.now_ms())
        keep = (config.MAX_SEGMENT_MS * 3) * config.SAMPLE_RATE // 1000
        if len(self._arrival_samples) > 64 and self._arrival_samples[0] < self._samples_in - keep:
            cut = bisect.bisect_left(self._arrival_samples, self._samples_in - keep)
            del self._arrival_samples[:cut], self._arrival_ms[:cut]

    async def push(self, pcm: np.ndarray) -> None:
        self._note_arrival(len(pcm))
        with Stopwatch() as sw:
            events = self.seg.push(pcm)
        self._vad_ms.append(sw.ms)
        self._diar_buf.append(pcm)
        self._kick_diar()
        for ev in events:
            if ev.kind == "start":
                self.active = True
                self._onset_sample[ev.seg_id] = ev.end_sample - config.VAD_FRAME_SAMPLES
                self._last_partial_at = 0
            elif ev.kind == "update":
                self._maybe_partial(ev)
            elif ev.kind == "end":
                self._flush_vad_latency()
                await self._finals.put(ev)

    async def close(self) -> None:
        ev = self.seg.flush()
        if ev:
            await self._finals.put(ev)
        await self._finals.put(None)
        await self._worker

    def _flush_vad_latency(self) -> None:
        if self._vad_ms:
            self.tracer.latency("vad", sum(self._vad_ms) / len(self._vad_ms))
            self._vad_ms.clear()

    # ------------------------------------------------------------- diarizer
    def _kick_diar(self) -> None:
        if isinstance(self.diar, NullDiarizer):
            self._diar_buf.clear()
            return
        if self._diar_busy or not self._diar_buf:
            return
        audio = np.concatenate(self._diar_buf)
        self._diar_buf.clear()
        self._diar_busy = True
        fut = self._loop.run_in_executor(GPU, _timed, self.diar.push, audio)
        fut.add_done_callback(self._diar_done)

    def _diar_done(self, fut) -> None:
        self._diar_busy = False
        try:
            _, ms = fut.result()
            if ms > 1.0:
                self.tracer.latency("diar.step", ms)
        except Exception as e:  # keep captions flowing without speaker labels
            self.tracer.event("error", stage="diar", message=repr(e))
        self._kick_diar()

    async def _wait_diar(self, sample: int, timeout_s: float = 0.8) -> None:
        if isinstance(self.diar, NullDiarizer):
            return
        deadline = self._loop.time() + timeout_s
        while self.diar.processed_until() < sample and self._loop.time() < deadline:
            await asyncio.sleep(0.02)

    def _speaker_for(self, start: int, end: int) -> tuple[int | None, float]:
        probs = self.diar.probs(start, end)
        return bind_speaker(probs)

    async def _announce_speaker(self, idx: int, conf: float) -> None:
        new = idx not in self._known_speakers
        self._known_speakers[idx] = conf
        if new:
            speakers = [{"id": f"spk_{i}", "label": f"Speaker {i + 1}", "conf": round(c, 3), "active": i == idx}
                        for i, c in sorted(self._known_speakers.items())]
            await self.emit(SpeakerUpdate(speakers=speakers))

    # ------------------------------------------------------------- partials
    def _maybe_partial(self, ev: SegEvent) -> None:
        if self._partial_busy or ev.audio is None:
            return
        if self.seg.speech_ms() < config.FIRST_PARTIAL_MIN_MS:
            return
        step = config.PARTIAL_INTERVAL_MS * config.SAMPLE_RATE // 1000
        if len(ev.audio) - self._last_partial_at < step and ev.seg_id in self._first_partial_sent:
            return
        self._partial_busy = True
        self._last_partial_at = len(ev.audio)
        asyncio.create_task(self._run_partial(ev.seg_id, ev.start_sample, ev.audio))

    async def _run_partial(self, seg_id: str, start: int, audio: np.ndarray) -> None:
        try:
            text, ms = await self._loop.run_in_executor(GPU, _timed, self.asr.transcribe_partial, audio)
        except Exception as e:
            self.tracer.event("error", stage="asr.partial", message=repr(e))
            return
        finally:
            self._partial_busy = False
        self.tracer.latency("asr.partial", ms)
        if not text or self.seg.current_id != seg_id:  # segment already finalized: drop stale partial
            return
        if seg_id not in self._first_partial_sent and _FILLER.fullmatch(text.strip()):
            return                                      # "Hmm." on the first 250 ms is usually a guess
        spk, _ = self._speaker_for(start, start + len(audio))
        self._partial_text[seg_id] = text
        await self.emit(CaptionPartial(segment_id=seg_id, text=text, lang=getattr(self.asr, "lang", "en"),
                                       t0=self.ms_at(start), t1=self.ms_at(start + len(audio)),
                                       speaker_label=None if spk is None else f"Speaker {spk + 1}"))
        if seg_id not in self._first_partial_sent:
            self._first_partial_sent.add(seg_id)
            onset = self._onset_sample.get(seg_id, start)
            first_ms = self.clock.now_ms() - self.ms_at(onset)
            self.tracer.latency("caption.first_partial", first_ms)
            await self.emit(LatencyMsg(stage="caption.first_partial", ms=round(first_ms, 1)))

    # --------------------------------------------------------------- finals
    async def _final_worker(self) -> None:
        while True:
            ev = await self._finals.get()
            if ev is None:
                return
            try:
                await self._finalize(ev)
            except Exception as e:
                self.tracer.event("error", stage="final", message=repr(e))
                await self.emit(HoldMsg(reason="Something went wrong on my side — please say that again",
                                        segment_id=ev.seg_id))
            finally:
                self._onset_sample.pop(ev.seg_id, None)
                self._first_partial_sent.discard(ev.seg_id)
                self.active = self.seg.in_speech or not self._finals.empty()

    async def _finalize(self, ev: SegEvent) -> None:
        detected_at = self.clock.now_ms()
        had_partial = ev.seg_id in self._partial_text
        self._partial_text.pop(ev.seg_id, None)
        if ev.audio is None or len(ev.audio) == 0:      # blip shorter than MIN_SPEECH_MS
            if had_partial:
                await self.emit(HoldMsg(reason=NO_WORDS, segment_id=ev.seg_id))
            return

        result, asr_ms = await self._loop.run_in_executor(GPU, _timed, self.asr.transcribe_final, ev.audio)
        self.tracer.latency("asr.final", asr_ms)
        await self.emit(LatencyMsg(stage="asr.final", ms=round(asr_ms, 1)))

        t0, t1 = self.ms_at(ev.start_sample), self.ms_at(ev.end_sample)
        lattice = hyps_to_lattice(result.hyps, offset_ms=t0)
        if not lattice and not had_partial and len(ev.audio) < config.SAMPLE_RATE:
            return                                        # a cough, not speech

        await self._wait_diar(ev.end_sample)
        spk_idx, spk_conf = self._speaker_for(ev.start_sample, ev.end_sample)
        speaker = None
        if spk_idx is not None:
            speaker = Speaker(id=f"spk_{spk_idx}", conf=round(spk_conf, 3), modality="audio")
            await self._announce_speaker(spk_idx, spk_conf)

        with Stopwatch() as sw:
            snr = result.extra.get("snr_db", ev.snr_db)
            event = PerceptEvent(t0=t0, t1=t1, channel="speech", source=result.source, lang_hint=result.lang,
                                 lattice=lattice, speaker=speaker, quality=Quality(snr_db=snr))
            trust = compute_trust(event)
            text = " ".join(event.top1())
            hs = highstakes.detect(text) is not None
            gate = decide(trust.value, thresholds(self.settings, self.profile(), hs)) if lattice else "hold"
            event.trust = round(trust.value, 4)
            frame = frame_from_percept(event, trust, speaker.id if speaker else None) if lattice else None
        self.tracer.latency("trust_gate", sw.ms)
        await self.emit(LatencyMsg(stage="trust_gate", ms=round(sw.ms, 2)))

        label = f"Speaker {spk_idx + 1}" if spk_idx is not None else None
        if frame is None:
            await self.emit(HoldMsg(reason=NO_WORDS, segment_id=ev.seg_id))
        else:
            plan = plan_caption(frame, event, gate, label)
            if gate == "emit":
                await self.emit(CaptionFinal(segment_id=ev.seg_id, plan=plan, t0=t0, t1=t1, percept=event))
            elif gate == "repair":
                await self.emit(RepairRequest(segment_id=ev.seg_id, plan=plan, percept=event))
            else:
                await self.emit(HoldMsg(reason=plan.repair.reason, segment_id=ev.seg_id, frame_id=frame.id))
            if self.on_final is not None:
                try:
                    await self.on_final(FinalCaption(ev.seg_id, event, frame, gate, label, t1))
                except Exception as e:  # the caption is already out; never fail it for the sign stage
                    self.tracer.event("error", stage="on_final", message=repr(e))

        self.trust_value, self.trust_gate = trust.value, gate
        done = self.clock.now_ms()
        self.tracer.latency("final.after_endpoint", done - detected_at)
        self.tracer.latency("final.after_speech_end", done - t1)
        await self.emit(LatencyMsg(stage="final.after_speech_end", ms=float(done - t1)))
        self.tracer.event("final", segment=ev.seg_id, gate=gate, trust=round(trust.value, 4),
                          margin=round(trust.margin, 4), quality=round(trust.quality, 4), snr_db=snr,
                          speaker=speaker.id if speaker else None, high_stakes=hs, forced=ev.forced,
                          dur_ms=t1 - t0, n_slots=len(lattice), text=text)
