// SETU 3D avatar: a stylised cartoon signer built entirely from code (no model files).
// Curly black hair, big smile, black hoodie with a white collar, light jeans.
// Driven by rig.js: call avatar.update({Rq, Lq, face}, timeSeconds) every frame.

import * as THREE from "../lib/three-bundle.min.js";
import { BODY, HAND, HandRig, FINGERS, solveFrame, REST, neutralFace } from "./rig.js";

const V = (x, y, z) => new THREE.Vector3(x, y, z);
const UP = V(0, 1, 0);

export const PALETTE = {
  skin: { light: "#fcdcc4", warm: "#f9c8a2", tan: "#d69b72", brown: "#a86f4c", deep: "#6f4630" },
  hair: { black: "#141418", brown: "#4a2e1c", blonde: "#c9a15a", red: "#8a3a1e", grey: "#8b8d92" },
  hoodie: { black: "#15161a", navy: "#1e2a4a", maroon: "#5a1d2a", teal: "#1d5b60", white: "#e9e9ea" },
  jeans: { light: "#a9c6e4", mid: "#6f93bd", dark: "#2f4466", black: "#2a2b30" },
};

function mat(color, opts = {}) {
  return new THREE.MeshPhysicalMaterial({ color, roughness: 0.6, metalness: 0, ...opts });
}

// simple seeded RNG so the hairstyle is the same every time
function rng(seed) {
  let s = seed >>> 0;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
}

// head silhouette (radius by height), used for the head mesh and to stick features onto its surface
const HEAD_PROFILE = [[0.0, -0.128], [0.03, -0.124], [0.062, -0.108], [0.088, -0.082], [0.104, -0.048],
                      [0.112, -0.01], [0.116, 0.025], [0.114, 0.06], [0.104, 0.088], [0.084, 0.11],
                      [0.055, 0.125], [0.02, 0.132], [0.0, 0.133]];
const HEAD_Z = 0.93;
export const HEAD_SCALE = 1.3;
function headRadiusAt(y) {
  for (let i = 1; i < HEAD_PROFILE.length; i++) {
    const [r0, y0] = HEAD_PROFILE[i - 1], [r1, y1] = HEAD_PROFILE[i];
    if (y <= y1) return r0 + (r1 - r0) * (y - y0) / (y1 - y0 || 1);
  }
  return 0;
}
function faceZ(x, y) {
  const r = headRadiusAt(y);
  return HEAD_Z * Math.sqrt(Math.max(r * r - x * x, 0));
}

function segment(mesh, a, b) {
  // place a unit-height Y-aligned mesh between points a and b
  const d = b.clone().sub(a);
  const len = d.length();
  mesh.position.copy(a).addScaledVector(d, 0.5);
  mesh.quaternion.setFromUnitVectors(UP, d.divideScalar(len || 1));
  mesh.scale.set(1, len, 1);
}

