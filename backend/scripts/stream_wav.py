"""Stream a WAV file to /ws/session at real-time speed and print what comes back.

    python backend/scripts/stream_wav.py data/clips/two_speakers.wav [--speed 1.0] [--url ws://127.0.0.1:8000/ws/session]

The file is read into memory only; nothing is written.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import sys
import time
import wave

import numpy as np
import websockets

SR = 16000
CHUNK = 1600  # 100 ms


def load_wav(path: str) -> np.ndarray:
    with wave.open(path, "rb") as w:
        if w.getsampwidth() != 2:
            sys.exit("need 16-bit PCM WAV")
        data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768
        if w.getnchannels() > 1:
            data = data.reshape(-1, w.getnchannels()).mean(axis=1)
        sr = w.getframerate()
    if sr != SR:  # linear resample; fine for a test tool
        n = int(len(data) * SR / sr)
        data = np.interp(np.linspace(0, len(data) - 1, n), np.arange(len(data)), data).astype(np.float32)
    return data


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("wav")
    ap.add_argument("--url", default="ws://127.0.0.1:8000/ws/session")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--tail", type=float, default=3.0, help="seconds of silence appended")
    args = ap.parse_args()

    audio = np.concatenate([load_wav(args.wav), np.zeros(int(args.tail * SR), np.float32)])
    async with websockets.connect(args.url, max_size=2**24) as ws:
        await ws.send(json.dumps({"type": "session.start", "mode": "LISTEN", "spoken_langs": ["en"]}))
        start = time.perf_counter()
        done = asyncio.Event()
        partial_lines = {}

        async def reader() -> None:
            async for raw in ws:
                m = json.loads(raw)
                t = f"{time.perf_counter() - start:6.2f}s"
                ty = m["type"]
                if ty == "caption.partial":
                    if partial_lines.get(m["segment_id"]) != m["text"]:
                        partial_lines[m["segment_id"]] = m["text"]
                        print(f"{t}  ..  {m['speaker_label'] or '':<10} {m['text']}")
                elif ty in ("caption.final", "repair.request"):
                    cap = m["plan"]["targets"][0]
                    spans = ", ".join(cap["text"][a:b] for a, b in cap["uncertain_spans"])
                    tag = {"emit": "EMIT  ", "repair": "REPAIR"}[m["plan"]["gate"]]
                    print(f"{t}  {tag} {cap['speaker_label'] or '-':<10} {cap['text']}"
                          f"   [trust {m['percept']['trust']}{'; unsure: ' + spans if spans else ''}]")
                elif ty == "hold":
                    print(f"{t}  HOLD   {m['reason']}")
                elif ty == "render.plan":
                    plan = m["plan"]
                    sign = next((x for x in plan["targets"] if x["kind"] == "sign"), None)
                    gloss = " ".join(g["fs_fallback"] if g["fingerspelled"] else g["g"]
                                     for g in (sign["gloss"] if sign else []))
                    print(f"{t}  SIGN   {plan['gate']:<6} {m['origin']:<7} {gloss or '-'}"
                          f"   [trust {m['frame']['trust'] if m['frame'] else '-'}"
                          f"; round-trip {sign['roundtrip_score'] if sign else '-'}]")
                    if plan["gate"] != "emit" and plan.get("repair"):
                        print(f"{t}         {plan['repair']['reason']}")
                elif ty == "latency":
                    print(f"{t}         latency {m['stage']} = {m['ms']} ms")
                elif ty == "session.ready":
                    print(f"{t}  ready: asr={m['asr']} diarizer={m['diarizer']} vad={m['vad']}")
                elif ty == "speaker.update":
                    print(f"{t}  speakers: {[s['label'] for s in m['speakers']]}")
                elif ty == "error":
                    print(f"{t}  ERROR {m['code']}: {m['message']}")
                    if m["code"] == "warming_up":
                        done.set()
                if done.is_set():
                    return

        task = asyncio.create_task(reader())
        await asyncio.sleep(0.3)
        t0 = time.perf_counter()
        for i in range(0, len(audio), CHUNK):
            pcm = (np.clip(audio[i:i + CHUNK], -1, 1) * 32767).astype("<i2").tobytes()
            await ws.send(json.dumps({"type": "audio.chunk", "seq": i // CHUNK,
                                      "pcm16_b64": base64.b64encode(pcm).decode(), "t": int((i / SR) * 1000)}))
            due = t0 + (i + CHUNK) / SR / args.speed
            await asyncio.sleep(max(0.0, due - time.perf_counter()))
        await asyncio.sleep(2.0)
        await ws.send(json.dumps({"type": "session.end"}))
        done.set()
        await asyncio.sleep(0.2)
        task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
