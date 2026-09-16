import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { ContactShadows, OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { createAvatar, addLights } from "../lib/avatar/avatar.js";
import { SignPlayer } from "../lib/signPlayer.js";
import { usePrefersReducedMotion } from "../hooks/useMediaQuery.js";
import { cx } from "../utils/cx.js";

export const VIEWS = {
  front: { pos: [0, 1.46, 2.25], tgt: [0, 1.36, 0], label: "Front" },
  three: { pos: [1.25, 1.55, 1.9], tgt: [0, 1.36, 0], label: "¾" },
  hands: { pos: [0.15, 1.38, 1.25], tgt: [0, 1.32, 0.2], label: "Hands" },
  side: { pos: [2.2, 1.5, 0.4], tgt: [0, 1.36, 0.1], label: "Side" },
  full: { pos: [0, 1.0, 3.6], tgt: [0, 0.94, 0], label: "Full" },
};

export const AVATAR_LOOKS = {
  classic: { skin: "#f9c8a2", hair: "#141418", hoodie: "#15161a", jeans: "#a9c6e4", label: "Classic" },
  moss: { skin: "#d69b72", hair: "#141418", hoodie: "#4E7A36", jeans: "#2f4466", label: "Moss" },
  coral: { skin: "#a86f4c", hair: "#4a2e1c", hoodie: "#b8574f", jeans: "#a9c6e4", label: "Coral" },
  paper: { skin: "#fcdcc4", hair: "#8a3a1e", hoodie: "#e9e9ea", jeans: "#2a2b30", label: "Paper" },
};

function AvatarRig({ player, view, look, onPick, expression }) {
  const avatar = useMemo(() => createAvatar(), []);
  const { camera, gl } = useThree();
  const controls = useRef();
  const anim = useRef(null);
  const reduced = usePrefersReducedMotion();
  const wasSigning = useRef(false);

  useEffect(() => { avatar.setColors(AVATAR_LOOKS[look] || AVATAR_LOOKS.classic); }, [avatar, look]);
  useEffect(() => { avatar.setExpression(expression); }, [avatar, expression]);

  useEffect(() => {
    const v = VIEWS[view] || VIEWS.front;
    const portrait = gl.domElement.clientWidth / Math.max(1, gl.domElement.clientHeight) < 0.8;
    const k = portrait ? 1.75 : 1;
    const tg = new THREE.Vector3(...v.tgt);
    const ps = new THREE.Vector3(...v.pos).sub(tg).multiplyScalar(k).add(tg);
    if (!controls.current || reduced) {
      camera.position.copy(ps);
      controls.current?.target.copy(tg);
      camera.lookAt(tg);
      return;
    }
    anim.current = { t: 0, p0: camera.position.clone(), q0: controls.current.target.clone(), p1: ps, q1: tg };
  }, [view, camera, gl, reduced]);

  useFrame((st, dt) => {
    const d = Math.min(dt, 0.05);
    const f = player.tick(d);
    const signing = !!(player.playing || player.override);
    if (signing !== wasSigning.current) { avatar.setSigning(signing); wasSigning.current = signing; }
    avatar.update(f, st.clock.elapsedTime, d);
    const a = anim.current;
    if (a && controls.current) {
      a.t = Math.min(1, a.t + d * 1.8);
      const u = a.t * a.t * (3 - 2 * a.t);
      camera.position.lerpVectors(a.p0, a.p1, u);
      controls.current.target.lerpVectors(a.q0, a.q1, u);
      if (a.t >= 1) anim.current = null;
    }
    controls.current?.update();
  });

  return (
    <>
      <primitive object={avatar.group} onClick={e => { e.stopPropagation(); onPick?.(); }} />
      <ContactShadows position={[0, 0.001, 0]} opacity={0.35} scale={3} blur={2.6} far={1.6} />
      <OrbitControls ref={controls} makeDefault enableDamping enablePan={false} minDistance={0.5} maxDistance={6}
        target={VIEWS.front.tgt} maxPolarAngle={Math.PI * 0.62} />
    </>
  );
}

function Lights() {
  const { scene } = useThree();
  useEffect(() => {
    const l = addLights(scene);
    return () => Object.values(l).forEach(o => scene.remove(o));
  }, [scene]);
  return null;
}

/**
 * The 3D signer. Pass a SignPlayer (or let it create one) and call player.load(clip).
 * ref exposes { player, snapshot() }.
 */
export const AvatarStage = forwardRef(function AvatarStage(
  { player: external, view = "front", look = "classic", expression = "auto", className = "", onPick, children, background = "sage", label = "3D signing avatar" },
  ref,
) {
  const own = useMemo(() => new SignPlayer(), []);
  const player = external || own;
  const glRef = useRef(null);
  const [ready, setReady] = useState(false);
  useImperativeHandle(ref, () => ({
    player,
    snapshot: () => glRef.current?.domElement.toDataURL("image/png"),
  }), [player]);

  const bg = {
    sage: "radial-gradient(120% 90% at 50% 18%, #EEF3E6 0%, #CFE0BC 48%, #91AE6E 100%)",
    coral: "radial-gradient(120% 90% at 50% 18%, #FBEDEC 0%, #F0C3BF 50%, #D96868 100%)",
    ink: "radial-gradient(120% 90% at 50% 10%, #3A403C 0%, #1F2421 70%)",
    light: "radial-gradient(120% 90% at 50% 18%, #FFFFFF 0%, #F2F2F2 60%, #DCE7CF 100%)",
    chroma: "#43c22e",
  }[background] || background;

  return (
    <div className={cx("relative overflow-hidden", className)} style={{ background: bg }}>
      <Canvas
        dpr={[1, 1.75]}
        camera={{ fov: 28, near: 0.05, far: 50, position: VIEWS.front.pos }}
        gl={{ antialias: true, alpha: true, preserveDrawingBuffer: true }}
        onCreated={({ gl }) => {
          glRef.current = gl;
          gl.toneMapping = THREE.ACESFilmicToneMapping;
          gl.toneMappingExposure = 1.05;
          setReady(true);
        }}
        aria-label={label}
        role="img"
      >
        <Lights />
        <AvatarRig player={player} view={view} look={look} onPick={onPick} expression={expression} />
      </Canvas>
      {!ready && (
        <div className="absolute inset-0 grid place-items-center text-sm font-semibold text-ink/60">Waking the signer…</div>
      )}
      {children}
    </div>
  );
});
