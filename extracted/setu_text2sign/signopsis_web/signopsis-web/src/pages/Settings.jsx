import { useEffect, useState } from "react";
import { Server, FlaskConical, Wand2, CheckCircle2, XCircle, Loader2, Accessibility, Hand, ShieldCheck, Terminal, Copy } from "lucide-react";
import { PageHeader } from "../components/PageHeader.jsx";
import { Segmented, Toast } from "../components/Bits.jsx";
import { useBackend } from "../hooks/useBackend.js";
import { backend } from "../services/backend.js";
import { config } from "../config.js";
import { usePrefs, resetPrefs } from "../services/prefs.js";
import { clearConsent } from "../components/ConsentSheet.jsx";
import { cx } from "../utils/cx.js";

function Card({ id, Icon, title, sub, children }) {
  return (
    <section id={id} className="card scroll-mt-24 p-5 sm:p-6">
      <div className="flex items-start gap-3">
        <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-sage-soft text-moss-deep"><Icon className="h-5 w-5" aria-hidden="true" /></span>
        <div>
          <h2 className="text-xl font-extrabold">{title}</h2>
          {sub && <p className="text-sm text-mute">{sub}</p>}
        </div>
      </div>
      <div className="mt-5 space-y-5">{children}</div>
    </section>
  );
}

function Row({ label, hint, children, htmlFor }) {
  return (
    <div className="grid gap-2 sm:grid-cols-[14rem_1fr] sm:items-center">
      <div>
        <label htmlFor={htmlFor} className="font-bold">{label}</label>
        {hint && <p className="text-xs text-mute">{hint}</p>}
      </div>
      <div>{children}</div>
    </div>
  );
}

function Toggle({ checked, onChange, label }) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={label} onClick={() => onChange(!checked)}
      className={cx("relative inline-flex h-12 w-20 items-center rounded-full p-1 transition", checked ? "bg-moss" : "bg-ink/15")}>
      <span className={cx("grid h-10 w-10 place-items-center rounded-full bg-white text-xs font-extrabold shadow transition-transform", checked ? "translate-x-8 text-moss-deep" : "text-mute")}>
        {checked ? "ON" : "OFF"}
      </span>
    </button>
  );
}

const SNIPPET = `# 1. start the backend (from the backend repo)
pip install -r requirements.txt
uvicorn signopsis.serve.main:app --port 8000

# 2. start the frontend (from this repo)
cp .env.example .env        # VITE_BACKEND_MODE=live
npm install && npm run dev  # Vite proxies /api, /ws, /healthz to :8000`;

