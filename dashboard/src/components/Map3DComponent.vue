<script setup>
/**
 * Map3DComponent.vue
 *
 * Optimisation strategy:
 *  - ONE geometry + ONE material per cell type, shared across every instance.
 *    No unique objects per tile — just Mesh(sharedGeo, sharedMat) + position.
 *  - MeshLambertMaterial everywhere except the rover (no PBR cost on static map).
 *  - Shadows disabled entirely.
 *  - Pixel ratio capped at 1.
 *  - Dirty-flag render loop: rAF only runs while something is actually changing
 *    (rover lerping, wheel spinning, orbit inertia, status/drill toggle).
 *    The GPU renders nothing when the scene is at rest.
 *  - Only the rover has animations. Map cells and path dots are fully static.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  AmbientLight,
  BoxGeometry,
  CatmullRomCurve3,
  Color,
  ConeGeometry,
  CylinderGeometry,
  DirectionalLight,
  Group,
  Mesh,
  MeshLambertMaterial,
  MeshStandardMaterial,
  OctahedronGeometry,
  PerspectiveCamera,
  PlaneGeometry,
  Scene,
  SphereGeometry,
  TubeGeometry,
  Vector3,
  WebGLRenderer,
} from "three";

// ─── Props ────────────────────────────────────────────────────────────────────
const props = defineProps({
  mapMatrix:     { type: Array,  required: true },
  roverPosition: { type: Object, required: true },
  pathPlan:      { type: Array,  default: () => [] },
  minedCells:    { type: Array,  default: () => [] },
  roverStatus:   { type: String, default: "idle" },
  roverSpeed:    { type: Number, default: 1 },
  timeOfDay:     { type: Number, default: 12 },
  dayHrs:        { type: Number, default: 16 },
  nightHrs:      { type: Number, default: 8 },
});

// ─── Scene constants ──────────────────────────────────────────────────────────
const CELL = 2.2;                     // world units per grid cell
const HALF = CELL / 2;

const C = Object.freeze({
  skyDay:      "#1a0e05",
  skyNight:    "#06040a",
  ground:      "#c47a3a",
  barrier:     "#3a1e0a",
  gold:        "#f0c040",
  ice:         "#a0d0f0",
  green:       "#30d070",
  start:       "#ff6b35",
  path:        "#44d1ff",
  mined:       "#120600",
  rover:       "#dce3e8",
  roverAccent: "#ff6b35",
  solar:       "#1a3a6e",
  wheel:       "#1c1c1c",
  statusColor: {
    mine: "#ffaa00", move: "#44d1ff", charge: "#ffd700",
    standby: "#334455", idle: "#ff6b35",
  },
});

// ─── Derived computeds ────────────────────────────────────────────────────────
const matrix   = computed(() => Array.isArray(props.mapMatrix) ? props.mapMatrix : []);
const rowCount = computed(() => matrix.value.length        || 1);
const colCount = computed(() => matrix.value[0]?.length    || 1);
const cycle    = computed(() => props.dayHrs + props.nightHrs);
const isDay    = computed(() => (props.timeOfDay % cycle.value) < props.dayHrs);
const dayFrac  = computed(() => (props.timeOfDay % cycle.value) / cycle.value);
const isMoving = computed(() => props.roverStatus === "move");
const isMining = computed(() => props.roverStatus === "mine");

// ─── DOM ──────────────────────────────────────────────────────────────────────
const canvasWrap = ref(null);

// ─── Three.js state ───────────────────────────────────────────────────────────
let scene, camera, renderer, frameId, resizeObs;
let cellGroup, pathGroup;
let ambientLight, sunLight;

// ─── Shared static assets ─────────────────────────────────────────────────────
// Allocated once in buildShared(), freed in dispose().
// Every map mesh reuses these — no per-cell allocation.
const S = {
  // Geometries
  gTile:       null,   // flat ground square
  gBarrier:    null,   // rock cube
  gGold:       null,   // octahedron crystal
  gIceCone:    null,   // cone shard
  gGreenStem:  null,
  gGreenCap:   null,
  gPole:       null,
  gFlag:       null,
  gPit:        null,   // mined-out cylinder

  // Materials (Lambert = no specular, cheapest lit shading)
  mTile:       null,
  mBarrier:    null,
  mGold:       null,
  mIce:        null,
  mGreen:      null,
  mGreenDark:  null,
  mStart:      null,
  mPole:       null,
  mMined:      null,
};

// Path is drawn as a TubeGeometry along waypoints.
// The tube mesh is disposed and recreated on each buildPath() call.
let pathTubeMesh = null;
let pathTubeMat  = null;

// Rover heading — smoothly interpolated Y rotation
let roverHeadingTarget  = 0;   // radians, updated when position changes
let roverHeadingCurrent = 0;

function buildShared() {
  S.gTile      = new PlaneGeometry(CELL - 0.1, CELL - 0.1);
  S.gBarrier   = new BoxGeometry(CELL * 0.8, 1.0, CELL * 0.8);
  S.gGold      = new OctahedronGeometry(0.26);
  S.gIceCone   = new ConeGeometry(0.15, 0.65, 5);
  S.gGreenStem = new CylinderGeometry(0.07, 0.10, 0.36, 6);
  S.gGreenCap  = new SphereGeometry(0.28, 6, 5);
  S.gPole      = new CylinderGeometry(0.03, 0.03, 0.88, 5);
  S.gFlag      = new BoxGeometry(0.26, 0.16, 0.02);
  S.gPit       = new CylinderGeometry(CELL * 0.34, CELL * 0.24, 0.22, 7);

  S.mTile      = new MeshLambertMaterial({ color: C.ground });
  S.mBarrier   = new MeshLambertMaterial({ color: C.barrier });
  S.mGold      = new MeshLambertMaterial({ color: C.gold,  emissive: new Color(C.gold),  emissiveIntensity: 0.15 });
  S.mIce       = new MeshLambertMaterial({ color: C.ice,   emissive: new Color(C.ice),   emissiveIntensity: 0.10, transparent: true, opacity: 0.88 });
  S.mGreen     = new MeshLambertMaterial({ color: C.green, emissive: new Color(C.green), emissiveIntensity: 0.18 });
  S.mGreenDark = new MeshLambertMaterial({ color: "#1a7a30" });
  S.mStart     = new MeshLambertMaterial({ color: C.start, emissive: new Color(C.start), emissiveIntensity: 0.20 });
  S.mPole      = new MeshLambertMaterial({ color: "#888888" });
  S.mMined     = new MeshLambertMaterial({ color: C.mined });
}

function disposeShared() {
  for (const v of Object.values(S)) v?.dispose?.();
  pathTubeMat?.dispose();
  pathTubeMesh?.geometry?.dispose();
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function toWorld(cx, cy, y = 0) {
  return new Vector3(
    cx * CELL - colCount.value * HALF + HALF,
    y,
    cy * CELL - rowCount.value * HALF + HALF,
  );
}

/**
 * Remove all children from a Group.
 * Shared geometries/materials are NOT disposed here — disposeShared() handles them.
 * Only rover-unique geometry/material objects are disposed.
 */
