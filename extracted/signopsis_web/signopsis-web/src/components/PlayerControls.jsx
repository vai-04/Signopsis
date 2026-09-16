import { Pause, Play, RotateCcw, Repeat, Gauge } from "lucide-react";
import { cx } from "../utils/cx.js";

const SPEEDS = [0.5, 0.75, 1, 1.25];

/** transport for a SignPlayer snapshot */
export function PlayerControls({ player, snap, className = "", dark = false, disabled = false }) {
  const pct = snap.total ? (snap.t / snap.total) * 100 : 0;
  const base = dark ? "bg-white/10 text-light hover:bg-white/20" : "bg-white text-ink hover:bg-ink hover:text-light";
  return (
    <div className={cx("flex items-center gap-2", className)}>
      <button type="button" className={cx("btn-icon shadow-sm", base)} disabled={disabled || !snap.hasClip}
        onClick={() => player.toggle()} aria-label={snap.playing ? "Pause signing" : "Play signing"}>
        {snap.playing ? <Pause className="h-5 w-5" /> : <Play className="h-5 w-5" />}
      </button>
      <button type="button" className={cx("btn-icon shadow-sm", base)} disabled={disabled || !snap.hasClip}
        onClick={() => { player.seek(0); player.play(); }} aria-label="Replay from the start">
        <RotateCcw className="h-5 w-5" />
      </button>
      <label className="relative flex h-12 min-w-0 flex-1 items-center">
        <span className="sr-only">Signing timeline</span>
        <input
          type="range" min={0} max={1000} value={Math.round(pct * 10)} disabled={disabled || !snap.hasClip}
          onChange={e => { player.pause(); player.seek((+e.target.value / 1000) * snap.total); }}
          className={cx("h-2 w-full cursor-pointer appearance-none rounded-full", dark ? "accent-[#91AE6E]" : "accent-[#1F2421]")}
          style={{ background: `linear-gradient(to right, ${dark ? "#91AE6E" : "#1F2421"} ${pct}%, ${dark ? "rgba(255,255,255,.2)" : "rgba(31,36,33,.12)"} ${pct}%)` }}
        />
      </label>
      <button type="button" className={cx("btn h-12 px-3 text-sm shadow-sm", base)}
        onClick={() => player.setSpeed(SPEEDS[(SPEEDS.indexOf(snap.speed) + 1) % SPEEDS.length])}
        aria-label={`Playback speed ${snap.speed}x, press to change`}>
        <Gauge className="h-4 w-4" aria-hidden="true" />{snap.speed}×
      </button>
      <button type="button" aria-pressed={snap.loop} className={cx("btn-icon shadow-sm", base, snap.loop && (dark ? "bg-sage text-ink" : "bg-ink text-light"))}
        onClick={() => player.setLoop(!snap.loop)} aria-label="Loop">
        <Repeat className="h-5 w-5" />
      </button>
    </div>
  );
}