export function createAvatar({ colors = {} } = {}) {
  const C = {
    skin: colors.skin || PALETTE.skin.warm, hair: colors.hair || PALETTE.hair.black,
    hoodie: colors.hoodie || PALETTE.hoodie.black, jeans: colors.jeans || PALETTE.jeans.light,
  };
  const M = {
    skin: mat(C.skin, { roughness: 0.55, sheen: 0.4, sheenColor: new THREE.Color("#ffb8a0"), sheenRoughness: 0.6 }),
    skinDark: mat(C.skin, { roughness: 0.6 }),
    hair: mat(C.hair, { roughness: 0.42, clearcoat: 0.3, clearcoatRoughness: 0.5 }),
    hoodie: mat(C.hoodie, { roughness: 0.92, sheen: 1, sheenColor: new THREE.Color("#5b5f6b"), sheenRoughness: 0.8 }),
    rib: mat(C.hoodie, { roughness: 1 }),
    collar: mat("#f5f5f3", { roughness: 0.8 }),
    jeans: mat(C.jeans, { roughness: 0.95, sheen: 0.5, sheenColor: new THREE.Color("#ffffff") }),
    shoe: mat("#f4f4f4", { roughness: 0.7 }),
    sole: mat("#b9bcc2", { roughness: 0.9 }),
    dark: mat("#1e1510", { roughness: 0.5 }),
    eyeWhite: mat("#ffffff", { roughness: 0.2 }),
    iris: mat("#2a1a12", { roughness: 0.2, clearcoat: 1 }),
    mouth: mat("#5a1519", { roughness: 0.8, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -2 }),
    teeth: mat("#ffffff", { roughness: 0.3, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -3 }),
    tongue: mat("#d9646e", { roughness: 0.6, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -3 }),
    blush: new THREE.MeshBasicMaterial({ color: "#ff8f8f", transparent: true, opacity: 0.18, depthWrite: false }),
    nail: mat("#f8e2d6", { roughness: 0.3 }),
    joint: new THREE.MeshBasicMaterial({ color: "#ff3df2", depthTest: false }),
  };

  const root = new THREE.Group();
  root.name = "setu-avatar";
  const body = new THREE.Group();          // sways / breathes
  root.add(body);

  // ------------------------------------------------------------ legs + shoes (short cartoon legs)
  for (const sx of [-1, 1]) {
    const hip = V(sx * 0.082, 0.93, 0), knee = V(sx * 0.088, 0.62, 0.012), ankle = V(sx * 0.09, 0.33, 0);
    const thigh = new THREE.Mesh(new THREE.CylinderGeometry(0.074, 0.084, 1, 24), M.jeans);
    segment(thigh, knee, hip); body.add(thigh);
    const shin = new THREE.Mesh(new THREE.CylinderGeometry(0.066, 0.074, 1, 24), M.jeans);
    segment(shin, ankle, knee); body.add(shin);
    const kneeBall = new THREE.Mesh(new THREE.SphereGeometry(0.077, 20, 16), M.jeans);
    kneeBall.position.copy(knee); body.add(kneeBall);
    const hem = new THREE.Mesh(new THREE.TorusGeometry(0.066, 0.008, 8, 24), M.jeans);
    hem.rotation.x = Math.PI / 2; hem.position.copy(ankle); body.add(hem);
    const shoe = new THREE.Mesh(new THREE.CapsuleGeometry(0.056, 0.13, 8, 16), M.shoe);
    shoe.rotation.x = Math.PI / 2; shoe.position.set(sx * 0.09, 0.295, 0.045); shoe.scale.set(1.05, 1, 0.72);
    body.add(shoe);
    const sole = new THREE.Mesh(new THREE.BoxGeometry(0.11, 0.022, 0.26), M.sole);
    sole.position.set(sx * 0.09, 0.255, 0.045); body.add(sole);
  }
  const hips = new THREE.Mesh(new THREE.CylinderGeometry(0.158, 0.15, 0.12, 32), M.jeans);
  hips.scale.set(1, 1, 0.62); hips.position.y = 0.9;
  body.add(hips);

  // ------------------------------------------------------------ torso (hoodie)
  const torsoPts = [[0.0, 0.9], [0.168, 0.9], [0.172, 0.93], [0.166, 1.0], [0.16, 1.1], [0.163, 1.2],
                    [0.176, 1.3], [0.19, 1.36], [0.186, 1.4], [0.15, 1.43], [0.08, 1.45], [0.0, 1.455]]
    .map(([r, y]) => new THREE.Vector2(r, y));
  const torso = new THREE.Mesh(new THREE.LatheGeometry(torsoPts, 48), M.hoodie);
  torso.scale.set(1, 1, 0.63);
  body.add(torso);
  const hem = new THREE.Mesh(new THREE.TorusGeometry(0.168, 0.012, 10, 48), M.rib);
  hem.rotation.x = Math.PI / 2; hem.scale.set(1, 0.63, 1); hem.position.y = 0.915; body.add(hem);
  // kangaroo pocket (a slightly raised panel)
  const pocketShape = new THREE.Shape();
  pocketShape.moveTo(-0.09, 0); pocketShape.lineTo(0.09, 0); pocketShape.lineTo(0.07, 0.1);
  pocketShape.lineTo(-0.07, 0.1); pocketShape.closePath();
  const pocket = new THREE.Mesh(new THREE.ExtrudeGeometry(pocketShape, { depth: 0.004, bevelEnabled: true, bevelSize: 0.003, bevelThickness: 0.002, bevelSegments: 2 }), M.hoodie);
  pocket.position.set(0, 0.975, 0.098); pocket.rotation.x = -0.04; body.add(pocket);
  // hood bunched behind the neck + white collar in front
  const hood = new THREE.Mesh(new THREE.TorusGeometry(0.08, 0.022, 14, 40), M.hoodie);
  hood.position.set(0, 1.45, -0.03); hood.rotation.x = Math.PI / 2 - 0.45; hood.scale.set(1.05, 0.8, 1); body.add(hood);
  const hoodBack = new THREE.Mesh(new THREE.SphereGeometry(0.1, 24, 16), M.hoodie);
  hoodBack.position.set(0, 1.42, -0.085); hoodBack.scale.set(1.0, 0.42, 0.4); body.add(hoodBack);
  const collar = new THREE.Mesh(new THREE.TorusGeometry(0.05, 0.01, 12, 32), M.collar);
  collar.position.set(0, 1.468, 0.004); collar.rotation.x = Math.PI / 2 - 0.2; body.add(collar);
  for (const sx of [-1, 1]) {                        // shirt collar points peeking out in front
    const flap = new THREE.Shape();
    flap.moveTo(0, 0); flap.lineTo(sx * 0.045, 0.012); flap.lineTo(sx * 0.012, -0.04); flap.closePath();
    const m = new THREE.Mesh(new THREE.ShapeGeometry(flap), new THREE.MeshPhysicalMaterial({ color: "#f5f5f3", roughness: 0.8, side: THREE.DoubleSide }));
    m.position.set(0, 1.462, 0.052); m.rotation.x = -0.35; body.add(m);
  }

  // shoulders
  for (const side of ["R", "L"]) {
    const sh = new THREE.Mesh(new THREE.SphereGeometry(0.058, 24, 18), M.hoodie);
    sh.position.set((side === "R" ? -1 : 1) * (BODY.shoulderHalf - 0.008), BODY.shoulderY - 0.012, 0);
    sh.scale.set(1, 0.9, 0.95);
    body.add(sh);
  }

  // ------------------------------------------------------------ neck + head
  const neck = new THREE.Mesh(new THREE.CylinderGeometry(0.043, 0.048, 0.13, 20), M.skin);
  neck.position.set(0, 1.49, -0.008); body.add(neck);

  const head = new THREE.Group();
  head.position.set(0, BODY.headY, 0);      // rotation pivot ~ centre of head
  head.scale.setScalar(HEAD_SCALE);          // big cartoon head
  body.add(head);
  const headPts = HEAD_PROFILE.map(([r, y]) => new THREE.Vector2(r, y));
  const skull = new THREE.Mesh(new THREE.LatheGeometry(headPts, 64), M.skin);
  skull.scale.set(1, 1, HEAD_Z);
  head.add(skull);
  for (const sx of [-1, 1]) {
    const ear = new THREE.Mesh(new THREE.SphereGeometry(0.03, 16, 12), M.skin);
    ear.position.set(sx * 0.112, -0.005, -0.005); ear.scale.set(0.45, 1, 0.75); head.add(ear);
    const blush = new THREE.Mesh(new THREE.CircleGeometry(0.018, 20), M.blush);
    blush.position.set(sx * 0.066, -0.028, faceZ(0.066, -0.028) + 0.002);
    blush.rotation.y = sx * 0.55; head.add(blush);
  }
  const nose = new THREE.Mesh(new THREE.SphereGeometry(0.013, 16, 12), M.skinDark);
  nose.position.set(0, -0.018, faceZ(0, -0.018) + 0.002); nose.scale.set(1.1, 0.85, 0.8); head.add(nose);

  // eyes: happy (closed arcs) and open (with blink)
  const eyes = { happy: new THREE.Group(), open: new THREE.Group(), lids: [] };
  for (const sx of [-1, 1]) {
    const ex = sx * 0.04, ey = 0.012, ez = faceZ(ex, ey);
    const arc = new THREE.Mesh(new THREE.TorusGeometry(0.015, 0.0038, 8, 20, Math.PI), M.dark);
    arc.position.set(ex, ey - 0.006, ez + 0.002); arc.rotation.y = sx * 0.35; eyes.happy.add(arc);
    const eg = new THREE.Group();
    eg.position.set(ex, ey, ez - 0.004); eg.rotation.y = sx * 0.33;
    const white = new THREE.Mesh(new THREE.SphereGeometry(0.017, 20, 16), M.eyeWhite);
    white.scale.set(1, 1.15, 0.55); eg.add(white);
    const iris = new THREE.Mesh(new THREE.SphereGeometry(0.0105, 16, 12), M.iris);
    iris.position.set(0, -0.001, 0.0065); iris.scale.set(1, 1.1, 0.5); eg.add(iris);
    const glint = new THREE.Mesh(new THREE.SphereGeometry(0.0028, 8, 6), M.eyeWhite);
    glint.position.set(0.004, 0.004, 0.012); eg.add(glint);
    eyes.open.add(eg); eyes.lids.push(eg);
  }
  head.add(eyes.happy, eyes.open);
  eyes.open.visible = false;

  const brows = [];
  for (const sx of [-1, 1]) {
    const pivot = new THREE.Group();         // faces outward along the head curve
    const bx = sx * 0.042, by = 0.047;
    pivot.position.set(bx, by, faceZ(bx, by) + 0.004);
    pivot.rotation.y = sx * 0.34;
    const tilt = new THREE.Group();           // in-plane tilt (furrow / arch)
    pivot.add(tilt);
    const b = new THREE.Mesh(new THREE.CapsuleGeometry(0.0058, 0.03, 4, 10), M.dark);
    b.rotation.z = Math.PI / 2;
    tilt.add(b);
    pivot.userData = { sx, bx, by, tilt };
    head.add(pivot); brows.push(pivot);
  }

  // mouth: a wide open smile (dark inside, teeth on top, tongue below)
  const mouth = new THREE.Group();
  const my = -0.056;
  mouth.position.set(0, my, faceZ(0, my) - 0.002);
  mouth.rotation.x = -0.32;
  const smile = new THREE.Shape();
  smile.moveTo(-0.034, 0.004);
  smile.quadraticCurveTo(0, -0.004, 0.034, 0.004);
  smile.bezierCurveTo(0.03, -0.03, -0.03, -0.03, -0.034, 0.004);
  const mouthIn = new THREE.Mesh(new THREE.ShapeGeometry(smile, 24), M.mouth);
  const teethShape = new THREE.Shape();
  teethShape.moveTo(-0.029, 0.0015);
  teethShape.quadraticCurveTo(0, -0.0055, 0.029, 0.0015);
  teethShape.lineTo(0.026, -0.006);
  teethShape.quadraticCurveTo(0, -0.012, -0.026, -0.006);
  teethShape.closePath();
  const teeth = new THREE.Mesh(new THREE.ShapeGeometry(teethShape, 16), M.teeth);
  teeth.position.z = 0.0005;
  const tongue = new THREE.Mesh(new THREE.CircleGeometry(0.014, 20), M.tongue);
  tongue.scale.set(1.3, 0.6, 1); tongue.position.set(0, -0.019, 0.0005);
  mouth.add(mouthIn, teeth, tongue);
  head.add(mouth);

  // hair: hundreds of curls on the upper head + a curly fringe
  const rand = rng(7);
  const curlGeo = new THREE.IcosahedronGeometry(1, 1);
  const curls = [];
  const addCurl = (x, y, z, s) => curls.push([x, y, z, s]);
  for (let i = 0; i < 900 && curls.length < 330; i++) {
    const th = rand() * Math.PI * 2;                 // around the vertical axis, 0 = facing +z
    const yy = -0.07 + rand() * 0.2;
    const front = Math.cos(th);                      // 1 at the face
    const hairline = 0.068 + 0.02 * (1 - front);     // higher on the forehead
    if (front > 0.35 && yy < hairline) continue;      // keep the face clear
    if (Math.abs(Math.sin(th)) > 0.8 && yy < 0.015 && front > -0.3) continue;   // ears
    if (yy < -0.04 && front > -0.5) continue;
    const r = headRadiusAt(Math.min(yy, 0.13)) + 0.006;
    addCurl(Math.sin(th) * r, yy, Math.cos(th) * r * HEAD_Z, 0.018 + rand() * 0.014);
  }
  for (let i = 0; i < 26; i++) {                       // fringe falling onto the forehead
    const x = -0.085 + (i / 25) * 0.17 + (rand() - 0.5) * 0.01;
    const y = 0.07 + rand() * 0.02 - Math.abs(x) * 0.12;
    addCurl(x, y, faceZ(x, y) + 0.004, 0.014 + rand() * 0.008);
  }
  for (let i = 0; i < 40; i++) {                        // top volume
    const th = rand() * Math.PI * 2, rr = rand() * 0.07;
    addCurl(Math.sin(th) * rr, 0.13 + rand() * 0.02, Math.cos(th) * rr * HEAD_Z - 0.01, 0.024 + rand() * 0.012);
  }
  const hair = new THREE.InstancedMesh(curlGeo, M.hair, curls.length);
  const tmp = new THREE.Object3D();
  curls.forEach(([x, y, z, s], i) => {
    tmp.position.set(x, y, z);
    tmp.rotation.set(rand() * 3, rand() * 3, rand() * 3);
    tmp.scale.set(s, s * (0.8 + rand() * 0.3), s);
    tmp.updateMatrix();
    hair.setMatrixAt(i, tmp.matrix);
  });
  const hairCap = new THREE.Mesh(new THREE.SphereGeometry(0.118, 32, 16, 0, Math.PI * 2, 0, Math.PI * 0.45), M.hair);
  hairCap.position.y = 0.012; hairCap.scale.set(1, 1.05, HEAD_Z * 0.98); hairCap.rotation.x = -0.35;
  head.add(hair, hairCap);

  // ------------------------------------------------------------ arms + hands
  const arms = {};
  for (const side of ["R", "L"]) {
    const upper = new THREE.Mesh(new THREE.CylinderGeometry(0.047, 0.054, 1, 20), M.hoodie);
    const fore = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.047, 1, 20), M.hoodie);
    const elbow = new THREE.Mesh(new THREE.SphereGeometry(0.048, 20, 14), M.hoodie);
    const cuff = new THREE.Mesh(new THREE.CylinderGeometry(0.039, 0.041, 1, 20), M.rib);
    const wrist = new THREE.Mesh(new THREE.CylinderGeometry(0.025, 0.028, 1, 14), M.skin);
    body.add(upper, fore, elbow, cuff, wrist);

    const rig = new HandRig(side);
    body.add(rig.root);
    const sx = side === "R" ? 1 : -1;
    const palm = new THREE.Mesh(new THREE.CapsuleGeometry(1, 1, 6, 16), M.skin);
    palm.scale.set(HAND.palmW / 2, HAND.palmH / 3, HAND.palmD / 2);
    palm.position.set(0, 0.05, 0);
    rig.root.add(palm);
    const heel = new THREE.Mesh(new THREE.SphereGeometry(0.022, 16, 12), M.skin);
    heel.position.set(sx * 0.022, 0.03, 0.006); heel.scale.set(1, 1.2, 0.8);
    rig.root.add(heel);
    for (const f of FINGERS) {
      const ch = rig.chains[f];
      const r0 = f === "thumb" ? 0.0128 : f === "pinky" ? 0.0098 : 0.0112;
      const knuckle = new THREE.Mesh(new THREE.SphereGeometry(r0 * 1.05, 12, 10), M.skin);
      ch.base.add(knuckle);
      ch.segs.forEach((s, i) => {
        const r = r0 * (1 - i * 0.1);
        const cyl = new THREE.Mesh(new THREE.CylinderGeometry(r * 0.94, r, s.L, 12), M.skin);
        cyl.position.y = s.L / 2;
        s.seg.add(cyl);
        const ball = new THREE.Mesh(new THREE.SphereGeometry(r * 0.95, 12, 10), M.skin);
        s.tip.add(ball);
        if (i === 2) {
          const nail = new THREE.Mesh(new THREE.SphereGeometry(r * 0.7, 10, 8), M.nail);
          nail.position.set(0, -0.003, -r * 0.55); nail.scale.set(1, 1.3, 0.35);
          s.tip.add(nail);
        }
      });
    }
    arms[side] = { upper, fore, elbow, cuff, wrist, rig };
  }

  // debug skeleton: MediaPipe-style joint dots on both hands
  const dots = [];
  const dotGeo = new THREE.SphereGeometry(0.006, 8, 6);
  for (const side of ["R", "L"]) {
    arms[side].rig.joints.forEach(j => {
      const d = new THREE.Mesh(dotGeo, M.joint);
      d.renderOrder = 10; d.visible = false;
      j.add(d); dots.push(d);
    });
  }
  const setSkeleton = on => dots.forEach(d => { d.visible = on; });

  // ------------------------------------------------------------ animation state
  const state = { expression: "auto", blinkT: 0, nextBlink: 2.5, signing: false, smile: 1, faceSm: neutralFace(), headRot: new THREE.Euler() };

  function placeArm(side, s) {
    const a = arms[side];
    const fwd = s.W.clone().sub(s.E).normalize();
    const cuffEnd = s.W.clone().addScaledVector(fwd, -0.018);
    const cuffStart = s.W.clone().addScaledVector(fwd, -0.05);
    segment(a.upper, s.S, s.E);
    segment(a.fore, s.E, cuffStart);
    segment(a.cuff, cuffStart, cuffEnd);
    segment(a.wrist, cuffEnd, s.W.clone().addScaledVector(fwd, 0.012));
    a.elbow.position.copy(s.E);
    a.rig.root.position.copy(s.W);
    a.rig.root.quaternion.copy(s.quat);
    a.rig.setShape(s.curls, s.spread);
  }

  function update(frame, t, dt = 1 / 60) {
    const f = { Rq: frame?.Rq || REST.R, Lq: frame?.Lq || REST.L, face: frame?.face || neutralFace() };
    const solved = solveFrame(f);
    placeArm("R", solved.R);
    placeArm("L", solved.L);

    // body life: breathing and a slow sway (arms are children of `body`, so they follow)
    body.position.y = Math.sin(t * 1.6) * 0.002;
    body.rotation.y = Math.sin(t * 0.45) * 0.02;
    torso.scale.set(1 + Math.sin(t * 1.6) * 0.006, 1, 0.63 * (1 + Math.sin(t * 1.6) * 0.01));

    // face (smoothed so expressions ease in)
    const fz = f.face;
    const k = 1 - Math.exp(-dt * 12);
    const sm = state.faceSm;
    sm.hx += ((fz.hx || 0) - sm.hx) * k;
    sm.hy += ((fz.hy || 0) - sm.hy) * k;
    const tilt = fz.head === "tilt_fwd" ? 0.13 : 0;
    const idleLook = Math.sin(t * 0.7) * 0.03;
    head.rotation.set(tilt + sm.hy * 0.05 + Math.sin(t * 0.9) * 0.012, sm.hx * 0.06 + idleLook, Math.sin(t * 0.5) * 0.02);

    const browTarget = fz.brow === "raised" ? 1 : fz.brow === "furrowed" ? -1 : 0;
    state.brow = (state.brow ?? 0) + (browTarget - (state.brow ?? 0)) * k;
    for (const b of brows) {
      const { sx, bx, by, tilt } = b.userData;
      const up = state.brow > 0 ? state.brow * 0.012 : state.brow * 0.005;
      b.position.set(bx, by + up, faceZ(bx, by + up) + 0.004);
      // furrowed: inner ends down; raised: gentle arch with inner ends up
      tilt.rotation.z = -sx * (state.brow < 0 ? state.brow * 0.38 : -state.brow * 0.15);
    }

    const mouthOpen = fz.mouth === "open" ? 1 : fz.mouth === "puffed" ? -0.4 : 0;
    state.mouth = (state.mouth ?? 0) + (mouthOpen - (state.mouth ?? 0)) * k;
    const smileAmt = fz.smile != null ? 0.4 + fz.smile * 0.8 : 1;
    mouth.scale.set(0.85 + 0.15 * smileAmt, (0.75 + 0.35 * smileAmt) * (1 + state.mouth * 0.45), 1);

    // eyes: "happy" closed smile eyes when idle (like the reference), open eyes while signing
    let useOpen = state.expression === "attentive" || (state.expression === "auto" && state.signing);
    if (fz.blink != null) useOpen = true;
    eyes.happy.visible = !useOpen;
    eyes.open.visible = useOpen;
    if (useOpen) {
      state.blinkT += dt;
      let lid = 1;
      if (fz.blink != null) lid = 1 - Math.min(1, fz.blink * 1.3);
      else if (state.blinkT > state.nextBlink) {
        const p = (state.blinkT - state.nextBlink) / 0.16;
        lid = p < 1 ? Math.abs(1 - 2 * p) : 1;
        if (p >= 1) { state.blinkT = 0; state.nextBlink = 2 + Math.random() * 3; }
      }
      if (fz.brow === "raised") lid = Math.min(1.15, lid * 1.12);
      eyes.lids.forEach(e => e.scale.set(1, Math.max(0.08, lid), 1));
    }
    return solved;
  }

  function setColors(c) {
    if (c.skin) { M.skin.color.set(c.skin); M.skinDark.color.set(c.skin).multiplyScalar(0.93); }
    if (c.hair) M.hair.color.set(c.hair);
    if (c.hoodie) { M.hoodie.color.set(c.hoodie); M.rib.color.set(c.hoodie).multiplyScalar(0.85); }
    if (c.jeans) M.jeans.color.set(c.jeans);
  }
  setColors(C);

  update(null, 0);
  return {
    group: root, head, arms, update, setColors, setSkeleton,
    setExpression: e => { state.expression = e; },
    setSigning: on => { state.signing = on; },
    hands: { R: arms.R.rig, L: arms.L.rig },
    pickables: [torso, skull, hair],
  };
}

