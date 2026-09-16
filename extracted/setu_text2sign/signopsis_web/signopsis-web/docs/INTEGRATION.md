# Connecting the SIGNOPSIS web app to the backend

Every screen talks to one object: `src/services/backend.js`. That object decides at runtime whether to call the FastAPI server (**live**) or the in-browser replica (**mock**). The mock serves real recorded server outputs, so both paths return the **same shapes**.

## 1. Choose how to connect

| Setup | What to do |
|---|---|
| Dev, two processes | Backend: `uvicorn signopsis.serve.main:app --port 8000`. Frontend: `VITE_BACKEND_MODE=live npm run dev`. Vite proxies `/api`, `/ws` and `/healthz` to `VITE_BACKEND_ORIGIN`. |
| Frontend on another host | Set `VITE_API_BASE=https://api.example.com` (and `VITE_WS_URL=wss://api.example.com/ws/sign` if it differs). Add your origin to `SIGNOPSIS_CORS_ORIGINS` on the server. |
| Served by the backend | `npm run build`, then copy `dist/` to `signopsis/serve/web/` (or set `SIGNOPSIS_WEB_DIST`). Open `http://host:8000/app/`. |
| No code change | Use **Settings → Backend connection**, or add `?backend=live&api=http://host:8000` to the URL. |

**Mode rules:**

- `auto` checks `GET /healthz` once and falls back to mock if it fails.
- `live` stays live and shows errors in the header badge.
- `mock` never touches the network.

## 2. Contract map

| Screen / hook | Call | Request → response |
|---|---|---|
| `useTextToSign`, Converse (hearing side), Live stage, Compose, Screen Glance | `POST /api/text-to-sign` | `{text, resolutions?, seed?, src_lang?, sign_lang?}` → `{frame: SemanticFrame, plan: RenderPlan, readback, frames: AvatarClip, sign_lang_fallback?}` |
| `useSignSession` (Converse, Teach) | `WS /ws/sign?user&lang&dominant` | Client messages: `frame` / `batch` / `repair_choice` / `enroll_start{label,kind,scope}` / `enroll_from_unknown` / `enroll_undo` / `enroll_cancel` / `forget_sign` / `list_signs` / `config` / `flush` / `reset` / `hello`. Server events: `hello` / `live` / `phrase_start` / `partial` / `result` / `teach_offer` / `enroll_progress` / `enrolled` / `signs` / `repair_done` / `config` / `reset` / `error`. |
| Simulated signer | `GET /api/simcam?text\|gloss&severity&seed&t0&speed` | `{frames: WireFrame[], info, degrade}`. The frames are streamed through the WebSocket in real time. |
| RepairCard previews, Library | `GET /api/sign/{gloss}` | `AvatarClip` |
| Library, sign-language status | `GET /api/lexicon` | `{signs, vocab_without_sign, unlisted_demo_signs, sign_langs}` |
| Library | `GET /api/users/{u}/signs`, `DELETE /api/users/{u}/signs/{label}` | `{signs: PersonalSign[]}` / `{removed}` |
| Diagnostics | `GET/POST /api/mode` | `{mode, resident, planned_vram_gb, budget_gb, fits, components}` |
| Diagnostics | `GET /api/eval/report` | `{reliability_bins, by_severity, ece, confidently_wrong_rate, …}` |
| Screen Glance | `POST /api/screen/describe` | `{question, intent?, snapshot}` → `{intent, answer, targets[]}`. If the server returns 404, the app uses the local describer. |
| Header badge | `GET /healthz` | `{ok, mode}` |

All types are in `src/contracts/contracts.d.ts`, mirrored from `signopsis/schemas/__init__.py`.

## 3. How backend output becomes UI

`src/services/adapters.js` is the only place that interprets backend fields.

- **Trust state.** `gate` maps to a trust state:
  - `emit` → **Clear**
  - `repair` → **Checking**
  - `hold` → **Held**
  - **Enhanced** is `emit` where a slot's `source` is `context`/`user`, or the user answered a repair.
- **Reasons.** `gate_reason` strings are shown after `humanReason()` strips the numbers. The raw values stay available to Diagnostics.
- **Captions and voice.** `RenderPlan.targets` supply the caption (`caption`), the voice (`tts`, spoken with Web Speech) and the avatar clip (`sign`).
- **Repairs.** A `RenderPlan.repair` becomes a RepairCard:
  - `disambiguate` sends `resolutions[token_index]` back to the server (text → sign), or `repair_choice{slot, choice}` (sign → text).
  - `confirm` (SEND / REPHRASE) is decided on the client.
  - `resign` shows "Held" with Teach / Dismiss.

## 4. Keeping mock mode honest

When the backend changes, regenerate the fixtures from the backend repo:

```bash
cd ../signopsis-backend
python ../signopsis-web/scripts/export_fixtures.py ../signopsis-web/src/mocks
cd ../signopsis-web && npm test
```

This rewrites the following files in `src/mocks/`:

- `sign_bank.json`: per-sign 3D clips.
- `t2s.json`: `/api/text-to-sign` for the featured sentences, including repair branches.
- `s2t.json`: recorded `/ws/sign` transcripts.
- `simcam_sample.json`, `lexicon.json` and `vocab.json`.

## 5. Adding a sign-language pack

The UI already sends `sign_lang` and reads `GET /api/lexicon → sign_langs`. To add a pack:

1. Add its lexicon on the server.
2. Append its code to `SIGN_LANGS` in `signopsis/serve/main.py`.
3. Return that code in `SignTarget.sign_lang`.

The Live stage and Compose pickers then mark that language **ready** automatically.

## 6. Adding a spoken language

The resolver currently handles `en`, `hi` and Hinglish (`hi-en`). `detectLanguage()` also recognises Tamil, Bengali, Telugu, Marathi, Gujarati, Punjabi, Kannada, Malayalam, Urdu, Spanish and French. To support one of these:

- **Server:** extend the resolver.
- **Client:** add the code to `RESOLVER_LANGS` in `src/services/speech.js`.

Until then, unsupported languages are captioned and **held** with a clear reason.
