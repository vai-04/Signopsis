"""Terminal test harness for pipeline D (no browser needed).

    python -m setu.cli "I went to the bank yesterday."
    python -m setu.cli "mujhe kal bank jaana hai" --resolve 1=TOMORROW
    python -m setu.cli "What is your name?" --gif out.gif      # pixel GIF (needs Pillow)
    python -m setu.cli --json "Do you want water?"             # full contracts
"""
from __future__ import annotations

import argparse
import json

from setu.pipeline import text_to_sign

# pixel colours for the GIF, same palette as the viewer
BG, STRIPE, BODY = (29, 43, 58), (34, 52, 71), (61, 90, 128)
SKIN_R, SKIN_L, BACK, TIP = (242, 194, 155), (217, 164, 124), (185, 132, 96), (255, 241, 224)
FINGERS = [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12], [13, 14, 15, 16], [17, 18, 19, 20]]


def render_gif(frames: dict, path: str, scale: int = 4):
    from PIL import Image, ImageDraw
    imgs = []
    for f in frames["frames"]:
        im = Image.new("RGB", (100, 100), BG)
        d = ImageDraw.Draw(im)
        for y in range(0, 100, 4):
            d.line([(0, y), (99, y)], fill=STRIPE)
        d.polygon([(30, 44), (70, 44), (76, 100), (24, 100)], fill=BODY)
        d.rectangle([46, 32, 53, 44], fill=BODY)
        face = f["face"]
        cx, cy = 50 + face["hx"], 22 + face["hy"]
        d.ellipse([cx - 8, cy - 10, cx + 8, cy + 10], fill=SKIN_R)
        d.chord([cx - 8, cy - 10, cx + 8, cy + 10], 180, 360, fill=(43, 43, 43))
        d.ellipse([cx - 8, cy - 6, cx + 8, cy + 10], fill=SKIN_R)
        d.rectangle([cx - 4, cy - 1, cx - 3, cy], fill=(26, 26, 26))
        d.rectangle([cx + 3, cy - 1, cx + 4, cy], fill=(26, 26, 26))
        brow = face["brow"]
        by = {"raised": -5, "neutral": -3}.get(brow)
        if by is not None:
            d.line([(cx - 5, cy + by), (cx - 2, cy + by)], fill=(58, 42, 32))
            d.line([(cx + 2, cy + by), (cx + 5, cy + by)], fill=(58, 42, 32))
        else:
            d.line([(cx - 5, cy - 4), (cx - 2, cy - 2)], fill=(58, 42, 32))
            d.line([(cx + 2, cy - 2), (cx + 5, cy - 4)], fill=(58, 42, 32))
        d.line([(cx - 2, cy + 5), (cx + 2, cy + 5)], fill=(138, 59, 59))
        for key, pk, skin in (("L", "Lp", SKIN_L), ("R", "Rp", SKIN_R)):
            H = [tuple(p) for p in f[key]]
            col = BACK if f[pk] < 0 else skin
            d.polygon([H[0], H[1], H[5], H[9], H[13], H[17]], fill=col)
            for fg in FINGERS:
                d.line([H[0] if fg[0] == 1 else H[fg[0]], H[fg[0]]], fill=col, width=2)
                d.line([H[i] for i in fg], fill=col, width=2)
                d.point(H[fg[3]], fill=TIP)
        if f.get("ch"):
            d.text((86, 3), f["ch"], fill=(255, 212, 138))
        imgs.append(im.resize((100 * scale, 100 * scale), Image.NEAREST))
    imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=int(1000 / frames["fps"]), loop=0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text")
    ap.add_argument("--resolve", action="append", default=[], help="token_index=GLOSS (repair answer)")
    ap.add_argument("--gif")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    res = {int(k): v for k, v in (r.split("=", 1) for r in a.resolve)}
    out = text_to_sign(a.text, res, with_frames=bool(a.gif))
    if a.json:
        print(json.dumps({k: v for k, v in out.items() if k != "frames"}, indent=2, ensure_ascii=False))
    else:
        p, fr = out["plan"], out["frame"]
        sign = next(t for t in p["targets"] if t["kind"] == "sign")
        print(f"text      : {a.text}   [{fr['lang']}, {fr['speech_act']}{', ' + fr['question_type'] if fr['question_type'] else ''}]")
        print(f"gloss     : {' '.join(fr['gloss'])}")
        for g in sign["gloss"]:
            tag = f"fingerspell {g['fs_fallback']}" if g["fingerspelled"] else "sign"
            print(f"   {g['g']:<12} {tag:<26} read-back {g['roundtrip']:.2f}")
        print(f"reads as  : {sign['back_translation']}")
        nm = ", ".join(str(k["t"]) + "ms " + "/".join(str(v) for kk, v in k.items() if kk != "t" and v)
                       for k in sign["nonmanual"])
        print(f"non-manual: {nm}")
        print(f"GATE      : {p['gate'].upper()}  trust={fr['trust']:.2f}  {p['gate_reason']}")
        if p["repair"]:
            r = p["repair"]
            opts = "  ".join(f"--resolve {r['token_index']}={o['gloss']}" for o in r["options"]) if r["type"] == "disambiguate" else ""
            print(f"REPAIR    : {r['prompt']}  {opts}")
        if p["advisory"]:
            print(f"ADVISORY  : {p['advisory']}")
        print(f"timings   : {p['timings_ms']}")
    if a.gif:
        render_gif(out["frames"], a.gif)
        print(f"wrote {a.gif}")


if __name__ == "__main__":
    main()