// ------------------------------------------------------------------ stage helpers
export function makeBackground(kind) {
  if (kind === "transparent") return null;
  const cv = document.createElement("canvas");
  cv.width = 16; cv.height = 256;
  const g = cv.getContext("2d");
  const grad = g.createLinearGradient(0, 0, 0, 256);
  const stops = {
    green: ["#7fe35a", "#43c22e", "#2a9a22"],
    studio: ["#f3f1ec", "#dcd8cf", "#bdb8ad"],
    night: ["#2b3547", "#1b2230", "#0f141c"],
    sky: ["#bfe3ff", "#8cc7f2", "#5ea5da"],
  }[kind] || ["#7fe35a", "#43c22e", "#2a9a22"];
  grad.addColorStop(0, stops[0]); grad.addColorStop(0.55, stops[1]); grad.addColorStop(1, stops[2]);
  g.fillStyle = grad; g.fillRect(0, 0, 16, 256);
  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

export function addLights(scene) {
  const hemi = new THREE.HemisphereLight("#ffffff", "#5c7a52", 1.1);
  const key = new THREE.DirectionalLight("#fff0e0", 2.6);
  key.position.set(1.2, 2.6, 2.4);
  const fill = new THREE.DirectionalLight("#dfe9ff", 0.9);
  fill.position.set(-2, 1.6, 1.5);
  const rim = new THREE.DirectionalLight("#ffffff", 1.6);
  rim.position.set(0, 2.2, -2.5);
  scene.add(hemi, key, fill, rim);
  return { hemi, key, fill, rim };
}
