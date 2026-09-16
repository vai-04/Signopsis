import { Suspense, useMemo, useRef } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Float, MeshDistortMaterial, Sparkles } from "@react-three/drei";
import * as THREE from "three";
import { usePrefersReducedMotion } from "../hooks/useMediaQuery.js";

/**
 * "Signal field": the brand scene. Two particle streams (voice on one side, hands on the other)
 * flow into a living core. The scene *is* the trust state:
 *   idle      slow drift, pale core
 *   signing   streams speed up, core ripples
 *   high      core settles, deep green, streams braid cleanly
 *   enhanced  sage core with sparkles (context / memory helped)
 *   repair    core splits into two candidates that orbit each other (coral)
 *   hold      streams freeze into a ring, charcoal core stops moving
 */
const STATE = {
  idle: { core: "#DCE7CF", distort: 0.25, speed: 0.35, flow: 0.45, split: 0, ring: 0, sparkle: 0 },
  signing: { core: "#91AE6E", distort: 0.5, speed: 1.4, flow: 1.4, split: 0, ring: 0, sparkle: 0 },
  high: { core: "#689D4B", distort: 0.2, speed: 0.6, flow: 0.9, split: 0, ring: 0, sparkle: 0 },
  enhanced: { core: "#91AE6E", distort: 0.3, speed: 0.8, flow: 1, split: 0, ring: 0, sparkle: 1 },
  repair: { core: "#D96868", distort: 0.42, speed: 0.9, flow: 0.7, split: 1, ring: 0, sparkle: 0 },
  hold: { core: "#2b312d", distort: 0.04, speed: 0.08, flow: 0.08, split: 0, ring: 1, sparkle: 0 },
};

const N = 900;
const tmpC = new THREE.Color();

function Streams({ state, reduced }) {
  const pts = useRef();
  const cfg = STATE[state] || STATE.idle;
  const cur = useRef({ flow: cfg.flow, ring: cfg.ring });
  const data = useMemo(() => {
    const seed = new Float32Array(N * 4);
    const colors = new Float32Array(N * 3);
    const pal = ["#D96868", "#91AE6E", "#689D4B", "#F2F2F2", "#1F2421"].map(c => new THREE.Color(c));
    for (let i = 0; i < N; i++) {
      seed[i * 4] = Math.random();                          // phase along path
      seed[i * 4 + 1] = (Math.random() - 0.5) * 2;          // lateral offset
      seed[i * 4 + 2] = i % 2;                               // which stream
      seed[i * 4 + 3] = 0.5 + Math.random();                // speed jitter
      const c = pal[i % 2 === 0 ? (Math.random() < 0.7 ? 0 : 3) : (Math.random() < 0.6 ? 2 : 1)];
      colors.set([c.r, c.g, c.b], i * 3);
    }
    const pos = new Float32Array(N * 3);
    return { seed, colors, pos };
  }, []);

  useFrame((st, dt) => {
    const k = 1 - Math.exp(-dt * 2.2);
    cur.current.flow += (cfg.flow - cur.current.flow) * k;
    cur.current.ring += (cfg.ring - cur.current.ring) * k;
    const t = st.clock.elapsedTime;
    const { seed, pos } = data;
    const f = reduced ? 0.15 : cur.current.flow;
    const ring = cur.current.ring;
    for (let i = 0; i < N; i++) {
      const s = seed[i * 4 + 2] ? 1 : -1;
      let u = (seed[i * 4] + t * 0.07 * f * seed[i * 4 + 3]) % 1;
      const lat = seed[i * 4 + 1];
      // path: from far side (x = s*4.2) spiralling into the core
      const r = 4.2 * (1 - u) + 0.95;
      const ang = u * Math.PI * 2.2 + (s > 0 ? 0 : Math.PI) + lat * 0.25;
      let x = s * (r * Math.cos(u * 1.2)) * 0.95;
      let y = Math.sin(ang) * (0.3 + (1 - u) * 1.1) + lat * 0.18 * (1 - u) + Math.sin(t * 0.6 + i) * 0.03;
      let z = Math.cos(ang) * (0.3 + (1 - u) * 0.9) + lat * 0.25;
      // hold: collapse onto a still ring
      if (ring > 0.001) {
        const a = (i / N) * Math.PI * 2;
        const rx = Math.cos(a) * 2.1, ry = Math.sin(a) * 2.1 * 0.62, rz = Math.sin(a * 3) * 0.1;
        x += (rx - x) * ring; y += (ry - y) * ring; z += (rz - z) * ring;
      }
      pos[i * 3] = x; pos[i * 3 + 1] = y; pos[i * 3 + 2] = z;
      u = 0;
    }
    const g = pts.current.geometry;
    g.attributes.position.needsUpdate = true;
  });

  return (
    <points ref={pts} frustumCulled={false}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[data.pos, 3]} />
        <bufferAttribute attach="attributes-color" args={[data.colors, 3]} />
      </bufferGeometry>
      <pointsMaterial size={0.055} vertexColors sizeAttenuation transparent opacity={0.9} depthWrite={false} />
    </points>
  );
}

