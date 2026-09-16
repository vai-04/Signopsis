# Signopsis

A local, two-way sign language interpreter: speech becomes ISL sign, and sign becomes
text and speech. Everything — the API, the WebSocket, and the pages you actually open in
a browser — is served by one backend. No separate frontend to build or run.

It's built around one idea: when it isn't sure what it heard, it should say so instead of
guessing. Captions carry a confidence badge, and anything genuinely ambiguous gets asked
about instead of assumed.

Not a certified interpreter — don't rely on it for anything medical, legal, or otherwise
high-stakes.

## Run it (frontend + backend, one server, one link)

```bash
cd /mnt/c/Users/shrey/Downloads/setu       # WSL2 / Ubuntu
cp .env.example .env
make setup                                  # GPU speech stack + deps
make models                                 # downloads Parakeet + Sortformer (asks first, ~2.9 GB)
make backend
```

Then open **http://127.0.0.1:8000/dev/listen** in your browser. That's it — same server,
same port, for the API and the UI.

No GPU / no models yet? `make backend-fake` boots the same server with a scripted fake
speech recognizer, so you can click through the whole flow without downloading anything.

Once it's running:

| Open | What it is |
|---|---|
| [`http://127.0.0.1:8000/dev/listen`](http://127.0.0.1:8000/dev/listen) | speak or stream a WAV → live captions → the avatar signs each one |
| [`http://127.0.0.1:8000/dev/compose`](http://127.0.0.1:8000/dev/compose) | type text → sign preview, confidence, repair prompts |
| [`http://127.0.0.1:8000/app/#/live`](http://127.0.0.1:8000/app/#/live) | full web app, Live stage — build it first: `cd app/web && npm install && npm run build`, then restart the backend |

Or drive it from the terminal without a browser at all:

```bash
make stream WAV=data/clips/two_speakers.wav      # streams a clip, prints captions + signs live
make sign SIGN_TEXT="What is your name?"         # one-shot text -> sign over the REST API
```

## Testing

```bash
make test          # no models needed
make test-gpu       # needs real models + data/clips/*.wav
make latency         # latency report from trace logs
```

## Config

Copy `.env.example` to `.env` and tweak as needed. The settings that matter most:

- `SETU_ASR` — `parakeet` (default), `whisper`, or `fake` for no-model testing.
- `SETU_FALLBACK=cpu` — switch to faster-whisper if you don't have a matching GPU.
- `SETU_SIGN_OUTPUT` / `SETU_SIGN_FRAMES` — turn speech→sign on/off and control whether
  avatar landmark frames are sent along with each sign plan.
- `SETU_SIGN_RESOLVER` — `rules` (default) or `llm` (routes through a local llama-server).

## Privacy

Audio is decoded in memory and dropped right after recognition — nothing is written to
disk (`backend/tests/test_privacy.py` checks this). Trace files only keep timings and IDs
unless you turn on `SETU_STORE_TRANSCRIPTS`.
