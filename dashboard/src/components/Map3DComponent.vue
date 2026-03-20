<script setup>
/**
 * Map3DComponent.vue
 *
 * Controls:
 *  - Left-drag   → pan camera (translate look-at in XZ)
 *  - Right-drag  → orbit (rotate around look-at point)
 *  - Scroll      → zoom
 *  - Two-finger pinch → zoom (touch)
 *  - Two-finger drag  → pan (touch)
 *  - Keyboard:
 *      W/A/S/D or Arrow keys → pan
 *      Q / E                 → rotate left / right
 *      + / =                 → zoom in
 *      - / _                 → zoom out
 *      R                     → reset camera
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
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
  IcosahedronGeometry
} from 'three'

// ─── Props ────────────────────────────────────────────────────────────────────
const props = defineProps({
  mapMatrix:    { type: Array,  required: true },
  roverPosition:{ type: Object, required: true },
  pathPlan:     { type: Array,  default: () => [] },
  minedCells:   { type: Array,  default: () => [] },
  roverStatus:  { type: String, default: 'idle' },
  roverSpeed:   { type: Number, default: 1 },
  timeOfDay:    { type: Number, default: 12 },
  dayHrs:       { type: Number, default: 16 },
  nightHrs:     { type: Number, default: 8 },
})

// ─── Scene constants ──────────────────────────────────────────────────────────
const CELL = 2.2
const HALF = CELL / 2

const C = Object.freeze({
  skyDay:   '#1a0e05',
  skyNight: '#06040a',
  ground:   '#c47a3a',
  barrier:  '#3a1e0a',
  gold:     '#f0c040',
  ice:      '#a0d0f0',
  green:    '#30d070',
  start:    '#ff6b35',
  path:     '#44d1ff',
  mined:    '#120600',
  rover:    '#dce3e8',
  roverAccent: '#ff6b35',
  solar:    '#1a3a6e',
  wheel:    '#1c1c1c',
  statusColor: {
    mine:    '#ffaa00',
    move:    '#44d1ff',
    charge:  '#ffd700',
    standby: '#334455',
    idle:    '#ff6b35',
  },
})

// ─── Derived computeds ────────────────────────────────────────────────────────
const matrix   = computed(() => (Array.isArray(props.mapMatrix) ? props.mapMatrix : []))
const rowCount = computed(() => matrix.value.length || 1)
const colCount = computed(() => matrix.value[0]?.length || 1)
const cycle    = computed(() => props.dayHrs + props.nightHrs)
const isDay    = computed(() => props.timeOfDay % cycle.value < props.dayHrs)
const dayFrac  = computed(() => (props.timeOfDay % cycle.value) / cycle.value)
const isMoving = computed(() => props.roverStatus === 'move')
const isMining = computed(() => props.roverStatus === 'mine')

// ─── DOM ──────────────────────────────────────────────────────────────────────
const canvasWrap = ref(null)

// ─── Three.js state ───────────────────────────────────────────────────────────
let scene, camera, renderer, frameId, resizeObs
let cellGroup, pathGroup
let ambientLight, sunLight

// ─── Shared static assets ─────────────────────────────────────────────────────
const S = {
  gTile: null,
  gBarrier: null, gBarrierB: null, gBarrierC: null, gBarrierSlab: null,
  gGoldCryst: null, gGoldBase: null,
  gIceCryst: null, gIceBase: null,
  gGreenOrb: null, gGreenSpike: null,
  gPole: null, gFlag: null, gPit: null,
  mTile: null,
  mBarrier: null, mBarrierDark: null, mBarrierLight: null, mBarrierMid: null,
  mGold: null, mGoldVein: null, mGoldRock: null,
  mIce: null, mIceCore: null, mIceRock: null,
  mGreen: null, mGreenDark: null, mGreenRock: null,
  mStart: null, mPole: null, mMined: null,
}

let pathTubeMesh = null
let pathTubeMat  = null
let roverHeadingTarget  = 0
let roverHeadingCurrent = 0

function buildShared() {
  S.gTile = new PlaneGeometry(CELL - 0.1, CELL - 0.1)

  // Rock barrier: flat angular slab strata, like sedimentary rock layers
  S.gBarrier      = new BoxGeometry(1.55, 0.36, 1.3)   // wide bottom slab
  S.gBarrierB     = new BoxGeometry(1.25, 0.32, 1.05)  // middle slab
  S.gBarrierC     = new BoxGeometry(0.88, 0.28, 0.72)  // top slab
  S.gBarrierSlab  = new BoxGeometry(0.52, 0.22, 0.44)  // accent chip

  // Ore bases — large flattened icosahedra that fill the cell
  S.gGoldBase  = new IcosahedronGeometry(0.62, 1)
  S.gGoldCryst = new OctahedronGeometry(0.22, 0)

  S.gIceBase   = new IcosahedronGeometry(0.58, 1)
  S.gIceCryst  = new OctahedronGeometry(0.15, 0)

  S.gGreenOrb  = new IcosahedronGeometry(0.6, 1)
  S.gGreenSpike= new OctahedronGeometry(0.11, 0)

  S.gPole = new CylinderGeometry(0.03, 0.03, 0.88, 5)
  S.gFlag = new BoxGeometry(0.26, 0.16, 0.02)
  S.gPit  = new CylinderGeometry(CELL * 0.34, CELL * 0.24, 0.22, 7)

  S.mTile = new MeshLambertMaterial({ color: C.ground })

  // Rock: layered sedimentary strata — warm sandy stone tones
  S.mBarrier      = new MeshStandardMaterial({ color: '#7a6e5e', roughness: 0.97, metalness: 0.0 })
  S.mBarrierMid   = new MeshStandardMaterial({ color: '#635a4c', roughness: 0.96, metalness: 0.0 })
  S.mBarrierDark  = new MeshStandardMaterial({ color: '#4a4038', roughness: 0.98, metalness: 0.0 })
  S.mBarrierLight = new MeshStandardMaterial({ color: '#9a8e7a', roughness: 0.94, metalness: 0.02 })

  // Gold ore
  S.mGoldRock = new MeshStandardMaterial({ color: '#5c4a2e', roughness: 0.9,  metalness: 0.05 })
  S.mGold     = new MeshStandardMaterial({ color: '#d4a017', roughness: 0.3,  metalness: 0.85, emissive: new Color('#c8920a'), emissiveIntensity: 0.2 })
  S.mGoldVein = new MeshStandardMaterial({ color: '#f5d060', roughness: 0.15, metalness: 0.95, emissive: new Color('#ffcc00'), emissiveIntensity: 0.4 })

  // Ice ore
  S.mIceRock  = new MeshStandardMaterial({ color: '#2a3848', roughness: 0.88, metalness: 0.08 })
  S.mIce      = new MeshStandardMaterial({ color: '#b8e0f8', roughness: 0.05, metalness: 0.2,  emissive: new Color('#70c0f0'), emissiveIntensity: 0.3,  transparent: true, opacity: 0.82 })
  S.mIceCore  = new MeshStandardMaterial({ color: '#ffffff', roughness: 0.0,  metalness: 0.35, emissive: new Color('#aaddff'), emissiveIntensity: 0.55, transparent: true, opacity: 0.68 })

  // Green ore
  S.mGreenRock = new MeshStandardMaterial({ color: '#1c3328', roughness: 0.9,  metalness: 0.05 })
  S.mGreen     = new MeshStandardMaterial({ color: '#22c55e', roughness: 0.18, metalness: 0.42, emissive: new Color('#16a34a'), emissiveIntensity: 0.42 })
  S.mGreenDark = new MeshStandardMaterial({ color: '#15803d', roughness: 0.28, metalness: 0.38, emissive: new Color('#166534'), emissiveIntensity: 0.28 })

  S.mStart = new MeshLambertMaterial({ color: C.start, emissive: new Color(C.start), emissiveIntensity: 0.2 })
  S.mPole  = new MeshLambertMaterial({ color: '#888888' })
  S.mMined = new MeshLambertMaterial({ color: C.mined })
}
function disposeShared() {
  for (const v of Object.values(S)) v?.dispose?.()
  pathTubeMat?.dispose()
  pathTubeMesh?.geometry?.dispose()
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function toWorld(cx, cy, y = 0) {
  return new Vector3(
    cx * CELL - colCount.value * HALF + HALF,
    y,
    cy * CELL - rowCount.value * HALF + HALF,
  )
}

function clearGroup(g) {
  if (!g) return
  while (g.children.length) g.remove(g.children[g.children.length - 1])
}

function normalizeStep(step) {
  if (Array.isArray(step) && step.length >= 2) {
    return { x: Number(step[0]), y: Number(step[1]) }
  }
  return { x: Number(step?.x ?? 0), y: Number(step?.y ?? 0) }
}

function isRelativePath(pathPlan) {
  if (!Array.isArray(pathPlan) || pathPlan.length === 0) return true
  return pathPlan.every((step) => {
    const { x, y } = normalizeStep(step)
    return Number.isFinite(x) && Number.isFinite(y) && Math.abs(x) <= 1 && Math.abs(y) <= 1
  })
}

// ─── Cell factories ───────────────────────────────────────────────────────────
function makeTile(gx, gy) {
  const m = new Mesh(S.gTile, S.mTile)
  m.rotation.x = -Math.PI / 2
  m.position.copy(toWorld(gx, gy, 0))
  return m
}
// Rocky barrier — clusters of jagged boulders
function makeBarrier(gx, gy) {
  const g = new Group()

  // Bottom slab — widest, sits flush with ground, slightly rotated
  const bot = new Mesh(S.gBarrier, S.mBarrierDark)
  bot.position.set(0.04, 0.4, -0.05)
  bot.rotation.set(0.0, 0.38, 0.04)
  bot.scale.set(1,2,1)

  // Middle slab — offset and counter-rotated for that broken-strata feel
  const mid = new Mesh(S.gBarrierB, S.mBarrierMid)
  mid.position.set(-0.06, 0.8, 0.06)
  mid.rotation.set(0.02, -0.55, -0.05)
  mid.scale.set(1,2.5,1)

  // Top slab — narrowest, more tilted, like it's about to topple
  const top = new Mesh(S.gBarrierC, S.mBarrier)
  top.position.set(0.10, 1.3, -0.04)
  top.rotation.set(0.06, 0.72, 0.10)
  top.scale.set(1,2.2,1)

  // Accent chip — small slab wedged to the side
  const chip = new Mesh(S.gBarrierSlab, S.mBarrierLight)
  chip.position.set(0.72, 0.28, 0.42)
  chip.rotation.set(0.08, -0.3, 0.22)

  // Second chip on other side
  const chip2 = new Mesh(S.gBarrierSlab, S.mBarrierDark)
  chip2.position.set(-0.65, 0.22, -0.48)
  chip2.rotation.set(-0.05, 1.1, -0.18)
  chip2.scale.set(0.8, 0.7, 0.9)

  g.add(bot, mid, top, chip, chip2)
  g.position.copy(toWorld(gx, gy, 0))
  return g
}
// Gold ore deposit — rocky host stone with metallic crystal veins jutting out
function makeGold(gx, gy) {
  const g = new Group()

  // Large host rock base — fills the cell
  const rock = new Mesh(S.gGoldBase, S.mGoldRock)
  rock.position.set(0, 0.28, 0)
  rock.rotation.set(0.3, 0.7, 0.15)
  rock.scale.set(1.55, 0.88, 1.45)

  // Main tall crystal shard
  const c1 = new Mesh(S.gGoldCryst, S.mGold)
  c1.position.set(-0.08, 0.9, 0.06)
  c1.rotation.set(0.15, 0.5, -0.18)
  c1.scale.set(0.9, 2.0, 0.9)

  // Bright vein shard
  const c2 = new Mesh(S.gGoldCryst, S.mGoldVein)
  c2.position.set(0.32, 0.9, -0.14)
  c2.rotation.set(-0.25, 1.2, 0.32)
  c2.scale.set(0.7, 1.6, 0.7)

  // Cluster shard
  const c3 = new Mesh(S.gGoldCryst, S.mGold)
  c3.position.set(-0.28, 0.9, -0.2)
  c3.rotation.set(0.45, 2.0, 0.12)
  c3.scale.set(0.55, 1.2, 0.55)

  // Surface sparkle
  const c4 = new Mesh(S.gGoldCryst, S.mGoldVein)
  c4.position.set(0.2, 0.38, 0.26)
  c4.rotation.set(-0.1, 0.8, 0.55)
  c4.scale.setScalar(0.42)

  g.add(rock, c1, c2, c3, c4)
  g.position.copy(toWorld(gx, gy, 0))
  return g
}
// Ice ore — dark rocky base with tall translucent ice crystal formations
function makeIce(gx, gy) {
  const g = new Group()

  // Dark base rock
  const rock = new Mesh(S.gIceBase, S.mIceRock)
  rock.position.set(0, 0.14, 0)
  rock.rotation.set(0.2, 1.1, 0.1)
  rock.scale.set(1.7, 0.9, 1.5)

  // Main tall crystal
  const ic1 = new Mesh(S.gIceCryst, S.mIce)
  ic1.position.set(-0.08, 0.7, 0.08)
  ic1.rotation.set(0.1, 0.3, -0.12)
  ic1.scale.set(0.9, 2.2, 0.9)

  // Inner bright core
  const ic1core = new Mesh(S.gIceCryst, S.mIceCore)
  ic1core.position.set(-0.08, 0.7, 0.08)
  ic1core.rotation.set(0.1, 0.3, -0.12)
  ic1core.scale.set(0.45, 2.0, 0.45)

  // Side crystal
  const ic2 = new Mesh(S.gIceCryst, S.mIce)
  ic2.position.set(0.24, 0.7, -0.1)
  ic2.rotation.set(-0.2, 1.4, 0.3)
  ic2.scale.set(0.7, 1.7, 0.7)

  // Small accent
  const ic3 = new Mesh(S.gIceCryst, S.mIce)
  ic3.position.set(-0.26, 0.7, -0.2)
  ic3.rotation.set(0.4, 0.6, -0.2)
  ic3.scale.set(0.5, 1.3, 0.5)

  g.add(rock, ic1, ic1core, ic2, ic3)
  g.position.copy(toWorld(gx, gy, 0))
  return g
}

// Green ore — dark host rock with glowing emerald crystal growths
function makeGreen(gx, gy) {
  const g = new Group()

  // Large host rock
  const rock = new Mesh(S.gGreenOrb, S.mGreenRock)
  rock.position.set(0, 0.23, 0)
  rock.rotation.set(0.25, 0.5, 0.15)
  rock.scale.set(1.58, 0.88, 1.5)

  // Glowing core orb
  const orb = new Mesh(S.gGreenOrb, S.mGreen)
  orb.position.set(0, 0.1, 0)
  orb.rotation.set(0.15, 0.9, 0.1)
  orb.scale.set(0.72, 0.62, 0.7)

  // Central tall spike
  const sp1 = new Mesh(S.gGreenSpike, S.mGreen)
  sp1.position.set(0, 0.9, 0)
  sp1.scale.set(0.9, 2.2, 0.9)

  // Surrounding spikes
  const sp2 = new Mesh(S.gGreenSpike, S.mGreenDark)
  sp2.position.set(0.22, 0.66, 0.14)
  sp2.rotation.set(0.35, 0.8, 0.32)
  sp2.scale.set(0.7, 1.7, 0.7)

  const sp3 = new Mesh(S.gGreenSpike, S.mGreen)
  sp3.position.set(-0.2, 0.9, -0.2)
  sp3.rotation.set(-0.3, 1.5, -0.28)
  sp3.scale.set(0.6, 1.5, 0.6)

  const sp4 = new Mesh(S.gGreenSpike, S.mGreenDark)
  sp4.position.set(0.12, 0.77, -0.3)
  sp4.rotation.set(-0.45, 2.2, 0.18)
  sp4.scale.set(0.5, 1.2, 0.5)

  const sp5 = new Mesh(S.gGreenSpike, S.mGreen)
  sp5.position.set(-0.3, 0.7, 0.18)
  sp5.rotation.set(0.28, 3.0, -0.22)
  sp5.scale.set(0.45, 1.1, 0.45)

  g.add(rock, orb, sp1, sp2, sp3, sp4, sp5)
  g.position.copy(toWorld(gx, gy, 0))
  return g
}
function makeStart(gx, gy) {
  const g = new Group()
  const pole = new Mesh(S.gPole, S.mPole); pole.position.y = 0.44
  const flag = new Mesh(S.gFlag, S.mStart); flag.position.set(0.13, 0.86, 0)
  g.add(pole, flag)
  g.position.copy(toWorld(gx, gy, 0))
  return g
}
function makeMinedPit(gx, gy) {
  const m = new Mesh(S.gPit, S.mMined)
  m.position.copy(toWorld(gx, gy, -0.09))
  return m
}

// ─── Rover ────────────────────────────────────────────────────────────────────
const rover = { root: null, wheels: [], statusLight: null, solarPanel: null, drillGroup: null }

function buildRover() {
  rover.wheels = []
  rover.statusLight = null
  rover.solarPanel  = null
  rover.drillGroup  = null
  const root = new Group()
  const sm = (col, o = {}) => new MeshStandardMaterial({ color: col, roughness: 0.55, metalness: 0.2, ...o })

  const chassis = new Mesh(new BoxGeometry(1.0, 0.18, 1.3), sm(C.rover, { roughness: 0.5 }))
  chassis.position.y = 0.42; root.add(chassis)

  const body = new Mesh(new BoxGeometry(0.8, 0.3, 0.86), sm(C.rover))
  body.position.y = 0.64; root.add(body)

  const panel = new Mesh(
    new BoxGeometry(1.42, 0.04, 0.68),
    new MeshStandardMaterial({ color: C.solar, roughness: 0.3, metalness: 0.7, emissive: new Color('#001a55'), emissiveIntensity: 0.3 }),
  )
  panel.position.y = 0.83
  rover.solarPanel = panel; root.add(panel)

  const tyreGeo = new CylinderGeometry(0.21, 0.21, 0.14, 10)
  const hubGeo  = new CylinderGeometry(0.07, 0.07, 0.15, 7)
  const tyreMat = new MeshStandardMaterial({ color: C.wheel, roughness: 0.95 })
  const hubMat  = new MeshStandardMaterial({ color: '#777777', roughness: 0.5, metalness: 0.6 })
  for (const [wx, wz] of [[-0.57,-0.46],[-0.57,0],[-0.57,0.46],[0.57,-0.46],[0.57,0],[0.57,0.46]]) {
    const wg  = new Group()
    const tyr = new Mesh(tyreGeo, tyreMat); tyr.rotation.z = Math.PI / 2
    const hub = new Mesh(hubGeo, hubMat);   hub.rotation.z = Math.PI / 2
    wg.add(tyr, hub)
    wg.position.set(wx, 0.22, wz)
    rover.wheels.push(wg); root.add(wg)
  }

  const mast = new Mesh(new CylinderGeometry(0.03, 0.03, 0.52, 6), sm('#aaaaaa'))
  mast.position.set(0, 1.0, -0.3); root.add(mast)
  const head = new Mesh(new BoxGeometry(0.13, 0.11, 0.11), sm('#222222', { metalness: 0.5 }))
  head.position.set(0, 1.3, -0.3); root.add(head)

  rover.statusLight = new Mesh(
    new SphereGeometry(0.07, 6, 5),
    new MeshStandardMaterial({ color: C.roverAccent, emissive: new Color(C.roverAccent), emissiveIntensity: 1.2 }),
  )
  rover.statusLight.position.set(0, 0.73, -0.51); root.add(rover.statusLight)

  rover.drillGroup = new Group()
  rover.drillGroup.visible = false
  const arm = new Mesh(new CylinderGeometry(0.03, 0.03, 0.46, 5), sm('#888888'))
  arm.rotation.z = Math.PI / 2; arm.position.set(0.33, 0.3, 0.5)
  const bit = new Mesh(new ConeGeometry(0.07, 0.18, 6), sm('#555555', { metalness: 0.7 }))
  bit.rotation.z = -Math.PI / 2; bit.position.set(0.58, 0.3, 0.5)
  rover.drillGroup.add(arm, bit); root.add(rover.drillGroup)

  rover.root = root
  return root
}

// ─── Scene builders ───────────────────────────────────────────────────────────
function buildCells() {
  clearGroup(cellGroup)
  const minedSet = new Set((props.minedCells ?? []).map((p) => `${p.x},${p.y}`))
  for (let gy = 0; gy < matrix.value.length; gy++) {
    const row = matrix.value[gy]
    for (let gx = 0; gx < row.length; gx++) {
      cellGroup.add(makeTile(gx, gy))
      if (minedSet.has(`${gx},${gy}`)) { cellGroup.add(makeMinedPit(gx, gy)); continue }
      switch (row[gx]) {
        case '#': cellGroup.add(makeBarrier(gx, gy)); break
        case 'Y': cellGroup.add(makeGold(gx, gy));    break
        case 'B': cellGroup.add(makeIce(gx, gy));     break
        case 'G': cellGroup.add(makeGreen(gx, gy));   break
        case 'S': cellGroup.add(makeStart(gx, gy));   break
      }
    }
  }
  markDirty()
}

function buildPath() {
  if (pathTubeMesh) { pathGroup.remove(pathTubeMesh); pathTubeMesh.geometry.dispose(); pathTubeMesh = null }
  pathTubeMat?.dispose(); pathTubeMat = null

  const plan = props.pathPlan ?? []
  if (plan.length < 2) { markDirty(); return }

  const pts = []
  let prevKey = null
  const isRelative = isRelativePath(plan)

  if (isRelative) {
    let currentX = Number(props.roverPosition?.x ?? 0)
    let currentY = Number(props.roverPosition?.y ?? 0)
    for (const step of plan) {
      const { x, y } = normalizeStep(step)
      if (!Number.isFinite(x) || !Number.isFinite(y)) continue
      const nextX = currentX + x
      const nextY = currentY + y
      const k = `${nextX},${nextY}`
      if (k === prevKey) { currentX = nextX; currentY = nextY; continue }
      prevKey = k
      pts.push(toWorld(nextX, nextY, 0.05))
      currentX = nextX
      currentY = nextY
    }
  } else {
    for (const p of plan) {
      const { x, y } = normalizeStep(p)
      if (!Number.isFinite(x) || !Number.isFinite(y)) continue
      const k = `${x},${y}`
      if (k === prevKey) continue
      prevKey = k
      pts.push(toWorld(x, y, 0.05))
    }
  }
  if (pts.length < 2) { markDirty(); return }

  const curve = new CatmullRomCurve3(pts, false, 'catmullrom', 0)
  pathTubeMat  = new MeshLambertMaterial({ color: C.path, emissive: new Color(C.path), emissiveIntensity: 0.65, transparent: true, opacity: 0.85 })
  pathTubeMesh = new Mesh(new TubeGeometry(curve, Math.max(pts.length * 4, 8), 0.07, 6, false), pathTubeMat)
  pathGroup.add(pathTubeMesh)
  markDirty()
}

function setRoverTarget() {
  const { x = 0, y = 0 } = props.roverPosition ?? {}
  const next = toWorld(x, y, 0)
  const dx = next.x - roverCurrent.x
  const dz = next.z - roverCurrent.z
  if (Math.abs(dx) > 0.01 || Math.abs(dz) > 0.01) roverHeadingTarget = Math.atan2(dx, dz)
  roverTarget.copy(next)
  markDirty()
}

function applyLighting() {
  if (!sunLight || !scene) return
  if (isDay.value) {
    const a = dayFrac.value * Math.PI
    sunLight.position.set(Math.cos(a) * 28, Math.sin(a) * 20 + 4, -10)
    sunLight.intensity = 1.1 + Math.sin(a) * 0.25
    ambientLight.intensity = 0.55
    scene.background = new Color(C.skyDay)
  } else {
    sunLight.position.set(-16, 5, -8)
    sunLight.intensity = 0.08
    ambientLight.intensity = 0.2
    scene.background = new Color(C.skyNight)
  }
  if (rover.solarPanel) {
    rover.solarPanel.rotation.z = isDay.value ? (Math.PI / 2 - dayFrac.value * Math.PI) * 0.35 : 0
  }
  markDirty()
}

function updateStatusLight() {
  if (!rover.statusLight?.material) return
  const col = C.statusColor[props.roverStatus] ?? C.roverAccent
  rover.statusLight.material.color.set(col)
  rover.statusLight.material.emissive.set(col)
  markDirty()
}

// ─── Dirty-flag render loop ───────────────────────────────────────────────────
let lastTs = 0
function markDirty() {
  if (!frameId) frameId = requestAnimationFrame(renderLoop)
}

const roverTarget  = new Vector3()
const roverCurrent = new Vector3()

function renderLoop(ts) {
  frameId = 0
  if (!renderer || !scene || !camera) return
  const dt = Math.min((ts - lastTs) / 1000, 0.05)
  lastTs = ts
  const t  = ts * 0.001
  let more = false

  // ── Camera inertia ──────────────────────────────────────────────────────────
  if (!cam.panDragging && (Math.abs(cam.vPanX) > 0.0001 || Math.abs(cam.vPanZ) > 0.0001)) {
    cam.targetX += cam.vPanX; cam.targetZ += cam.vPanZ
    cam.vPanX *= 0.85; cam.vPanZ *= 0.85
    _camApplyNoMark(); more = true
  }
  if (!cam.orbitDragging && (Math.abs(cam.vTheta) > 0.0001 || Math.abs(cam.vPhi) > 0.0001)) {
    cam.theta += cam.vTheta; cam.phi += cam.vPhi
    cam.vTheta *= 0.87; cam.vPhi *= 0.87
    cam.phi = Math.max(0.12, Math.min(Math.PI * 0.48, cam.phi))
    _camApplyNoMark(); more = true
  }
  if (Math.abs(cam.vZoom) > 0.001) {
    cam.radius = Math.min(cam.maxR, Math.max(cam.minR, cam.radius + cam.vZoom))
    cam.vZoom *= 0.82; _camApplyNoMark(); more = true
  }

  // ── Keyboard input ─────────────────────────────────────────────────────────
  if (keys.size > 0) {
    const panSpd  = cam.radius * 0.018
    const rotSpd  = 0.03
    const zoomSpd = cam.radius * 0.04
    const sinA = Math.sin(cam.theta)
    const cosA = Math.cos(cam.theta)
    if (keys.has('w') || keys.has('arrowup'))    { cam.targetX -= sinA * panSpd; cam.targetZ -= cosA * panSpd }
    if (keys.has('s') || keys.has('arrowdown'))  { cam.targetX += sinA * panSpd; cam.targetZ += cosA * panSpd }
    if (keys.has('a') || keys.has('arrowleft'))  { cam.targetX -= cosA * panSpd; cam.targetZ += sinA * panSpd }
    if (keys.has('d') || keys.has('arrowright')) { cam.targetX += cosA * panSpd; cam.targetZ -= sinA * panSpd }
    if (keys.has('q')) cam.theta -= rotSpd
    if (keys.has('e')) cam.theta += rotSpd
    if (keys.has('+') || keys.has('=')) cam.radius = Math.max(cam.minR, cam.radius - zoomSpd)
    if (keys.has('-') || keys.has('_')) cam.radius = Math.min(cam.maxR, cam.radius + zoomSpd)
    _camApplyNoMark(); more = true
  }

  // ── Rover lerp ─────────────────────────────────────────────────────────────
  if (rover.root && roverCurrent.distanceTo(roverTarget) > 0.002) {
    roverCurrent.lerp(roverTarget, 1 - Math.exp(-(isMoving.value ? 5 : 12) * dt))
    rover.root.position.x = roverCurrent.x
    rover.root.position.z = roverCurrent.z
    more = true
  }
  if (rover.root) {
    let diff = roverHeadingTarget - roverHeadingCurrent
    while (diff >  Math.PI) diff -= Math.PI * 2
    while (diff < -Math.PI) diff += Math.PI * 2
    if (Math.abs(diff) > 0.002) {
      roverHeadingCurrent += diff * (1 - Math.exp(-10 * dt))
      rover.root.rotation.y = roverHeadingCurrent
      more = true
    }
  }

  if (isMoving.value && rover.wheels.length) {
    const roll = props.roverSpeed * 3.5 * dt
    for (const wg of rover.wheels) wg.rotation.x += roll
    more = true
  }

  if (rover.root) {
    if (isMoving.value) {
      rover.root.position.y = Math.sin(t * 7) * 0.026
      rover.root.rotation.z = Math.sin(t * 3.5) * 0.016
      more = true
    } else if (Math.abs(rover.root.position.y) > 0.001 || Math.abs(rover.root.rotation.z) > 0.001) {
      rover.root.position.y *= Math.exp(-8 * dt)
      rover.root.rotation.z *= Math.exp(-8 * dt)
      more = true
    }
  }

  if (rover.drillGroup) {
    if (rover.drillGroup.visible !== isMining.value) { rover.drillGroup.visible = isMining.value; more = true }
    if (isMining.value) { rover.drillGroup.rotation.x += 7 * dt; more = true }
  }

  renderer.render(scene, camera)
  if (more) frameId = requestAnimationFrame(renderLoop)
}

// ─── Combined camera state ────────────────────────────────────────────────────
const cam = {
  targetX: 0, targetZ: 0,
  theta: 0, phi: 0.95, radius: 10, minR: 2, maxR: 100,
  panDragging: false, panLastX: 0, panLastY: 0, vPanX: 0, vPanZ: 0,
  orbitDragging: false, orbitLastX: 0, orbitLastY: 0, vTheta: 0, vPhi: 0,
  vZoom: 0,
}

function _camApplyNoMark() {
  if (!camera) return
  cam.phi = Math.max(0.12, Math.min(Math.PI * 0.48, cam.phi))
  const sinP = Math.sin(cam.phi), cosP = Math.cos(cam.phi)
  const sinT = Math.sin(cam.theta), cosT = Math.cos(cam.theta)
  camera.position.set(
    cam.targetX + cam.radius * sinP * sinT,
    cam.radius * cosP,
    cam.targetZ + cam.radius * sinP * cosT,
  )
  camera.lookAt(cam.targetX, 0, cam.targetZ)
}
function camApply() { _camApplyNoMark(); markDirty() }

function camReset() {
  cam.targetX = 0; cam.targetZ = 0
  cam.theta = 0; cam.phi = 0.95; cam.radius = cam.minR * 2.5
  cam.vPanX = 0; cam.vPanZ = 0; cam.vTheta = 0; cam.vPhi = 0; cam.vZoom = 0
  camApply()
}

function screenToWorldPan(dx, dy) {
  if (!camera) return [0, 0]
  const fwd   = new Vector3()
  camera.getWorldDirection(fwd)
  const right = new Vector3().crossVectors(fwd, new Vector3(0, 1, 0)).normalize()
  fwd.y = 0; fwd.normalize()
  const scale = cam.radius * 0.003
  return [(-dx * right.x + dy * fwd.x) * scale, (-dx * right.z + dy * fwd.z) * scale]
}

// ─── Keyboard state ───────────────────────────────────────────────────────────
const keys = new Set()
function onKeyDown(e) {
  const k = e.key.toLowerCase()
  if (e.target !== document.body && e.target.tagName !== 'CANVAS') return
  if (['w','a','s','d','q','e','+','=','-','_','arrowup','arrowdown','arrowleft','arrowright'].includes(k)) {
    e.preventDefault(); keys.add(k); markDirty()
  }
  if (k === 'r') camReset()
}
function onKeyUp(e) { keys.delete(e.key.toLowerCase()) }

// ─── Mouse / touch controls ───────────────────────────────────────────────────
function onPointerDown(e) {
  if (e.button === 0) {
    cam.panDragging = true; cam.panLastX = e.clientX; cam.panLastY = e.clientY
    cam.vPanX = 0; cam.vPanZ = 0
  } else if (e.button === 2) {
    cam.orbitDragging = true; cam.orbitLastX = e.clientX; cam.orbitLastY = e.clientY
    cam.vTheta = 0; cam.vPhi = 0
  }
}
function onPointerMove(e) {
  if (cam.panDragging) {
    const dx = e.clientX - cam.panLastX, dy = e.clientY - cam.panLastY
    const [wx, wz] = screenToWorldPan(dx, dy)
    cam.vPanX = wx; cam.vPanZ = wz; cam.targetX += wx; cam.targetZ += wz
    cam.panLastX = e.clientX; cam.panLastY = e.clientY; camApply()
  }
  if (cam.orbitDragging) {
    cam.vTheta = (e.clientX - cam.orbitLastX) * -0.008
    cam.vPhi   = (e.clientY - cam.orbitLastY) * -0.008
    cam.theta += cam.vTheta; cam.phi += cam.vPhi
    cam.orbitLastX = e.clientX; cam.orbitLastY = e.clientY; camApply()
  }
}
function onPointerUp(e) {
  if (e.button === 0) cam.panDragging = false
  if (e.button === 2) cam.orbitDragging = false
}
function onContextMenu(e) { e.preventDefault() }

function onWheel(e) {
  e.preventDefault()
  const delta = e.deltaY > 0 ? 1 : -1
  cam.vZoom  = delta * cam.radius * 0.04
  cam.radius = Math.min(cam.maxR, Math.max(cam.minR, cam.radius + delta * cam.radius * 0.08))
  camApply()
}

let _touches = [], _pinchDist = 0

function onTouchStart(e) {
  _touches = Array.from(e.touches)
  if (_touches.length === 1) {
    cam.panDragging = true
    cam.panLastX = _touches[0].clientX; cam.panLastY = _touches[0].clientY
    cam.vPanX = 0; cam.vPanZ = 0
  } else if (_touches.length === 2) {
    cam.panDragging = false
    _pinchDist = Math.hypot(
      _touches[0].clientX - _touches[1].clientX,
      _touches[0].clientY - _touches[1].clientY,
    )
  }
}
function onTouchMove(e) {
  e.preventDefault()
  _touches = Array.from(e.touches)
  if (_touches.length === 1 && cam.panDragging) {
    const dx = _touches[0].clientX - cam.panLastX
    const dy = _touches[0].clientY - cam.panLastY
    const [wx, wz] = screenToWorldPan(dx, dy)
    cam.vPanX = wx; cam.vPanZ = wz; cam.targetX += wx; cam.targetZ += wz
    cam.panLastX = _touches[0].clientX; cam.panLastY = _touches[0].clientY; camApply()
  } else if (_touches.length === 2) {
    const d = Math.hypot(
      _touches[0].clientX - _touches[1].clientX,
      _touches[0].clientY - _touches[1].clientY,
    )
    cam.radius = Math.min(cam.maxR, Math.max(cam.minR, cam.radius * (_pinchDist / d)))
    _pinchDist = d; camApply()
  }
}
function onTouchEnd() { cam.panDragging = false; cam.orbitDragging = false }

function attachEvents(el) {
  el.addEventListener('pointerdown', onPointerDown)
  el.addEventListener('pointermove', onPointerMove, { passive: true })
  el.addEventListener('pointerup', onPointerUp)
  el.addEventListener('pointercancel', onPointerUp)
  el.addEventListener('contextmenu', onContextMenu)
  el.addEventListener('wheel', onWheel, { passive: false })
  el.addEventListener('touchstart', onTouchStart, { passive: true })
  el.addEventListener('touchmove', onTouchMove, { passive: false })
  el.addEventListener('touchend', onTouchEnd, { passive: true })
  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('keyup', onKeyUp)
}
function detachEvents(el) {
  el.removeEventListener('pointerdown', onPointerDown)
  el.removeEventListener('pointermove', onPointerMove)
  el.removeEventListener('pointerup', onPointerUp)
  el.removeEventListener('pointercancel', onPointerUp)
  el.removeEventListener('contextmenu', onContextMenu)
  el.removeEventListener('wheel', onWheel)
  el.removeEventListener('touchstart', onTouchStart)
  el.removeEventListener('touchmove', onTouchMove)
  el.removeEventListener('touchend', onTouchEnd)
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('keyup', onKeyUp)
}

// ─── Resize ───────────────────────────────────────────────────────────────────
function onResize() {
  if (!canvasWrap.value || !camera || !renderer) return
  const w = Math.max(canvasWrap.value.clientWidth, 1)
  const h = Math.max(canvasWrap.value.clientHeight, 1)
  renderer.setSize(w, h, false)
  camera.aspect = w / h
  camera.updateProjectionMatrix()
  markDirty()
}

// ─── Lifecycle ────────────────────────────────────────────────────────────────
onMounted(() => {
  if (!canvasWrap.value) return
  buildShared()

  scene = new Scene()
  scene.background = new Color(C.skyDay)

  const span = Math.max(rowCount.value, colCount.value) * CELL
  camera = new PerspectiveCamera(50, 1, 0.1, 500)
  cam.radius = span * 1.55
  cam.minR   = span * 0.25
  cam.maxR   = span * 5.0
  camApply()

  renderer = new WebGLRenderer({ antialias: true })
  renderer.setPixelRatio(1)
  renderer.shadowMap.enabled = false
  canvasWrap.value.appendChild(renderer.domElement)

  ambientLight = new AmbientLight('#ffffff', 0.55)
  sunLight     = new DirectionalLight('#ffe8c0', 1.2)
  scene.add(ambientLight, sunLight)

  cellGroup = new Group()
  pathGroup = new Group()
  scene.add(cellGroup, pathGroup)

  buildCells()
  buildPath()
  scene.add(buildRover())
  updateStatusLight()

  const { x = 0, y = 0 } = props.roverPosition ?? {}
  const sp = toWorld(x, y, 0)
  roverCurrent.copy(sp); roverTarget.copy(sp); rover.root.position.copy(sp)

  applyLighting()
  onResize()

  attachEvents(canvasWrap.value)
  resizeObs = new ResizeObserver(onResize)
  resizeObs.observe(canvasWrap.value)

  lastTs = performance.now()
  markDirty()
})

onBeforeUnmount(() => {
  if (frameId) { cancelAnimationFrame(frameId); frameId = 0 }
  resizeObs?.disconnect()
  if (canvasWrap.value) detachEvents(canvasWrap.value)

  clearGroup(cellGroup)
  if (pathTubeMesh) { pathGroup.remove(pathTubeMesh); pathTubeMesh.geometry.dispose() }
  pathTubeMat?.dispose()

  if (rover.root) {
    rover.root.traverse((o) => { o.geometry?.dispose(); o.material?.dispose() })
    scene?.remove(rover.root)
  }

  disposeShared()
  renderer?.dispose()
  renderer?.forceContextLoss()
  if (renderer?.domElement?.parentNode === canvasWrap.value)
    canvasWrap.value.removeChild(renderer.domElement)

  scene = camera = renderer = null
})

// ─── Watchers ─────────────────────────────────────────────────────────────────
watch(matrix, () => buildCells(), { deep: true })
watch(() => props.minedCells,  () => buildCells(), { deep: true })
watch(() => props.pathPlan,    () => buildPath(),   { deep: true })
watch(() => props.roverPosition, () => setRoverTarget(), { deep: true })
watch(() => props.timeOfDay,   () => applyLighting())
watch(() => props.roverStatus, () => updateStatusLight())
</script>

<template>
  <div ref="canvasWrap" class="canvas-wrap">
    <div class="hint">
      <!-- Desktop hint -->
      <span class="hint--desktop">
        🖱 Left-drag: pan &nbsp;|&nbsp; Right-drag: rotate &nbsp;|&nbsp; Scroll: zoom
      </span>
      <span class="hint--desktop">
        ⌨ WASD/↑↓←→: pan &nbsp;|&nbsp; Q/E: rotate &nbsp;|&nbsp; +/−: zoom &nbsp;|&nbsp; R: reset
      </span>
      <!-- Mobile/tablet hint -->
      <span class="hint--mobile">
        👆 Drag: pan &nbsp;|&nbsp; Pinch: zoom
      </span>
    </div>
  </div>
</template>

<style src="../styles/main.css"></style>
