import { useEffect, useRef } from "react";
import { solveFrame, REST } from "../lib/avatar/rig.js";
import { usePrefersReducedMotion } from "../hooks/useMediaQuery.js";

const D2R = Math.PI / 180;

/**
 * Lightweight flat 2D signer (canvas) for thumbnails: repair previews, library cards.
 * Uses the same rig solver as the 3D avatar, so a clip looks the same in both.
 */
export function MiniSigner({ clip, className = "", loop = true, pauseMs = 500, label, animate = true, color = "#1F2421" }) {
  const ref = useRef(null);
  const reduced = usePrefersReducedMotion();

  useEffect(() => {
    const cv = ref.current;
    if (!cv) return undefined;
    const ctx = cv.getContext("2d");
    let raf = 0, visible = true, t0 = performance.now();
    const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; });
    io.observe(cv);

    let drawn = false;
    const draw = now => {
      raf = requestAnimationFrame(draw);
      if (!visible) return;
      if (!animate && drawn && cv.width === Math.round(cv.clientWidth * Math.min(window.devicePixelRatio || 1, 2))) return;
      drawn = true;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const W = cv.clientWidth, H = cv.clientHeight;
      if (!W || !H) return;
      if (cv.width !== Math.round(W * dpr)) { cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, W, H);

      let frame = { Rq: REST.R, Lq: REST.L, face: null };
      const F = clip?.frames;
      if (F?.length) {
        const total = (clip.total_ms || F.length * 33) + pauseMs;
        const ms = reduced || !animate ? total * 0.45 : loop ? (now - t0) % total : Math.min(now - t0, total);
        const i = Math.max(0, Math.min(F.length - 1, Math.floor(Math.max(0, ms) / (1000 / clip.fps))));
        frame = F[i];
      }
      const s = solveFrame({ Rq: frame.Rq, Lq: frame.Lq, face: frame.face });
      // world (metres, y up, shoulders ~1.44) -> canvas
      const k = H / 1.02;
      const P = v => [W / 2 + v.x * k, H * 0.2 + (1.62 - v.y) * k];

      // body
      ctx.fillStyle = color;
      const [lsx, lsy] = P(s.L.S), [rsx, rsy] = P(s.R.S);
      ctx.beginPath();
      ctx.moveTo(rsx - 6, rsy + 4);
      ctx.quadraticCurveTo(W / 2, rsy - 10, lsx + 6, lsy + 4);
      ctx.lineTo(lsx + 12, H + 10);
      ctx.lineTo(rsx - 12, H + 10);
      ctx.closePath();
      ctx.fill();
      // collar
      ctx.fillStyle = "#F2F2F2";
      ctx.beginPath(); ctx.ellipse(W / 2, rsy - 2, k * 0.07, k * 0.025, 0, 0, Math.PI * 2); ctx.fill();
      // head
      const [hx, hy] = P({ x: 0, y: 1.63 });
      const hr = k * 0.13;
      ctx.fillStyle = "#f9c8a2";
      ctx.beginPath(); ctx.ellipse(hx, hy, hr * 0.92, hr, 0, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = "#141418";
      for (let a = -2.7; a <= -0.4; a += 0.32) {
        ctx.beginPath(); ctx.arc(hx + Math.cos(a) * hr * 0.9, hy + Math.sin(a) * hr * 0.95, hr * 0.3, 0, Math.PI * 2); ctx.fill();
      }
      // face
      const brow = frame.face?.brow;
      ctx.strokeStyle = "#1F2421"; ctx.lineWidth = Math.max(1.4, hr * 0.07); ctx.lineCap = "round";
      for (const sx of [-1, 1]) {
        ctx.beginPath(); ctx.arc(hx + sx * hr * 0.36, hy + hr * 0.05, hr * 0.12, Math.PI * 1.1, Math.PI * 1.9); ctx.stroke();
        const by = hy - hr * (brow === "raised" ? 0.34 : 0.24);
        ctx.beginPath();
        ctx.moveTo(hx + sx * hr * 0.2, by + (brow === "furrowed" ? hr * 0.08 : 0));
        ctx.lineTo(hx + sx * hr * 0.5, by);
        ctx.stroke();
      }
      ctx.fillStyle = "#b8574f";
      ctx.beginPath(); ctx.arc(hx, hy + hr * 0.38, hr * (frame.face?.mouth === "open" ? 0.2 : 0.16), 0, Math.PI); ctx.fill();

      // arms + hands (far arm first)
      for (const side of ["L", "R"]) {
        const a = s[side];
        const [sx, sy] = P(a.S), [ex, ey] = P(a.E), [wx, wy] = P(a.W);
        ctx.strokeStyle = "#2b312d"; ctx.lineWidth = k * 0.07;
        ctx.beginPath(); ctx.moveTo(sx, sy); ctx.lineTo(ex, ey); ctx.lineTo(wx, wy); ctx.stroke();
        const q = side === "R" ? frame.Rq : frame.Lq;
        const r = q.r * D2R;
        const dx = Math.sin(r), dy = -Math.cos(r);
        const palm = k * 0.05;
        const cx0 = wx + dx * palm * 0.9, cy0 = wy + dy * palm * 0.9;
        ctx.fillStyle = side === "R" ? "#f4bb92" : "#f9c8a2";
        ctx.beginPath(); ctx.arc(cx0, cy0, palm, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = ctx.fillStyle; ctx.lineWidth = palm * 0.42;
        const px = -dy, py = dx;           // across the palm
        const mirror = side === "R" ? 1 : -1;
        q.c.forEach((curl, fi) => {
          const across = (fi - 2) * 0.42 * mirror * (1 + q.s * 0.5);
          const len = palm * (fi === 0 ? 1.0 : 1.55) * (1 - Math.min(0.85, curl * 0.9));
          const bx = cx0 + px * across * palm + dx * palm * 0.5;
          const by2 = cy0 + py * across * palm + dy * palm * 0.5;
          const fdx = fi === 0 ? dx * 0.4 + px * mirror * -0.9 : dx + px * across * 0.25;
          const fdy = fi === 0 ? dy * 0.4 + py * mirror * -0.9 : dy + py * across * 0.25;
          ctx.beginPath(); ctx.moveTo(bx, by2); ctx.lineTo(bx + fdx * len, by2 + fdy * len); ctx.stroke();
        });
      }
      if (frame.ch) {
        ctx.fillStyle = "#1F2421";
        ctx.font = `800 ${Math.round(H * 0.16)}px "JetBrains Mono Variable", monospace`;
        ctx.textAlign = "right";
        ctx.fillText(frame.ch, W - 8, H * 0.2);
      }
    };
    raf = requestAnimationFrame(draw);
    return () => { cancelAnimationFrame(raf); io.disconnect(); };
  }, [clip, loop, pauseMs, reduced, animate, color]);

  return <canvas ref={ref} className={className} style={{ width: "100%", height: "100%" }} role="img" aria-label={label || "Sign preview"} />;
}
