import { useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { CameraOff, Hand, Sun, UserRound, Eye, Loader2 } from "lucide-react";
import { drawLandmarks } from "../services/camera/mediapipeSource.js";
import { cx } from "../utils/cx.js";

function Chip({ ok, Icon, children, warn }) {
  return (
    <span className={cx("inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-bold backdrop-blur",
      ok ? "bg-white/85 text-ink" : warn ? "bg-coral text-ink" : "bg-ink/70 text-light")}>
      <Icon className="h-3.5 w-3.5" aria-hidden="true" />{children}
      <span className="sr-only">{ok ? "(ok)" : "(needs attention)"}</span>
    </span>
  );
}

/**
 * The signer's view: webcam (mirrored like a mirror), landmark overlay, and the live HUD from `live` events.
 * Frames reach the overlay through `session.paint(frame)` (camera) and the simulator.
 */
export function CameraStage({ cam, session, mirror = true, className = "", simulated = false, compact = false, emptyActions = null }) {
  const canvas = useRef(null);
  const live = session.live;

  useEffect(() => {
    const c = canvas.current;
    if (!c) return undefined;
    const ctx = c.getContext("2d");
    c.width = 640; c.height = 480;
    const paint = f => {
      if (!f) { ctx.clearRect(0, 0, 640, 480); return; }
      drawLandmarks(ctx, f, { background: cam.state === "on" ? null : "#1F2421" });
    };
    session.onFrame(paint);
    return () => session.onFrame(null);
  }, [session.onFrame, cam.state]); // eslint-disable-line react-hooks/exhaustive-deps

  const on = cam.state === "on";
  const lightOk = live?.lux == null || live.lux >= 40;
  return (
    <div className={cx("relative overflow-hidden bg-ink", className)}>
      <video
        ref={cam.videoRef}
        playsInline muted
        className={cx("absolute inset-0 h-full w-full object-cover transition-opacity", on ? "opacity-100" : "opacity-0", mirror && "-scale-x-100")}
        aria-label="Your camera"
      />
      <canvas ref={canvas} className={cx("absolute inset-0 h-full w-full object-cover", mirror && on && "-scale-x-100")} aria-hidden="true" />

      {!on && !simulated && (
        <div className="absolute inset-0 grid place-items-center p-6 text-center text-light">
          {cam.state === "loading" ? (
            <p className="flex items-center gap-2 text-sm font-semibold"><Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Loading hand tracking…</p>
          ) : (
            <div className="max-w-xs">
              <span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-white/10"><CameraOff className="h-6 w-6" aria-hidden="true" /></span>
              <p className="mt-3 font-bold">Camera is off</p>
              <p className="mt-1 text-sm text-light/70">{cam.error || "Turn it on to sign, or play the simulated signer."}</p>
              {!compact && emptyActions}
            </div>
          )}
        </div>
      )}

      {/* live HUD */}
      <div className="pointer-events-none absolute inset-x-2 top-2 flex flex-wrap gap-1.5">
        {(on || simulated) && (
          <>
            <Chip ok={!!(live?.hands?.R || live?.hands?.L)} Icon={Hand}>
              {live?.hands?.R && live?.hands?.L ? "Both hands" : live?.hands?.R || live?.hands?.L ? "One hand" : "No hands"}
            </Chip>
            {!compact && <Chip ok={live?.anchor !== false} Icon={UserRound}>{live?.anchor === false ? "Step back" : "Framed"}</Chip>}
            <Chip ok={lightOk} warn={!lightOk} Icon={Sun}>{lightOk ? "Light OK" : "Too dark"}</Chip>
            {!compact && live?.brow && live.brow !== "neutral" && <Chip ok Icon={Eye}>Brows {live.brow}</Chip>}
          </>
        )}
      </div>

      {session.signing && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
          className="absolute bottom-2 left-2 inline-flex items-center gap-2 rounded-full bg-coral px-3 py-1.5 text-xs font-extrabold uppercase tracking-wider text-ink">
          <span className="h-2 w-2 animate-pulse rounded-full bg-ink" /> Reading signs
        </motion.div>
      )}
      {live?.hint && (on || simulated) && (
        <div className="absolute inset-x-0 bottom-12 flex justify-center px-3">
          <span className="rounded-full bg-ink/85 px-3 py-1.5 text-sm font-semibold text-light">{live.hint}</span>
        </div>
      )}
    </div>
  );
}