function clearGroup(g) {
  if (!g) return;
  while (g.children.length) {
    g.remove(g.children[g.children.length - 1]);
    // No dispose — meshes use shared assets.
    // Rover group is handled separately in cleanup.
  }
}

// ─── Static cell factories ────────────────────────────────────────────────────
// Each function creates the minimum number of Mesh objects.
// All use shared geometry + shared material — O(1) GPU state changes per type.

function makeTile(gx, gy) {
  const m = new Mesh(S.gTile, S.mTile);
  m.rotation.x = -Math.PI / 2;
  m.position.copy(toWorld(gx, gy, 0));
  return m;
}

function makeBarrier(gx, gy) {
  const m = new Mesh(S.gBarrier, S.mBarrier);
  m.position.copy(toWorld(gx, gy, 0.5));
  return m;
}

function makeGold(gx, gy) {
  // Two crystals, different rotations — same shared geo+mat
  const g  = new Group();
  const c1 = new Mesh(S.gGold, S.mGold);
  c1.position.set(-0.2, 0.34, -0.14);
  c1.rotation.set(0.4, 0.7, 0);
  c1.scale.y = 1.5;
  const c2 = new Mesh(S.gGold, S.mGold);
  c2.position.set(0.18, 0.27, 0.16);
  c2.rotation.set(-0.3, 1.2, 0.2);
  c2.scale.y = 1.2;
  g.add(c1, c2);
  g.position.copy(toWorld(gx, gy, 0));
  return g;
}