export default function Settings() {
  const b = useBackend();
  const [prefs, setPrefs] = usePrefs();
  const [mode, setMode] = useState(config.mode);
  const [api, setApi] = useState(config.apiBase);
  const [ws, setWs] = useState(config.wsUrl);
  const [user, setUser] = useState(config.user);
  const [testing, setTesting] = useState(false);
  const [toast, setToast] = useState(null);

  useEffect(() => { setMode(config.mode); }, [b.requested]);

  const apply = async () => {
    setTesting(true);
    const r = await backend.configure({ mode, apiBase: api.replace(/\/$/, ""), wsUrl: ws, user: user.trim() || "demo" });
    setTesting(false);
    setToast(r === "live" ? (backend.status.error ? `Live mode, but the server didn't answer: ${backend.status.error}` : "Connected to the SIGNOPSIS server.") : "Running in demo mode.");
  };

  return (
    <div className="mx-auto max-w-4xl px-4 pb-10 sm:px-6">
      <PageHeader n="S20" eyebrow="Settings" title="Make it yours." lead="Connection, accessibility and how SIGNOPSIS reads your signing. Saved on this device." />
      <div className="space-y-4">
        <Card id="backend" Icon={Server} title="Backend connection"
          sub={b.resolved === "live" ? (b.error ? `Live mode · server unreachable (${b.error})` : `Connected · ${b.latencyMs ?? "?"} ms`) : "Demo mode · recorded server outputs, nothing leaves your browser"}>
          <Row label="Mode" hint="Auto tries the server and falls back to demo.">
            <Segmented label="Backend mode" value={mode} onChange={setMode} options={[
              { value: "mock", label: "Demo", icon: <FlaskConical className="h-4 w-4" aria-hidden="true" /> },
              { value: "auto", label: "Auto", icon: <Wand2 className="h-4 w-4" aria-hidden="true" /> },
              { value: "live", label: "Live", icon: <Server className="h-4 w-4" aria-hidden="true" /> },
            ]} />
          </Row>
          <Row label="API base URL" hint="Empty = same origin (dev proxy or the backend serving this app)." htmlFor="api-base">
            <input id="api-base" className="field font-mono text-sm" placeholder="http://127.0.0.1:8000" value={api} onChange={e => setApi(e.target.value)} disabled={mode === "mock"} />
          </Row>
          <Row label="WebSocket URL" hint="Empty = derived from the API base (/ws/sign)." htmlFor="ws-url">
            <input id="ws-url" className="field font-mono text-sm" placeholder="ws://127.0.0.1:8000/ws/sign" value={ws} onChange={e => setWs(e.target.value)} disabled={mode === "mock"} />
          </Row>
          <Row label="User ID" hint="Personal signs are stored under this name." htmlFor="user-id">
            <input id="user-id" className="field" value={user} onChange={e => setUser(e.target.value)} />
          </Row>
          <div className="flex flex-wrap items-center gap-3">
            <button className="btn-primary" onClick={apply} disabled={testing}>
              {testing ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null} Save & test
            </button>
            <span className="flex items-center gap-1.5 text-sm font-semibold">
              {b.resolved === "live" && !b.error ? <CheckCircle2 className="h-4 w-4 text-moss" aria-hidden="true" /> : b.resolved === "live" ? <XCircle className="h-4 w-4 text-coral-deep" aria-hidden="true" /> : <FlaskConical className="h-4 w-4 text-mute" aria-hidden="true" />}
              {b.resolved === "live" ? (b.error ? "Server not reachable" : `Server OK · mode ${b.health?.mode}`) : "Demo data"}
            </span>
          </div>
          <div className="relative rounded-2xl bg-ink p-4 text-light">
            <p className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-sage"><Terminal className="h-4 w-4" aria-hidden="true" /> Connect in two steps</p>
            <pre className="overflow-x-auto font-mono text-[12.5px] leading-relaxed text-light/85">{SNIPPET}</pre>
            <button className="btn-icon absolute right-2 top-2 text-light/70 hover:bg-white/10" aria-label="Copy commands"
              onClick={() => { navigator.clipboard?.writeText(SNIPPET); setToast("Copied"); }}><Copy className="h-4 w-4" /></button>
          </div>
        </Card>

        <Card id="access" Icon={Accessibility} title="Accessibility">
          <Row label="Motion" hint="System follows your device setting.">
            <Segmented label="Motion" value={prefs.motion} onChange={v => setPrefs({ motion: v })}
              options={[{ value: "system", label: "System" }, { value: "reduce", label: "Reduced" }, { value: "full", label: "Full" }]} />
          </Row>
          <Row label="Text size">
            <Segmented label="Text size" value={prefs.textSize} onChange={v => setPrefs({ textSize: v })}
              options={[{ value: "normal", label: "Aa" }, { value: "large", label: "Aa+" }, { value: "huge", label: "Aa++" }]} />
          </Row>
          <Row label="Stronger contrast" hint="Darker secondary text, thicker focus rings.">
            <Toggle checked={prefs.contrast} onChange={v => setPrefs({ contrast: v })} label="Stronger contrast" />
          </Row>
          <Row label="Read captions aloud" hint="For hearing people in the room.">
            <Toggle checked={prefs.voice} onChange={v => setPrefs({ voice: v })} label="Read captions aloud" />
          </Row>
        </Card>

        <Card id="signing" Icon={Hand} title="Signing">
          <Row label="Dominant hand" hint="Sent to the recognizer as config.dominant.">
            <Segmented label="Dominant hand" value={prefs.dominant} onChange={v => setPrefs({ dominant: v })}
              options={[{ value: "right", label: "Right" }, { value: "left", label: "Left" }]} />
          </Row>
          <Row label="Caption language" hint="Output of sign → text.">
            <Segmented label="Caption language" value={prefs.captionLang} onChange={v => setPrefs({ captionLang: v })}
              options={[{ value: "en", label: "English" }, { value: "hi", label: "हिन्दी" }]} />
          </Row>
        </Card>

        <Card id="data" Icon={ShieldCheck} title="Your data" sub="See the Privacy page for what is and isn't sent.">
          <div className="flex flex-wrap gap-2">
            <button className="btn-ghost" onClick={() => { clearConsent(); setToast("Camera and microphone will ask again."); }}>Ask again for camera & mic</button>
            <button className="btn-ghost" onClick={() => { resetPrefs(); setToast("Preferences reset."); }}>Reset preferences</button>
            <a className="btn-ghost" href="#/privacy">Privacy details</a>
            <a className="btn-ghost" href="#/diagnostics">Diagnostics</a>
          </div>
        </Card>
      </div>
      <Toast message={toast} onClose={() => setToast(null)} />
    </div>
  );
}
