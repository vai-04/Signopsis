# SIGNOPSIS: two-way ISL interpreter that knows when it doesn't know

- **Sign → text and voice**, live from your webcam. MediaPipe runs in the browser. The server reads the signing, scores how much to trust it, and then **shows** the caption, **asks** you a question, or **holds** it.
- **Text → sign**: English, Hindi or Hinglish becomes ISL gloss and a pixel avatar. A round-trip check reads the avatar's signing back before it plays.
- **Teach it your own signs** (name signs, local variants) with 4 samples. No retraining.
- **3D cartoon signer** (three.js): curly hair, big smile, black hoodie. It signs whatever you type in real time, can copy your hands from the webcam, and has a pose lab where you can shape every finger.

- **Web app** (separate repo `signopsis-web`, React + three.js): Converse, Live stage (auto language detection → ISL/ASL/BSL…), Compose, Teach a sign, Screen Glance, Diagnostics. Build it into `signopsis/serve/web` and open `/app/`.

```bash
pip install -r requirements.txt
python scripts/fetch_models.py        # optional: offline MediaPipe models + wasm
uvicorn signopsis.serve.main:app           # open http://localhost:8000
pytest -q                             # 160 tests
```

## Try it

| Where | What to do |
|---|---|
| `/avatar` | **3D signer.** Type and it signs. Orbit, zoom and switch views (front, ¾, hands, side, full body), restyle skin, hair, clothes and background, and click the avatar to make it wave. **Mirror me** copies your hands and face from the webcam. **Pose lab** has sliders for every finger. |
| `/sign-to-text` → **Camera** | Start the camera and sign. The HUD shows hands, body, light and brows. Captions appear with trust bars. |
| `/sign-to-text` → **Simulated** | No webcam needed. Type a sentence or click a chip; drag *conditions* toward "awful" to watch it start asking or holding instead of guessing. |
| chip **ambiguous: ME RIVER GO** | A "Which sign?" card with two avatar previews. Answer it once and it's remembered for that context. |
| chips **unlisted …** | A sign it doesn't know → hold → *Teach me* → it recognizes your sign from then on. |
| `/text-to-sign` | Pixel avatar, ISL gloss, read-back check. |
| `/` | Mode manager and VRAM plan. |
| `/app/` | The SIGNOPSIS web app (after `npm run build` in signopsis-web → copy `dist/` to `signopsis/serve/web/`). |

Terminal only:

```bash
python -m signopsis.perceive.simulate "I went to the bank yesterday." --severity 0.6
python -m signopsis.perceive.simulate --gloss ME,RIVER,GO --answer RIVER
python -m signopsis.perceive.simulate --teach Kushagra --gloss MY,NAME,DEMO-NAMESIGN
python -m signopsis.cli "What is your name?" --gif out.gif          # text -> sign
python scripts/build_avatar_demo.py                           # single-file offline 3D signer (needs Node)
python -m signopsis.perceive.camera_cv --user me                    # native webcam client (opencv + mediapipe)
python -m signopsis.fuse.fit --n 400 --plot                         # refit trust weights and write the metrics report
```

## Results on the simulator (this build)

Held-out set: 200 phrases (583 recognized signs) across six severity levels, from studio conditions to awful. Refit
and re-measure with `python -m signopsis.fuse.fit`.

| Metric | Value |
|---|---|
| Top-1 accuracy per sign, all conditions | 89.4% |
| Signs that would be wrong if every top-1 were shown | 10.6% |
| **Wrong signs among those actually shown** | **2.2%** (85% of signs shown) |
| Sentences that would be wrong if every sentence were shown | 28.0% |
| **Wrong sentences among those actually shown** | **1.8%** (57% of sentences shown) |
| Sentences where it asked a question / held | 23% / 20% |
| Calibration error (ECE) of the trust score | 0.030 |
| Studio conditions | 100% shown, 0 wrong |
| Latency, end of phrase → caption (CPU) | about 60–250 ms |

The trade-off is visible in these numbers. Errors that would have been shown are
moved into questions ("which sign?", "did I get all of that?") and holds
("it's too dark"), and the system learns your own signs.

> **Important:** the base sign vocabulary is a set of placeholder motions made for the 2D avatar. Real
> ISL at a real camera will mostly be read as *unknown* until you teach those signs or replace
> the lexicon with recorded ISL prototypes. The trust, repair and teaching machinery is what this
> build demonstrates. See `ARCHITECTURE.md` §7.

## Endpoints added for the web app

| Endpoint / message | Purpose |
|---|---|
| `POST /api/screen/describe` | Screen Glance: `{question, intent, snapshot}` → short, ordered answer + targets (`signopsis/screen`) |
| `GET /api/eval/report` | Trust-model evaluation for the Diagnostics screen |
| `GET /api/lexicon` → `sign_langs` | Installed sign-language packs (ISL today) |
| `POST /api/text-to-sign` accepts `src_lang`, `sign_lang` | Unsupported `sign_lang` → ISL with `sign_lang_fallback` in the response |
| WS `enroll_undo`, `enroll_start{kind, scope}` | "Redo last" and sign metadata (name sign / variant / work word; only me / team) |
| CORS (`SIGNOPSIS_CORS_ORIGINS`) | Vite dev server on :5173 allowed by default |
| `/app/` static mount (`SIGNOPSIS_WEB_DIST`) | Serve the built web app from the same origin |

Design, contracts and the plan for swapping in the heavy models are in [`ARCHITECTURE.md`](ARCHITECTURE.md).
The grammar rules, written for review by a Deaf consultant, are in [`signopsis/resolve/grammar/isl.md`](signopsis/resolve/grammar/isl.md).