function makeIce(gx, gy) {
  const g  = new Group();
  const s1 = new Mesh(S.gIceCone, S.mIce);
  s1.position.set(-0.18, 0.33, 0.10);
  s1.rotation.z = -0.2;
  const s2 = new Mesh(S.gIceCone, S.mIce);
  s2.position.set(0.18, 0.27, -0.14);
  s2.rotation.z = 0.25;
  g.add(s1, s2);
  g.position.copy(toWorld(gx, gy, 0));
  return g;
}

function makeGreen(gx, gy) {
  const g    = new Group();
  const stem = new Mesh(S.gGreenStem, S.mGreenDark);
  stem.position.y = 0.18;
  const cap  = new Mesh(S.gGreenCap, S.mGreen);
  cap.position.y = 0.50;
  cap.scale.y    = 0.60;
  g.add(stem, cap);
  g.position.copy(toWorld(gx, gy, 0));
  return g;
}

function makeStart(gx, gy) {
  const g    = new Group();
  const pole = new Mesh(S.gPole, S.mPole);
  pole.position.y = 0.44;
  const flag = new Mesh(S.gFlag, S.mStart);
  flag.position.set(0.13, 0.86, 0);
  g.add(pole, flag);
  g.position.copy(toWorld(gx, gy, 0));
  return g;
}

function makeMinedPit(gx, gy) {
  const m = new Mesh(S.gPit, S.mMined);
  m.position.copy(toWorld(gx, gy, -0.09));
  return m;
}

// ─── Rover factory ────────────────────────────────────────────────────────────
// Rover uses MeshStandardMaterial because it's the visual focus of the scene.
// All rover geometries are unique (only one rover) so no sharing needed.
const rover = {
  root:        null,
  wheels:      [],   // Group[] — rotation.x incremented when moving
  statusLight: null, // Mesh   — emissive colour updated on status change
  solarPanel:  null, // Mesh   — tilt set once per timeOfDay change
  drillGroup:  null, // Group  — visible only when mining
};

function buildRover() {
  rover.wheels = []; rover.statusLight = null; rover.solarPanel = null; rover.drillGroup = null;

  const root = new Group();
  const sm   = (col, o = {}) => new MeshStandardMaterial({ color: col, roughness: 0.55, metalness: 0.2, ...o });

  // Body
  const chassis = new Mesh(new BoxGeometry(1.0, 0.18, 1.3), sm(C.rover, { roughness: 0.5 }));
  chassis.position.y = 0.42;
  root.add(chassis);

  const body = new Mesh(new BoxGeometry(0.80, 0.30, 0.86), sm(C.rover));
  body.position.y = 0.64;
  root.add(body);

  // Solar panel
  const panel = new Mesh(
    new BoxGeometry(1.42, 0.04, 0.68),
    new MeshStandardMaterial({ color: C.solar, roughness: 0.3, metalness: 0.7,
      emissive: new Color("#001a55"), emissiveIntensity: 0.3 }),
  );
  panel.position.y = 0.83;
  rover.solarPanel  = panel;
  root.add(panel);

  // Wheels — shared geometry per rover (6 wheels, 2 meshes each)
  const tyreGeo = new CylinderGeometry(0.21, 0.21, 0.14, 10);
  const hubGeo  = new CylinderGeometry(0.07, 0.07, 0.15, 7);
  const tyreMat = new MeshStandardMaterial({ color: C.wheel, roughness: 0.95 });
  const hubMat  = new MeshStandardMaterial({ color: "#777777", roughness: 0.5, metalness: 0.6 });

  for (const [wx, wz] of [
    [-0.57, -0.46], [-0.57, 0], [-0.57, 0.46],
    [ 0.57, -0.46], [ 0.57, 0], [ 0.57, 0.46],
  ]) {
    const wg  = new Group();
    const tyr = new Mesh(tyreGeo, tyreMat);
    tyr.rotation.z = Math.PI / 2;
    const hub = new Mesh(hubGeo, hubMat);
    hub.rotation.z = Math.PI / 2;
    wg.add(tyr, hub);
    wg.position.set(wx, 0.22, wz);
    rover.wheels.push(wg);
    root.add(wg);
  }

  // Camera mast
  const mast = new Mesh(new CylinderGeometry(0.03, 0.03, 0.52, 6), sm("#aaaaaa"));
  mast.position.set(0, 1.00, -0.30);
  root.add(mast);

  const head = new Mesh(new BoxGeometry(0.13, 0.11, 0.11), sm("#222222", { metalness: 0.5 }));
  head.position.set(0, 1.30, -0.30);
  root.add(head);

  // Status light — colour updated on status prop change, not every frame
  rover.statusLight = new Mesh(
    new SphereGeometry(0.07, 6, 5),
    new MeshStandardMaterial({ color: C.roverAccent, emissive: new Color(C.roverAccent), emissiveIntensity: 1.2 }),
  );
  rover.statusLight.position.set(0, 0.73, -0.51);
  root.add(rover.statusLight);

  // Drill arm — shown only when mining
  rover.drillGroup = new Group();
  rover.drillGroup.visible = false;
  const arm = new Mesh(new CylinderGeometry(0.03, 0.03, 0.46, 5), sm("#888888"));
  arm.rotation.z = Math.PI / 2;
  arm.position.set(0.33, 0.30, 0.50);
  const bit = new Mesh(new ConeGeometry(0.07, 0.18, 6), sm("#555555", { metalness: 0.7 }));
  bit.rotation.z = -Math.PI / 2;
  bit.position.set(0.58, 0.30, 0.50);
  rover.drillGroup.add(arm, bit);
  root.add(rover.drillGroup);

  rover.root = root;
  return root;
}

