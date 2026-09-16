import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Activity, Cpu, RefreshCw, Server, Loader2 } from "lucide-react";
import { backend } from "../services/backend.js";
import { metrics } from "../services/metrics.js";
import { useBackend } from "../hooks/useBackend.js";
import { cx } from "../utils/cx.js";

const INK = "#1F2421", MOSS = "#689D4B", SAGE = "#91AE6E", CORAL = "#D96868";
const PROBES = ["I went to the bank yesterday.", "What is your name?", "Please help me, I need a doctor.", "Thank you! See you tomorrow.", "Where is the hospital?", "I don't understand."];

function Panel({ title, sub, children, className = "", right }) {
  return (
    <section className={cx("card p-4 sm:p-5", className)}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-lg font-extrabold">{title}</h3>
          {sub && <p className="text-xs font-semibold text-mute">{sub}</p>}
        </div>
        {right}
      </div>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function Reliability({ bins }) {
  const W = 300, H = 220, p = 30;
  const x = v => p + v * (W - p - 8), y = v => H - p - v * (H - p - 8);
  const maxN = Math.max(...bins.map(b => b[2]));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Reliability diagram: predicted trust against observed accuracy">
      {[0, 0.25, 0.5, 0.75, 1].map(v => (
        <g key={v}>
          <line x1={x(0)} x2={x(1)} y1={y(v)} y2={y(v)} stroke={INK} strokeOpacity=".07" />
          <text x={p - 6} y={y(v) + 3} fontSize="9" textAnchor="end" fill={INK} fillOpacity=".55">{v}</text>
          <text x={x(v)} y={H - p + 14} fontSize="9" textAnchor="middle" fill={INK} fillOpacity=".55">{v}</text>
        </g>
      ))}
      <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)} stroke={INK} strokeDasharray="4 4" strokeOpacity=".35" />
      {bins.map(([c, a, n], i) => (
        <motion.circle key={i} cx={x(c)} cy={y(a)} r={3 + 9 * Math.sqrt(n / maxN)} fill={Math.abs(c - a) > 0.15 ? CORAL : MOSS} fillOpacity=".75"
          initial={{ scale: 0 }} whileInView={{ scale: 1 }} viewport={{ once: true }} transition={{ delay: i * 0.05 }} />
      ))}
      <motion.polyline fill="none" stroke={MOSS} strokeWidth="2" points={bins.map(([c, a]) => `${x(c)},${y(a)}`).join(" ")}
        initial={{ pathLength: 0 }} whileInView={{ pathLength: 1 }} viewport={{ once: true }} transition={{ duration: 1.2 }} />
      <text x={x(0.5)} y={H - 2} fontSize="9.5" textAnchor="middle" fill={INK}>trust score</text>
      <text x={9} y={y(0.5)} fontSize="9.5" textAnchor="middle" fill={INK} transform={`rotate(-90 9 ${y(0.5)})`}>accuracy</text>
    </svg>
  );
}

function Bars({ data }) {
  // data: [{label, a, b}] a=emit rate, b=confidently wrong
  const W = 300, H = 200, p = 26, bw = (W - p) / data.length;
  const maxB = Math.max(0.08, ...data.map(d => d.b));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="By camera condition: share shown, and confidently wrong rate">
      {data.map((d, i) => {
        const x0 = p + i * bw + 4, h1 = d.a * (H - p - 20), h2 = (d.b / maxB) * (H - p - 20);
        return (
          <g key={d.label}>
            <motion.rect x={x0} width={bw / 2 - 5} rx="4" fill={SAGE} initial={{ height: 0, y: H - p }} whileInView={{ height: h1, y: H - p - h1 }} viewport={{ once: true }} transition={{ delay: i * 0.06 }} />
            <motion.rect x={x0 + bw / 2 - 3} width={bw / 2 - 5} rx="4" fill={CORAL} initial={{ height: 0, y: H - p }} whileInView={{ height: h2, y: H - p - h2 }} viewport={{ once: true }} transition={{ delay: i * 0.06 + 0.1 }} />
            <text x={x0 + bw / 2 - 5} y={H - p + 13} fontSize="9" textAnchor="middle" fill={INK} fillOpacity=".6">{d.label}</text>
            <text x={x0 + bw * 0.75 - 5} y={H - p - h2 - 4} fontSize="8.5" textAnchor="middle" fill={CORAL} fontWeight="700">{(d.b * 100).toFixed(1)}%</text>
          </g>
        );
      })}
      <text x={p} y={H - 2} fontSize="9.5" fill={INK}>camera condition: studio → awful</text>
    </svg>
  );
}

