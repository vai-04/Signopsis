"""English ASR: NVIDIA Parakeet TDT 0.6B v2 (NeMo, FP16 autocast, GPU).

Partials: greedy decode of the whole live segment (segments are capped at
20 s, so re-decoding stays in the tens of ms on the GPU).
Finals: one encoder pass, then
  - greedy decode with word timestamps + word confidence (best path), and
  - beam decode (N-best) for alternatives,
merged into a word lattice by nbest.hyps_to_lattice().
"""

from __future__ import annotations

import copy
import logging

import numpy as np

from ... import config
from .base import ASRResult, Hypothesis, Word
from .nemo_util import restore

log = logging.getLogger("setu.parakeet")

FRAME_S = 0.08  # FastConformer: 10 ms hop x 8 subsampling
PUNCT = set(".,?!;:'\"-…")


def bucket_len(n: int) -> int:
    """Padding buckets: 1 s steps up to 8 s, then 2 s steps (few distinct shapes)."""
    sr = config.SAMPLE_RATE
    if n <= 8 * sr:
        return max(1, -(-n // sr)) * sr
    return -(-n // (2 * sr)) * 2 * sr


def _warmup_speech() -> np.ndarray | None:
    """Any 16 kHz mono clip under data/clips (read only; nothing is written)."""
    import wave

    for path in sorted((config.ROOT / "data" / "clips").glob("*.wav")):
        try:
            with wave.open(str(path), "rb") as w:
                if w.getframerate() == config.SAMPLE_RATE and w.getnchannels() == 1 and w.getsampwidth() == 2:
                    return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768
        except Exception:
            continue
    return None


def all_buckets() -> list[int]:
    out, n = [], 1
    while True:
        b = bucket_len(n)
        out.append(b)
        if b >= config.MAX_SEGMENT_MS * config.SAMPLE_RATE // 1000:
            return out
        n = b + 1


class ParakeetASR:
    name = "parakeet-tdt"
    lang = "en"

    def __init__(self, device: str = "cuda", dtype: str = "float16") -> None:
        self.device = device
        self.dtype_name = dtype
        self.model = None
        self.beam = None

    # ------------------------------------------------------------------ setup
    def load(self) -> None:
        import torch
        from nemo.collections.asr.models import ASRModel
        from nemo.collections.asr.parts.submodules.rnnt_decoding import RNNTBPEDecoding
        from omegaconf import open_dict

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA not available — Parakeet needs the GPU (use SETU_FALLBACK=cpu for CPU)")
        self.torch = torch
        self.dtype = getattr(torch, self.dtype_name)
        model = restore(ASRModel, config.PARAKEET_MODEL, self.device)
        model.eval()
        model.preprocessor.featurizer.dither = 0.0
        model.preprocessor.featurizer.pad_to = 0

        greedy = copy.deepcopy(model.cfg.decoding)
        with open_dict(greedy):
            greedy.strategy = "greedy_batch"
            greedy.compute_timestamps = True
            greedy.preserve_alignments = False
            greedy.confidence_cfg = {
                "preserve_frame_confidence": True,
                "preserve_token_confidence": True,
                "preserve_word_confidence": True,
                "exclude_blank": True,
                "aggregation": "min",
                "method_cfg": {"name": "entropy", "entropy_type": "tsallis", "alpha": 0.5, "entropy_norm": "exp"},
            }
            # Word confidence needs the per-frame path; CUDA graphs decoding does not keep it.
            if "greedy" in greedy:
                greedy.greedy.use_cuda_graph_decoder = False
        model.change_decoding_strategy(greedy, verbose=False)

        # Partials: plain greedy with CUDA graphs — no confidence, no timestamps.
        fast = copy.deepcopy(model.cfg.decoding)
        with open_dict(fast):
            fast.strategy = "greedy_batch"
            fast.compute_timestamps = False
            fast.confidence_cfg = {"preserve_frame_confidence": False}
            # CUDA graphs re-capture whenever the (growing) segment gets longer.
            fast.greedy.use_cuda_graph_decoder = False
        self.fast = RNNTBPEDecoding(decoding_cfg=fast, decoder=model.decoder, joint=model.joint,
                                    tokenizer=model.tokenizer)

        if self.dtype_name == "float16":
            # Encoder (almost all parameters) in FP16; preprocessor, decoder and
            # joint stay FP32 so every decoding strategy works.
            model.encoder.half()

        beam = copy.deepcopy(model.cfg.decoding)
        with open_dict(beam):
            beam.strategy = "malsd_batch"   # batched GPU beam search (TDT)
            beam.compute_timestamps = False
            beam.beam.beam_size = config.NBEST
            beam.beam.return_best_hypothesis = False
            beam.confidence_cfg = {"preserve_frame_confidence": False}
        self.beam = RNNTBPEDecoding(decoding_cfg=beam, decoder=model.decoder, joint=model.joint,
                                    tokenizer=model.tokenizer)
        self.model = model

    def warmup(self) -> None:
        rng = np.random.default_rng(0)
        audio = (0.01 * rng.standard_normal(config.SAMPLE_RATE * 2)).astype(np.float32)
        for _ in range(2):
            self.transcribe_partial(audio)
            self.transcribe_final(audio)
        noise = (0.01 * rng.standard_normal(all_buckets()[-1])).astype(np.float32)
        for b in all_buckets():  # first use of each shape is slow; pay it at startup
            self.transcribe_partial(noise[:b])
            self.transcribe_final(noise[:b])
        speech = _warmup_speech()
        if speech is not None:   # noise yields no tokens; exercise the token path too
            for sec in (0.3, 0.6, 1, 2, 3, 5):
                self.transcribe_partial(speech[: int(sec * config.SAMPLE_RATE)])
            self.transcribe_final(speech[: 5 * config.SAMPLE_RATE])

    # -------------------------------------------------------------- inference
    def _encode(self, audio: np.ndarray):
        torch = self.torch
        # Pad to a length bucket so kernels see few distinct shapes; the true
        # length is passed, so masking keeps results unchanged.
        n = len(audio)
        padded = bucket_len(n)
        buf = np.zeros(padded, dtype=np.float32)
        buf[:n] = audio
        sig = torch.from_numpy(buf).to(self.device).unsqueeze(0)
        length = torch.tensor([n], device=self.device)
        with torch.autocast("cuda", dtype=self.dtype):
            enc, enc_len = self.model(input_signal=sig, input_signal_length=length)
        return enc.float(), enc_len

    @staticmethod
    def _first(out):
        # NeMo returns list[Hypothesis] (2.x) or (best, all) tuples (older).
        if isinstance(out, tuple):
            out = out[0]
        return out

    def transcribe_partial(self, audio: np.ndarray) -> str:
        with self.torch.inference_mode():
            enc, enc_len = self._encode(audio)
            hyps = self._first(self.fast.rnnt_decoder_predictions_tensor(
                encoder_output=enc, encoded_lengths=enc_len, return_hypotheses=True))
        h = hyps[0]
        return (h.text if hasattr(h, "text") else str(h)).strip()

    def transcribe_final(self, audio: np.ndarray) -> ASRResult:
        with self.torch.inference_mode():
            enc, enc_len = self._encode(audio)
            best = self._first(self.model.decoding.rnnt_decoder_predictions_tensor(
                encoder_output=enc, encoded_lengths=enc_len, return_hypotheses=True))[0]
            nbest = self._nbest(enc, enc_len)

        words = self._words(best)
        if not words:
            return ASRResult(hyps=[], lang=self.lang, source=self.name)
        best_text = " ".join(w.text for w in words)
        by_text = {t: s for t, s in nbest}
        best_score = by_text.get(best_text, nbest[0][1] if nbest else 0.0)
        hyps = [Hypothesis(words, score=best_score)]
        for text, score in nbest:
            if text != best_text and text:
                hyps.append(Hypothesis([Word(t, 0, 0) for t in text.split()], score=score))
        return ASRResult(hyps=hyps, lang=self.lang, source=self.name,
                         extra={"n_beam": len(nbest)})

    def _nbest(self, enc, enc_len) -> list[tuple[str, float]]:
        try:
            out = self.beam.rnnt_decoder_predictions_tensor(
                encoder_output=enc, encoded_lengths=enc_len, return_hypotheses=True)
        except Exception as e:  # beam is an enhancement; greedy + confidence still works
            log.warning("beam decode failed: %r", e)
            return []
        if isinstance(out, tuple):
            out = out[1] if len(out) > 1 and out[1] is not None else out[0]
        item = out[0]
        if isinstance(item, (list, tuple)):
            cands = list(item)
        else:
            cands = getattr(item, "n_best_hypotheses", None) or [item]
        res: list[tuple[str, float]] = []
        seen: set[str] = set()
        for h in cands:
            if isinstance(h.text, str):
                text = h.text.strip()
            else:
                ids = h.y_sequence.tolist() if hasattr(h.y_sequence, "tolist") else list(h.y_sequence)
                text = self.model.tokenizer.ids_to_text(ids).strip()
            if text in seen:
                continue
            seen.add(text)
            res.append((text, float(h.score)))
        res.sort(key=lambda x: x[1], reverse=True)
        return res

    def _word_confs(self, hyp, n_words: int) -> list[float]:
        """Min token confidence per word, ignoring pure punctuation tokens.

        NeMo's word confidence includes the trailing "." / "?" token, whose
        uncertainty is about punctuation, not about the word that was said.
        """
        fallback = [float(c) for c in (getattr(hyp, "word_confidence", None) or [])]
        tok_conf = getattr(hyp, "token_confidence", None)
        ids = hyp.y_sequence.tolist() if hasattr(hyp.y_sequence, "tolist") else list(hyp.y_sequence or [])
        if not tok_conf or len(tok_conf) != len(ids):
            return fallback
        pieces = self.model.tokenizer.ids_to_tokens(ids)
        words: list[list[float]] = []
        for piece, c in zip(pieces, tok_conf):
            starts = piece.startswith("▁") or not words
            core = piece.lstrip("▁")
            if starts:
                words.append([])
            if core and all(ch in PUNCT for ch in core):
                continue
            words[-1].append(float(c))
        if len(words) != n_words:
            return fallback
        return [min(w) if w else 1.0 for w in words]

    def _words(self, hyp) -> list[Word]:
        text = (hyp.text or "").strip()
        if not text:
            return []
        tokens = text.split()
        confs = self._word_confs(hyp, len(tokens))
        stamps = []
        ts = getattr(hyp, "timestamp", None) or getattr(hyp, "timestep", None)
        if isinstance(ts, dict):
            stamps = ts.get("word", []) or []
        words: list[Word] = []
        for i, tok in enumerate(tokens):
            start = end = 0
            if i < len(stamps):
                st = stamps[i]
                if "start" in st and st["start"] is not None:
                    start, end = int(float(st["start"]) * 1000), int(float(st["end"]) * 1000)
                else:
                    start = int(st.get("start_offset", 0) * FRAME_S * 1000)
                    end = int(st.get("end_offset", 0) * FRAME_S * 1000)
            conf = float(confs[i]) if i < len(confs) else None
            words.append(Word(tok, start, end, conf))
        return words