// ─── Scene builders ───────────────────────────────────────────────────────────
function buildCells() {
  clearGroup(cellGroup);
  const minedSet = new Set((props.minedCells ?? []).map(p => `${p.x},${p.y}`));

  for (let gy = 0; gy < matrix.value.length; gy++) {
    const row = matrix.value[gy];
    for (let gx = 0; gx < row.length; gx++) {
      cellGroup.add(makeTile(gx, gy));
      if (minedSet.has(`${gx},${gy}`)) { cellGroup.add(makeMinedPit(gx, gy)); continue; }
      switch (row[gx]) {
        case "#": cellGroup.add(makeBarrier(gx, gy)); break;
        case "Y": cellGroup.add(makeGold(gx, gy));   break;
        case "B": cellGroup.add(makeIce(gx, gy));    break;
        case "G": cellGroup.add(makeGreen(gx, gy));  break;
        case "S": cellGroup.add(makeStart(gx, gy));  break;
      }
    }
  }
  markDirty();
}

function buildPath() {
  // Dispose previous tube
  if (pathTubeMesh) {
    pathGroup.remove(pathTubeMesh);
    pathTubeMesh.geometry.dispose();
    pathTubeMesh = null;
  }
  pathTubeMat?.dispose();
  pathTubeMat = null;

  const plan = props.pathPlan ?? [];
  if (plan.length < 2) { markDirty(); return; }

  // Deduplicate consecutive identical cells and build world-space points
  const pts = [];
  let prevKey = null;
  for (const p of plan) {
    if (typeof p.x !== "number" || typeof p.y !== "number") continue;
    const k = `${p.x},${p.y}`;
    if (k === prevKey) continue;
    prevKey = k;
    pts.push(toWorld(p.x, p.y, 0.18));
  }
  if (pts.length < 2) { markDirty(); return; }

  // Duplicate endpoints so the tube reaches all the way to first/last cell
  const curve = new CatmullRomCurve3([pts[0], ...pts, pts[pts.length - 1]]);

  pathTubeMat  = new MeshLambertMaterial({
    color: C.path,
    emissive: new Color(C.path),
    emissiveIntensity: 0.55,
    transparent: true,
    opacity: 0.75,
  });
  pathTubeMesh = new Mesh(new TubeGeometry(curve, pts.length * 4, 0.06, 5, false), pathTubeMat);
  pathGroup.add(pathTubeMesh);
  markDirty();
}

