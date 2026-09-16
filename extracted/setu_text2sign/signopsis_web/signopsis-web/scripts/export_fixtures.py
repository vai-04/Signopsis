"""Export real backend outputs as fixtures for the SIGNOPSIS frontend mock mode.

    cd <backend repo> && python <frontend>/scripts/export_fixtures.py <frontend>/src/mocks

Writes:
  sign_bank.json   per-sign 3D clips (Rq/Lq/face) for every lexicon sign + fingerspelling letters
  t2s.json         full /api/text-to-sign responses for the featured sentences (incl. repair branches)
  s2t.json         recorded /ws/sign event transcripts (clean, ambiguous, dark, unknown sign)
  lexicon.json     /api/lexicon
  simcam_sample.json  one /api/simcam stream (drawn as the simulated signer in mock mode)
  vocab.json       word->gloss tables (used only by the in-browser mock resolver)
Re-run it whenever the backend lexicon or contracts change; mock mode then matches the server again.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")
from signopsis.generate.avatar2d import frames_json          # noqa: E402
from signopsis.generate.signs import LEXICON, ALPHABET, UNLISTED, FS_DUR  # noqa: E402
from signopsis.memory.store import MemoryStore                # noqa: E402
from signopsis.perceive.session import SignSession            # noqa: E402
from signopsis.perceive.simcam import Degrade, plan_for, stream, text_stream  # noqa: E402
from signopsis.pipeline import text_to_sign                   # noqa: E402
from signopsis.resolve.vocab import CATEGORY                  # noqa: E402
from signopsis.schemas import GlossItem, SignTarget           # noqa: E402

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "src/mocks")
OUT.mkdir(parents=True, exist_ok=True)


def r2(o):
    if isinstance(o, float):
        return round(o, 2)
    if isinstance(o, list):
        return [r2(x) for x in o]
    if isinstance(o, dict):
        return {k: r2(v) for k, v in o.items()}
    return o


def slim_frame(f):
    return r2({"Rq": f["Rq"], "Lq": f["Lq"], "face": f["face"]})


def clip(gloss, dur, fs=False):
    item = GlossItem(g=gloss, dur_ms=dur, fingerspelled=fs, fs_fallback=gloss[3:] if fs else None)
    return frames_json(SignTarget(gloss=[item]))


bank = {"fps": 30, "signs": {}, "letters": {}, "rest": None}
for g, spec in list(LEXICON.items()) + [(g, {"dur": 700}) for g in UNLISTED]:
    r = clip(g, spec.get("dur", 700))
    seg = r["segments"][0] if r["segments"] else {"start": 0, "end": r["total_ms"]}
    fr = [slim_frame(f) for f in r["frames"] if seg["start"] <= f["t"] <= seg["end"]]
    bank["signs"][g] = fr
    if bank["rest"] is None:
        bank["rest"] = slim_frame(r["frames"][0])
for ch in ALPHABET:
    r = clip("FS:" + ch, FS_DUR, fs=True)
    mid = r["frames"][len(r["frames"]) // 2]
    bank["letters"][ch] = slim_frame(mid)
bank["fs_ms"] = FS_DUR


def slim_res(res):
    for f in res["frames"]["frames"]:
        for k in ("R", "L", "Rp", "Lp"):
            f.pop(k, None)
    return r2(res)


FEATURED = ["Hello, my name is Priya. What is your name?", "I went to the bank yesterday.",
            "Your appointment is moved to Thursday at 4.", "Do you want water?", "I don't understand.",
            "Thank you! See you tomorrow.", "Where is the hospital?", "I have pain, I need medicine.",
            "mujhe kal bank jaana hai", "main kal ghar gaya tha", "Hello", "Good morning, welcome to school.",
            "Please help me, I need a doctor.", "Namaste, aap kaise ho?", "मुझे पानी चाहिए", "Where is the toilet?", "Are you sick?"]
t2s = {}
for text in FEATURED:
    res = text_to_sign(text, with_frames=True)
    t2s[text] = slim_res(res)
    rep = res["plan"]["repair"]
    if rep and rep["type"] == "disambiguate":
        for o in rep["options"]:
            key = text + "|" + json.dumps({str(rep["token_index"]): o["gloss"]}, separators=(",", ":"))
            t2s[key] = slim_res(text_to_sign(text, {rep["token_index"]: o["gloss"]}, with_frames=True))


def record(sess, frames):
    ev = [sess.hello()]
    for f in frames:
        ev += sess.handle(f)
    ev += sess.handle({"type": "flush"})
    # thin out 'live' spam and drop percept landmark payloads (large)
    out, k = [], 0
    for e in ev:
        if e["type"] == "live":
            k += 1
            if k % 6:
                continue
        out.append(e)
    return r2(out)


tmp = Path(tempfile.mkdtemp())
s2t = {}
scen = {
    "clean": ("text", "I went to the bank yesterday.", Degrade(noise=0.4)),
    "question": ("text", "What is your name?", Degrade(noise=0.4)),
    "ambiguous": ("gloss", ["ME", "RIVER", "GO"], Degrade(noise=0.4)),
    "dark": ("text", "I went to the bank yesterday.", Degrade(noise=3.5, dropout=0.5, lux=12)),
    "unknown": ("gloss", ["MY", "NAME", "DEMO-NAMESIGN"], Degrade(noise=0.4)),
    "medical": ("text", "I have pain, I need medicine.", Degrade(noise=0.4)),
}
for name, (kind, what, deg) in scen.items():
    sess = SignSession("demo", MemoryStore(tmp / name))
    frames = text_stream(what, deg, seed=5 if name == "dark" else 3)[0] if kind == "text" else \
        stream(plan_for(what), deg, seed=0)
    ev = record(sess, frames)
    # repair follow-up for the ambiguous case
    res = [e for e in ev if e["type"] == "result"]
    if name == "ambiguous" and res and res[-1]["plan"].get("repair"):
        rep = res[-1]["plan"]["repair"]
        s2t["ambiguous_after_RIVER"] = r2(sess.handle({"type": "repair_choice", "frame_id": res[-1]["plan"]["frame_id"],
                                                        "slot": rep["slot"], "choice": "RIVER"}))
    s2t[name] = ev

import signopsis.resolve.vocab as V  # noqa: E402
from signopsis.resolve.rules import CONTRACTIONS, YESNO_STARTERS  # noqa: E402
vocab = {k: (sorted(getattr(V, k)) if isinstance(getattr(V, k), set) else getattr(V, k))
         for k in dir(V) if k.isupper()}
vocab["CONTRACTIONS"] = CONTRACTIONS
vocab["YESNO_STARTERS"] = sorted(YESNO_STARTERS)

def r3(o):
    if isinstance(o, float):
        return round(o, 3)
    if isinstance(o, list):
        return [r3(x) for x in o]
    if isinstance(o, dict):
        return {k: r3(v) for k, v in o.items()}
    return o


# one real simulated-camera stream: mock mode replays it to draw the landmark overlay
sim_frames, sim_info = text_stream("I went to the bank yesterday.", Degrade(noise=0.4), seed=3)
for f in sim_frames:
    f.pop("_gi", None)
    if f.get("pose"):
        f["pose"] = f["pose"][:17]
simcam = {"frames": r3(sim_frames), "info": sim_info}

lex = {"signs": sorted(LEXICON), "vocab_without_sign": sorted(set(CATEGORY) - set(LEXICON)),
       "unlisted_demo_signs": sorted(UNLISTED)}

for name, obj in [("sign_bank", bank), ("t2s", t2s), ("s2t", s2t), ("lexicon", lex), ("vocab", vocab), ("simcam_sample", simcam)]:
    p = OUT / f"{name}.json"
    p.write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print(p, f"{p.stat().st_size / 1e3:.0f} kB")