function Spark({ values, color = MOSS, height = 64, label }) {
  const W = 300, H = height;
  if (values.length < 2) return <p className="grid h-16 place-items-center text-sm text-mute">Not enough data yet</p>;
  const max = Math.max(...values, 1), min = Math.min(...values, 0);
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * W},${H - 4 - ((v - min) / (max - min || 1)) * (H - 8)}`);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" preserveAspectRatio="none" role="img" aria-label={label}>
      <polygon points={`0,${H} ${pts.join(" ")} ${W},${H}`} fill={color} fillOpacity=".12" />
      <polyline points={pts.join(" ")} fill="none" stroke={color} strokeWidth="2.5" strokeLinejoin="round" />
    </svg>
  );
}

function Stat({ k, v, tone }) {
  return (
    <div className="rounded-2xl bg-light p-3">
      <p className={cx("text-3xl font-extrabold tabular-nums tracking-tight", tone === "coral" && "text-coral-deep", tone === "moss" && "text-moss-deep")}>{v}</p>
      <p className="text-[11px] font-bold uppercase tracking-wider text-mute">{k}</p>
    </div>
  );
}

/** S18 Diagnostics: trust-model evaluation + this session's live numbers + the mode/VRAM plan. */
export function Diagnostics({ variant = "page" }) {
  const embed = variant === "embed";
  const b = useBackend();
  const [report, setReport] = useState(null);
  const [mode, setMode] = useState(null);
  const [switching, setSwitching] = useState(null);
  const [, tick] = useState(0);

  useEffect(() => metrics.subscribe(() => tick(t => t + 1)), []);
  useEffect(() => {
    backend.evalReport().then(setReport).catch(() => setReport(null));
    backend.getMode().then(setMode).catch(() => {});
    // probe a few sentences so round-trip and latency panels have real data
    if (metrics.roundtrips.length < 3) PROBES.forEach((t, i) => setTimeout(() => backend.textToSign({ text: t }).catch(() => {}), i * 120));
  }, [b.resolved]);

  const res = metrics.results;
  const minutes = Math.max(1, (Date.now() - metrics.started) / 60000);
  const repairs = res.filter(r => r.state === "repair").length;
  const lat = res.map(r => r.latency).filter(v => v != null);
  const p50 = lat.length ? [...lat].sort((a, c) => a - c)[Math.floor(lat.length / 2)] : null;
  const perMinute = useMemo(() => {
    const buckets = Array(10).fill(0);
    res.forEach(r => {
      const m = Math.floor((Date.now() - r.at) / 30000);
      if (m < 10 && r.state === "repair") buckets[9 - m] += 1;
    });
    return buckets;
  }, [res.length]); // eslint-disable-line
  const rtGloss = metrics.roundtrips.flatMap(r => r.perGloss).filter(g => g.rt != null);
  const rtBySign = Object.values(rtGloss.reduce((m, g) => { (m[g.g] ||= { g: g.g, sum: 0, n: 0, fs: g.fs }); m[g.g].sum += g.rt; m[g.g].n += 1; return m; }, {}))
    .map(x => ({ ...x, rt: x.sum / x.n })).sort((a, c) => a.rt - c.rt).slice(0, embed ? 6 : 10);

  const sev = report ? Object.entries(report.by_severity).map(([k, v]) => ({ label: k, a: v.emit_rate, b: v.confidently_wrong })) : [];

  const changeMode = async m => {
    setSwitching(m);
    try { setMode(await backend.setMode(m)); } finally { setSwitching(null); }
  };

  return (
    <div className={cx("grid grid-cols-1 gap-4 [&>*]:min-w-0", embed ? "md:grid-cols-3" : "md:grid-cols-2 xl:grid-cols-3")}>
      <Panel title="Calibration" sub={report ? `When it says it's sure, is it right? ECE ${report.ece.toFixed(3)}` : "loading"}>
        {report ? <Reliability bins={report.reliability_bins} /> : <div className="h-48 animate-pulse rounded-2xl bg-light" />}
      </Panel>
      <Panel title="Confidently wrong" sub="Shown-but-wrong signs, by camera condition"
        right={report && <span className="rounded-full bg-coral-soft px-2 py-1 text-xs font-extrabold text-ink">{(report.confidently_wrong_rate * 100).toFixed(1)}% overall</span>}>
        {report ? <Bars data={sev} /> : <div className="h-48 animate-pulse rounded-2xl bg-light" />}
        <div className="mt-2 flex gap-4 text-[11px] font-semibold text-mute">
          <span className="flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-sm bg-sage" /> shown</span>
          <span className="flex items-center gap-1"><i className="hatch h-2.5 w-2.5 rounded-sm bg-coral" /> confidently wrong</span>
        </div>
      </Panel>
      <Panel title="This session" sub={`${res.length} results · ${minutes.toFixed(1)} min`}>
        <div className="grid grid-cols-3 gap-2">
          <Stat k="repairs / min" v={(repairs / minutes).toFixed(1)} tone="coral" />
          <Stat k="held" v={res.filter(r => r.state === "hold").length} />
          <Stat k="p50 latency" v={p50 != null ? `${p50}ms` : "—"} tone="moss" />
        </div>
        <p className="mt-3 text-xs font-bold uppercase tracking-wider text-mute">Repairs, last 5 minutes</p>
        <Spark values={perMinute} color={CORAL} label="Repairs per 30 seconds" />
      </Panel>
      <Panel title="Round-trip intelligibility" sub="How clearly the avatar's own signing reads back (lowest first)">
        <ul className="space-y-1.5">
          {rtBySign.length === 0 && <li className="h-40 animate-pulse rounded-2xl bg-light" />}
          {rtBySign.map(x => (
            <li key={x.g} className="grid grid-cols-[7rem_1fr_3rem] items-center gap-2 text-xs">
              <span className={cx("truncate font-mono font-bold", x.fs && "italic")}>{x.g.replace("FS:", "✎ ")}</span>
              <span className="h-2.5 overflow-hidden rounded-full bg-light">
                <motion.span className="block h-full rounded-full" style={{ background: x.rt < 0.8 ? CORAL : MOSS }}
                  initial={{ width: 0 }} animate={{ width: `${x.rt * 100}%` }} />
              </span>
              <span className="text-right font-bold tabular-nums">{Math.round(x.rt * 100)}%</span>
            </li>
          ))}
        </ul>
      </Panel>
      <Panel title="Latency" sub="End of phrase or request → plan (ms)">
        <Spark values={lat.slice(-40)} color={INK} height={90} label="Latency over time" />
        <p className="mt-2 text-xs text-mute">Server-reported totals are in each RenderPlan's <code className="font-mono">timings_ms</code>.</p>
      </Panel>
      <Panel title="Models on the GPU" sub={mode ? `${mode.planned_vram_gb} of ${mode.budget_gb} GB planned` : "loading"}
        right={b.resolved === "live" ? <Server className="h-5 w-5 text-moss" aria-label="live server" /> : <Cpu className="h-5 w-5 text-mute" aria-label="demo" />}>
        {mode && (
          <>
            <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="Pipeline mode">
              {["WATCH", "SPEAK", "CONVERSE", "LISTEN", "SCREEN"].map(m => (
                <button key={m} role="radio" aria-checked={mode.mode === m} onClick={() => changeMode(m)} disabled={!!switching}
                  className={cx("min-h-10 rounded-full px-3 font-mono text-[11px] font-bold", mode.mode === m ? "bg-ink text-light" : "bg-light hover:bg-ink/10")}>
                  {switching === m ? <Loader2 className="inline h-3 w-3 animate-spin" /> : m}
                </button>
              ))}
            </div>
            <div className="mt-3 flex h-3 overflow-hidden rounded-full bg-light" aria-hidden="true">
              {Object.entries(mode.components).filter(([n]) => mode.resident.includes(n)).map(([n, c], i) => (
                <motion.span key={n} layout className="h-full border-r-2 border-white" style={{ width: `${(c.vram_gb / mode.budget_gb) * 100}%`, background: [MOSS, SAGE, CORAL, INK][i % 4] }} />
              ))}
            </div>
            {!embed && (
              <ul className="mt-3 grid grid-cols-2 gap-1 text-[11px]">
                {Object.entries(mode.components).map(([n, c]) => (
                  <li key={n} className={cx("flex justify-between rounded-lg px-2 py-1", mode.resident.includes(n) ? "bg-sage-soft font-bold" : "text-mute")}>
                    <span>{n.replace("_", " ")}</span><span className="tabular-nums">{c.vram_gb} GB</span>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </Panel>
      {!embed && (
        <Panel title="Connection" className="md:col-span-2 xl:col-span-3" sub={b.resolved === "live" ? "Talking to the SIGNOPSIS server" : "Demo mode: recorded server outputs in this browser"}
          right={<button className="btn-ghost min-h-11 px-3 text-sm" onClick={() => backend.resolve(true)}><RefreshCw className="h-4 w-4" aria-hidden="true" /> Re-check</button>}>
          <div className="grid gap-2 sm:grid-cols-4">
            <Stat k="backend" v={b.resolved || "…"} tone={b.resolved === "live" ? "moss" : undefined} />
            <Stat k="health" v={b.health ? "ok" : b.resolved === "live" ? "down" : "n/a"} />
            <Stat k="ping" v={b.latencyMs != null ? `${b.latencyMs}ms` : "—"} />
            <Stat k="phrases shown (eval)" v={report ? `${Math.round(report.phrase_emit_rate * 100)}%` : "—"} />
          </div>
          {b.error && b.requested !== "mock" && <p className="mt-2 flex items-center gap-2 text-sm text-coral-deep"><Activity className="h-4 w-4" aria-hidden="true" /> {b.error}</p>}
        </Panel>
      )}
    </div>
  );
}