function setRoverTarget() {
  const { x = 0, y = 0 } = props.roverPosition ?? {};
  const next = toWorld(x, y, 0);

  // Compute heading from current → next position (only when actually moving)
  const dx = next.x - roverCurrent.x;
  const dz = next.z - roverCurrent.z;
  if (Math.abs(dx) > 0.01 || Math.abs(dz) > 0.01) {
    // atan2 gives angle in XZ plane; Three.js Y-rotation: 0 = +Z, so we use atan2(dx, dz)
    roverHeadingTarget = Math.atan2(dx, dz);
  }

  roverTarget.copy(next);
  markDirty();
}

function applyLighting() {
  if (!sunLight || !scene) return;
  if (isDay.value) {
    const a = dayFrac.value * Math.PI;
    sunLight.position.set(Math.cos(a) * 28, Math.sin(a) * 20 + 4, -10);
    sunLight.intensity     = 1.1 + Math.sin(a) * 0.25;
    ambientLight.intensity = 0.55;
    scene.background       = new Color(C.skyDay);
  } else {
    sunLight.position.set(-16, 5, -8);
    sunLight.intensity     = 0.08;
    ambientLight.intensity = 0.2;
    scene.background       = new Color(C.skyNight);
  }
  // Solar panel tilt is a one-time set, not per-frame
  if (rover.solarPanel) {
    rover.solarPanel.rotation.z = isDay.value
      ? (Math.PI / 2 - dayFrac.value * Math.PI) * 0.35
      : 0;
  }
  markDirty();
}

function updateStatusLight() {
  if (!rover.statusLight?.material) return;
  const col = C.statusColor[props.roverStatus] ?? C.roverAccent;
  rover.statusLight.material.color.set(col);
  rover.statusLight.material.emissive.set(col);
  markDirty();
}

// ─── Dirty-flag render loop ───────────────────────────────────────────────────
// rAF only runs while something needs updating. At rest: GPU renders nothing.
let lastTs = 0;

function markDirty() {
  if (!frameId) frameId = requestAnimationFrame(renderLoop);
}

const roverTarget  = new Vector3();
const roverCurrent = new Vector3();

function renderLoop(ts) {
  frameId = 0;
  if (!renderer || !scene || !camera) return;

  const dt = Math.min((ts - lastTs) / 1000, 0.05);
  lastTs = ts;
  const t  = ts * 0.001;

  let more = false;   // true = request next frame

  // Orbit inertia
  if (!orb.dragging && (Math.abs(orb.dTheta) > 0.0001 || Math.abs(orb.dPhi) > 0.0001)) {
    orb.theta  += orb.dTheta;
    orb.phi    += orb.dPhi;
    orb.dTheta *= 0.87;
    orb.dPhi   *= 0.87;
    orb.phi     = Math.max(0.15, Math.min(Math.PI * 0.48, orb.phi));
    _orbitApplyNoMark();
    more = true;
  }

  // Rover position lerp
  if (rover.root && roverCurrent.distanceTo(roverTarget) > 0.002) {
    roverCurrent.lerp(roverTarget, 1 - Math.exp(-(isMoving.value ? 5 : 12) * dt));
    rover.root.position.x = roverCurrent.x;
    rover.root.position.z = roverCurrent.z;
    more = true;
  }

  // Rover heading lerp — shortest-angle rotation toward travel direction
  if (rover.root) {
    let diff = roverHeadingTarget - roverHeadingCurrent;
    // Wrap to [-PI, PI] so we always take the short arc
    while (diff >  Math.PI) diff -= Math.PI * 2;
    while (diff < -Math.PI) diff += Math.PI * 2;
    if (Math.abs(diff) > 0.002) {
      roverHeadingCurrent += diff * (1 - Math.exp(-10 * dt));
      rover.root.rotation.y = roverHeadingCurrent;
      more = true;
    }
  }

  // Wheel roll — only while moving
  if (isMoving.value && rover.wheels.length) {
    const roll = props.roverSpeed * 3.5 * dt;
    for (const wg of rover.wheels) wg.rotation.x += roll;
    more = true;
  }

  // Body bob — only while moving, then exponential decay to rest
  if (rover.root) {
    if (isMoving.value) {
      rover.root.position.y = Math.sin(t * 7) * 0.026;
      rover.root.rotation.z = Math.sin(t * 3.5) * 0.016;
      more = true;
    } else if (Math.abs(rover.root.position.y) > 0.001 || Math.abs(rover.root.rotation.z) > 0.001) {
      rover.root.position.y *= Math.exp(-8 * dt);
      rover.root.rotation.z *= Math.exp(-8 * dt);
      more = true;
    }
  }

  // Drill — toggle visibility, spin when mining
  if (rover.drillGroup) {
    if (rover.drillGroup.visible !== isMining.value) {
      rover.drillGroup.visible = isMining.value;
      more = true;
    }
    if (isMining.value) {
      rover.drillGroup.rotation.x += 7 * dt;
      more = true;
    }
  }

  renderer.render(scene, camera);
  if (more) frameId = requestAnimationFrame(renderLoop);
}

