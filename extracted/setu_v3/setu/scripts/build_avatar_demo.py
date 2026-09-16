"""Build a single-file, offline copy of the 3D signer (no server needed).

    python scripts/build_avatar_demo.py          # -> dist/setu_avatar3d_demo.html

Needs Node (npx esbuild) to bundle the modules into one script. The demo
embeds precomputed plans for the example sentences; free text needs the server.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from setu.pipeline import text_to_sign  # noqa: E402

STATIC = ROOT / "setu" / "serve" / "static"
EXAMPLES = ["Hello, my name is Priya. What is your name?", "I went to the bank yesterday.", "Do you want water?",
            "I don't understand.", "Thank you! See you tomorrow.", "Where is the hospital?",
            "mujhe kal bank jaana hai", "main kal ghar gaya tha", "Hello"]


def slim(res: dict) -> dict:
    for f in res["frames"]["frames"]:
        for k in ("R", "L", "Rp", "Lp"):
            f.pop(k, None)
    return res


def main(out: Path = ROOT / "dist" / "setu_avatar3d_demo.html") -> Path:
    results = {}
    for text in EXAMPLES:
        r = text_to_sign(text, with_frames=True)
        results[text] = slim(r)
        rep = r["plan"]["repair"]
        if rep and rep["type"] == "disambiguate":
            for o in rep["options"]:
                key = text + "|" + json.dumps({str(rep["token_index"]): o["gloss"]}, separators=(",", ":"))
                results[key] = slim(text_to_sign(text, {rep["token_index"]: o["gloss"]}, with_frames=True))
    npx = shutil.which("npx")
    if not npx:
        sys.exit("npx (Node.js) is required to bundle the page")
    bundle = subprocess.run([npx, "--yes", "esbuild", str(STATIC / "avatar3d" / "app.js"), "--bundle",
                             "--format=esm", "--minify"], capture_output=True, text=True, check=True).stdout
    html = (STATIC / "avatar3d.html").read_text(encoding="utf-8")
    data = json.dumps({"results": results}, separators=(",", ":"))
    html = html.replace('<script type="module" src="/static/avatar3d/app.js"></script>',
                        f"<script>window.SETU_AVATAR_DEMO={data};</script>\n<script type=\"module\">{bundle}</script>")
    html = html.replace('<nav><a href="/">Hub</a><a href="/text-to-sign">Text → sign (2D)</a><a href="/sign-to-text">Sign → text</a></nav>',
                        '<nav><span style="color:var(--muted);font-size:13px">offline demo · run the SETU server for free text and the webcam</span></nav>')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(out, f"{out.stat().st_size / 1e6:.2f} MB")
    return out


if __name__ == "__main__":
    main()