function Core({ state, reduced }) {
  const cfg = STATE[state] || STATE.idle;
  const main = useRef(), a = useRef(), b = useRef(), mat = useRef(), group = useRef();
  const cur = useRef({ split: 0, color: new THREE.Color(cfg.core), distort: cfg.distort, speed: cfg.speed });
  useFrame((st, dt) => {
    const c = cur.current;
    const k = 1 - Math.exp(-dt * 3);
    c.split += (cfg.split - c.split) * k;
    c.distort += (cfg.distort - c.distort) * k;
    c.speed += (cfg.speed - c.speed) * k;
    c.color.lerp(tmpC.set(cfg.core), k);
    if (mat.current) {
      mat.current.color.copy(c.color);
      mat.current.distort = reduced ? 0.12 : c.distort;
      mat.current.speed = reduced ? 0 : c.speed * 2;
    }
    const t = st.clock.elapsedTime;
    const s = 1 - c.split * 0.55;
    main.current.scale.setScalar(s);
    const orbit = t * 1.3;
    const d = c.split * 1.15;
    for (const [m, ph] of [[a, 0], [b, Math.PI]]) {
      m.current.position.set(Math.cos(orbit + ph) * d, Math.sin(orbit * 0.7 + ph) * d * 0.35, Math.sin(orbit + ph) * d * 0.6);
      m.current.scale.setScalar(Math.max(0.001, c.split * 0.48));
      m.current.material.color.copy(c.color);
      m.current.material.opacity = c.split;
    }
    if (group.current && !reduced) group.current.rotation.y += dt * 0.15 * c.speed;
  });
  return (
    <group ref={group}>
      <mesh ref={main}>
        <icosahedronGeometry args={[1, 24]} />
        <MeshDistortMaterial ref={mat} color={cfg.core} roughness={0.28} metalness={0.05} distort={cfg.distort} speed={1.5} />
      </mesh>
      <mesh ref={a}><sphereGeometry args={[1, 40, 40]} /><meshStandardMaterial transparent roughness={0.35} /></mesh>
      <mesh ref={b}><sphereGeometry args={[1, 40, 40]} /><meshStandardMaterial transparent roughness={0.35} wireframe /></mesh>
    </group>
  );
}

function Rig({ reduced }) {
  const { camera, pointer } = useThree();
  useFrame((_, dt) => {
    if (reduced) return;
    const k = 1 - Math.exp(-dt * 2);
    camera.position.x += (pointer.x * 0.9 - camera.position.x) * k;
    camera.position.y += (pointer.y * 0.5 + 0.2 - camera.position.y) * k;
    camera.lookAt(0, 0, 0);
  });
  return null;
}

export function ThreeScene({ state = "idle", className = "", label }) {
  const reduced = usePrefersReducedMotion();
  const cfg = STATE[state] || STATE.idle;
  return (
    <div className={className || "relative h-full w-full"} role="img" aria-label={label || `Animated signal field showing the ${state} state`}>
      <Canvas
        dpr={[1, 1.75]}
        camera={{ position: [0, 0.2, 6.4], fov: 42 }}
        gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
        frameloop={reduced ? "demand" : "always"}
      >
        <ambientLight intensity={0.75} />
        <directionalLight position={[3, 4, 5]} intensity={2.2} color="#fff4ea" />
        <directionalLight position={[-4, -2, -3]} intensity={1.1} color="#91AE6E" />
        <pointLight position={[0, 0, 3]} intensity={6} color="#D96868" distance={7} />
        <Suspense fallback={null}>
          <Float speed={reduced ? 0 : 1.4} rotationIntensity={0.25} floatIntensity={0.6}>
            <Core state={state} reduced={reduced} />
          </Float>
          <Streams state={state} reduced={reduced} />
          {cfg.sparkle > 0 && <Sparkles count={60} scale={[4, 3, 3]} size={4} speed={reduced ? 0 : 0.6} color="#F2F2F2" />}
        </Suspense>
        <Rig reduced={reduced} />
      </Canvas>
    </div>
  );
}