// ─── Inline orbit controls ────────────────────────────────────────────────────
const orb = { theta: 0, phi: 1.1, radius: 10, dTheta: 0, dPhi: 0, dragging: false, lastX: 0, lastY: 0, minR: 2, maxR: 100 };

function _orbitApplyNoMark() {
  orb.phi = Math.max(0.15, Math.min(Math.PI * 0.48, orb.phi));
  camera.position.set(
    orb.radius * Math.sin(orb.phi) * Math.sin(orb.theta),
    orb.radius * Math.cos(orb.phi),
    orb.radius * Math.sin(orb.phi) * Math.cos(orb.theta),
  );
  camera.lookAt(0, 0, 0);
}
function orbitApply() { _orbitApplyNoMark(); markDirty(); }

function orbitOnDown(e) {
  if (e.button !== 0) return;
  orb.dragging = true; orb.lastX = e.clientX; orb.lastY = e.clientY; orb.dTheta = 0; orb.dPhi = 0;
}
function orbitOnMove(e) {
  if (!orb.dragging) return;
  orb.dTheta = -(e.clientX - orb.lastX) * 0.008;
  orb.dPhi   = -(e.clientY - orb.lastY) * 0.008;
  orb.theta += orb.dTheta; orb.phi += orb.dPhi;
  orb.lastX = e.clientX; orb.lastY = e.clientY;
  orbitApply();
}
function orbitOnUp() { orb.dragging = false; }
function orbitOnWheel(e) {
  e.preventDefault();
  orb.radius = Math.min(orb.maxR, Math.max(orb.minR, orb.radius * (e.deltaY > 0 ? 1.08 : 0.93)));
  orbitApply();
}

let _pinch = 0;
function orbitOnTouchStart(e) {
  if (e.touches.length === 1) {
    orb.dragging = true; orb.lastX = e.touches[0].clientX; orb.lastY = e.touches[0].clientY; orb.dTheta = 0; orb.dPhi = 0;
  } else if (e.touches.length === 2) {
    orb.dragging = false;
    _pinch = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY);
  }
}
function orbitOnTouchMove(e) {
  e.preventDefault();
  if (e.touches.length === 1 && orb.dragging) {
    orb.dTheta = -(e.touches[0].clientX - orb.lastX) * 0.009;
    orb.dPhi   = -(e.touches[0].clientY - orb.lastY) * 0.009;
    orb.theta += orb.dTheta; orb.phi += orb.dPhi;
    orb.lastX = e.touches[0].clientX; orb.lastY = e.touches[0].clientY;
    orbitApply();
  } else if (e.touches.length === 2) {
    const d = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY);
    orb.radius = Math.min(orb.maxR, Math.max(orb.minR, orb.radius * (_pinch / d)));
    _pinch = d; orbitApply();
  }
}
function orbitOnTouchEnd() { orb.dragging = false; }

function orbitAttach(el) {
  el.addEventListener("pointerdown",   orbitOnDown);
  el.addEventListener("pointermove",   orbitOnMove,         { passive: true });
  el.addEventListener("pointerup",     orbitOnUp);
  el.addEventListener("pointercancel", orbitOnUp);
  el.addEventListener("wheel",         orbitOnWheel,        { passive: false });
  el.addEventListener("touchstart",    orbitOnTouchStart,   { passive: true });
  el.addEventListener("touchmove",     orbitOnTouchMove,    { passive: false });
  el.addEventListener("touchend",      orbitOnTouchEnd,     { passive: true });
}
function orbitDetach(el) {
  el.removeEventListener("pointerdown",   orbitOnDown);
  el.removeEventListener("pointermove",   orbitOnMove);
  el.removeEventListener("pointerup",     orbitOnUp);
  el.removeEventListener("pointercancel", orbitOnUp);
  el.removeEventListener("wheel",         orbitOnWheel);
  el.removeEventListener("touchstart",    orbitOnTouchStart);
  el.removeEventListener("touchmove",     orbitOnTouchMove);
  el.removeEventListener("touchend",      orbitOnTouchEnd);
}

// ─── Resize ───────────────────────────────────────────────────────────────────
function onResize() {
  if (!canvasWrap.value || !camera || !renderer) return;
  const w = Math.max(canvasWrap.value.clientWidth, 1);
  const h = Math.max(canvasWrap.value.clientHeight, 1);
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  markDirty();
}

// ─── Lifecycle ────────────────────────────────────────────────────────────────
onMounted(() => {
  if (!canvasWrap.value) return;

  buildShared();

  scene = new Scene();
  scene.background = new Color(C.skyDay);

  const span = Math.max(rowCount.value, colCount.value) * CELL;
  camera     = new PerspectiveCamera(50, 1, 0.1, 500);
  orb.radius = span * 1.55;
  orb.minR   = span * 0.44;
  orb.maxR   = span * 4.5;
  orbitApply();

  renderer = new WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(1);            // cap at 1 — biggest single perf win on HiDPI
  renderer.shadowMap.enabled = false;   // no shadows needed
  canvasWrap.value.appendChild(renderer.domElement);

  ambientLight = new AmbientLight("#ffffff", 0.55);
  sunLight     = new DirectionalLight("#ffe8c0", 1.2);
  scene.add(ambientLight, sunLight);

  cellGroup = new Group();
  pathGroup = new Group();
  scene.add(cellGroup, pathGroup);

  buildCells();
  buildPath();
  scene.add(buildRover());
  updateStatusLight();

  const { x = 0, y = 0 } = props.roverPosition ?? {};
  const sp = toWorld(x, y, 0);
  roverCurrent.copy(sp);
  roverTarget.copy(sp);
  rover.root.position.copy(sp);

  applyLighting();
  onResize();

  orbitAttach(canvasWrap.value);
  resizeObs = new ResizeObserver(onResize);
  resizeObs.observe(canvasWrap.value);

  lastTs  = performance.now();
  markDirty();
});

onBeforeUnmount(() => {
  if (frameId) { cancelAnimationFrame(frameId); frameId = 0; }
  resizeObs?.disconnect();
  if (canvasWrap.value) orbitDetach(canvasWrap.value);

  // Remove children from groups (no geo/mat disposal — shared assets handle that)
  clearGroup(cellGroup);
  if (pathTubeMesh) { pathGroup.remove(pathTubeMesh); pathTubeMesh.geometry.dispose(); }
  pathTubeMat?.dispose();

  // Rover has unique geometry/material — dispose them
  if (rover.root) {
    rover.root.traverse(o => { o.geometry?.dispose(); o.material?.dispose(); });
    scene?.remove(rover.root);
  }

  disposeShared();   // frees all shared geo + mat + pathMat

  renderer?.dispose();
  renderer?.forceContextLoss();
  if (renderer?.domElement?.parentNode === canvasWrap.value)
    canvasWrap.value.removeChild(renderer.domElement);

  scene = camera = renderer = null;
});

// ─── Watchers ─────────────────────────────────────────────────────────────────
watch(matrix,                    () => buildCells(),       { deep: true });
watch(() => props.minedCells,    () => buildCells(),       { deep: true });
watch(() => props.pathPlan,      () => buildPath(),        { deep: true });
watch(() => props.roverPosition, () => setRoverTarget(),   { deep: true });
watch(() => props.timeOfDay,     () => applyLighting());
watch(() => props.roverStatus,   () => updateStatusLight());
</script>

<template>
  <div ref="canvasWrap" class="canvas-wrap" />
</template>

<style scoped>
.canvas-wrap {
  width: 100%;
  height: 100%;
  display: block;
  cursor: grab;
  touch-action: none;
  user-select: none;
  -webkit-user-select: none;
}
.canvas-wrap:active {
  cursor: grabbing;
}
</style>