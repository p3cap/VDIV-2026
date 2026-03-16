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
 *
 * Path fix:
 *  - Tube rendered at y:0.05 (flush on ground) with correct XZ centering
 *  - CatmullRom tension:0 + no endpoint duplication (no fold-back artefact)
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
} from 'three'

// ─── Props ────────────────────────────────────────────────────────────────────
const props = defineProps({
	mapMatrix: { type: Array, required: true },
	roverPosition: { type: Object, required: true },
	pathPlan: { type: Array, default: () => [] },
	minedCells: { type: Array, default: () => [] },
	roverStatus: { type: String, default: 'idle' },
	roverSpeed: { type: Number, default: 1 },
	timeOfDay: { type: Number, default: 12 },
	dayHrs: { type: Number, default: 16 },
	nightHrs: { type: Number, default: 8 },
})

// ─── Scene constants ──────────────────────────────────────────────────────────
const CELL = 2.2
const HALF = CELL / 2

const C = Object.freeze({
	skyDay: '#1a0e05',
	skyNight: '#06040a',
	ground: '#c47a3a',
	barrier: '#3a1e0a',
	gold: '#f0c040',
	ice: '#a0d0f0',
	green: '#30d070',
	start: '#ff6b35',
	path: '#44d1ff',
	mined: '#120600',
	rover: '#dce3e8',
	roverAccent: '#ff6b35',
	solar: '#1a3a6e',
	wheel: '#1c1c1c',
	statusColor: {
		mine: '#ffaa00',
		move: '#44d1ff',
		charge: '#ffd700',
		standby: '#334455',
		idle: '#ff6b35',
	},
})

// ─── Derived computeds ────────────────────────────────────────────────────────
const matrix = computed(() => (Array.isArray(props.mapMatrix) ? props.mapMatrix : []))
const rowCount = computed(() => matrix.value.length || 1)
const colCount = computed(() => matrix.value[0]?.length || 1)
const cycle = computed(() => props.dayHrs + props.nightHrs)
const isDay = computed(() => props.timeOfDay % cycle.value < props.dayHrs)
const dayFrac = computed(() => (props.timeOfDay % cycle.value) / cycle.value)
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
	gBarrier: null,
	gGold: null,
	gIceCone: null,
	gGreenStem: null,
	gGreenCap: null,
	gPole: null,
	gFlag: null,
	gPit: null,
	mTile: null,
	mBarrier: null,
	mGold: null,
	mIce: null,
	mGreen: null,
	mGreenDark: null,
	mStart: null,
	mPole: null,
	mMined: null,
}

let pathTubeMesh = null
let pathTubeMat = null
let roverHeadingTarget = 0
let roverHeadingCurrent = 0

function buildShared() {
	S.gTile = new PlaneGeometry(CELL - 0.1, CELL - 0.1)
	S.gBarrier = new BoxGeometry(CELL * 0.8, 1.0, CELL * 0.8)
	S.gGold = new OctahedronGeometry(0.26)
	S.gIceCone = new ConeGeometry(0.15, 0.65, 5)
	S.gGreenStem = new CylinderGeometry(0.07, 0.1, 0.36, 6)
	S.gGreenCap = new SphereGeometry(0.28, 6, 5)
	S.gPole = new CylinderGeometry(0.03, 0.03, 0.88, 5)
	S.gFlag = new BoxGeometry(0.26, 0.16, 0.02)
	S.gPit = new CylinderGeometry(CELL * 0.34, CELL * 0.24, 0.22, 7)

	S.mTile = new MeshLambertMaterial({ color: C.ground })
	S.mBarrier = new MeshLambertMaterial({ color: C.barrier })
	S.mGold = new MeshLambertMaterial({
		color: C.gold,
		emissive: new Color(C.gold),
		emissiveIntensity: 0.15,
	})
	S.mIce = new MeshLambertMaterial({
		color: C.ice,
		emissive: new Color(C.ice),
		emissiveIntensity: 0.1,
		transparent: true,
		opacity: 0.88,
	})
	S.mGreen = new MeshLambertMaterial({
		color: C.green,
		emissive: new Color(C.green),
		emissiveIntensity: 0.18,
	})
	S.mGreenDark = new MeshLambertMaterial({ color: '#1a7a30' })
	S.mStart = new MeshLambertMaterial({
		color: C.start,
		emissive: new Color(C.start),
		emissiveIntensity: 0.2,
	})
	S.mPole = new MeshLambertMaterial({ color: '#888888' })
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

// ─── Cell factories ───────────────────────────────────────────────────────────
function makeTile(gx, gy) {
	const m = new Mesh(S.gTile, S.mTile)
	m.rotation.x = -Math.PI / 2
	m.position.copy(toWorld(gx, gy, 0))
	return m
}
function makeBarrier(gx, gy) {
	const m = new Mesh(S.gBarrier, S.mBarrier)
	m.position.copy(toWorld(gx, gy, 0.5))
	return m
}
function makeGold(gx, gy) {
	const g = new Group()
	const c1 = new Mesh(S.gGold, S.mGold)
	c1.position.set(-0.2, 0.34, -0.14)
	c1.rotation.set(0.4, 0.7, 0)
	c1.scale.y = 1.5
	const c2 = new Mesh(S.gGold, S.mGold)
	c2.position.set(0.18, 0.27, 0.16)
	c2.rotation.set(-0.3, 1.2, 0.2)
	c2.scale.y = 1.2
	g.add(c1, c2)
	g.position.copy(toWorld(gx, gy, 0))
	return g
}
function makeIce(gx, gy) {
	const g = new Group()
	const s1 = new Mesh(S.gIceCone, S.mIce)
	s1.position.set(-0.18, 0.33, 0.1)
	s1.rotation.z = -0.2
	const s2 = new Mesh(S.gIceCone, S.mIce)
	s2.position.set(0.18, 0.27, -0.14)
	s2.rotation.z = 0.25
	g.add(s1, s2)
	g.position.copy(toWorld(gx, gy, 0))
	return g
}
function makeGreen(gx, gy) {
	const g = new Group()
	const stem = new Mesh(S.gGreenStem, S.mGreenDark)
	stem.position.y = 0.18
	const cap = new Mesh(S.gGreenCap, S.mGreen)
	cap.position.y = 0.5
	cap.scale.y = 0.6
	g.add(stem, cap)
	g.position.copy(toWorld(gx, gy, 0))
	return g
}
function makeStart(gx, gy) {
	const g = new Group()
	const pole = new Mesh(S.gPole, S.mPole)
	pole.position.y = 0.44
	const flag = new Mesh(S.gFlag, S.mStart)
	flag.position.set(0.13, 0.86, 0)
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
	rover.solarPanel = null
	rover.drillGroup = null
	const root = new Group()
	const sm = (col, o = {}) =>
		new MeshStandardMaterial({ color: col, roughness: 0.55, metalness: 0.2, ...o })

	const chassis = new Mesh(new BoxGeometry(1.0, 0.18, 1.3), sm(C.rover, { roughness: 0.5 }))
	chassis.position.y = 0.42
	root.add(chassis)
	const body = new Mesh(new BoxGeometry(0.8, 0.3, 0.86), sm(C.rover))
	body.position.y = 0.64
	root.add(body)

	const panel = new Mesh(
		new BoxGeometry(1.42, 0.04, 0.68),
		new MeshStandardMaterial({
			color: C.solar,
			roughness: 0.3,
			metalness: 0.7,
			emissive: new Color('#001a55'),
			emissiveIntensity: 0.3,
		}),
	)
	panel.position.y = 0.83
	rover.solarPanel = panel
	root.add(panel)

	const tyreGeo = new CylinderGeometry(0.21, 0.21, 0.14, 10)
	const hubGeo = new CylinderGeometry(0.07, 0.07, 0.15, 7)
	const tyreMat = new MeshStandardMaterial({ color: C.wheel, roughness: 0.95 })
	const hubMat = new MeshStandardMaterial({ color: '#777777', roughness: 0.5, metalness: 0.6 })
	for (const [wx, wz] of [
		[-0.57, -0.46],
		[-0.57, 0],
		[-0.57, 0.46],
		[0.57, -0.46],
		[0.57, 0],
		[0.57, 0.46],
	]) {
		const wg = new Group()
		const tyr = new Mesh(tyreGeo, tyreMat)
		tyr.rotation.z = Math.PI / 2
		const hub = new Mesh(hubGeo, hubMat)
		hub.rotation.z = Math.PI / 2
		wg.add(tyr, hub)
		wg.position.set(wx, 0.22, wz)
		rover.wheels.push(wg)
		root.add(wg)
	}

	const mast = new Mesh(new CylinderGeometry(0.03, 0.03, 0.52, 6), sm('#aaaaaa'))
	mast.position.set(0, 1.0, -0.3)
	root.add(mast)
	const head = new Mesh(new BoxGeometry(0.13, 0.11, 0.11), sm('#222222', { metalness: 0.5 }))
	head.position.set(0, 1.3, -0.3)
	root.add(head)

	rover.statusLight = new Mesh(
		new SphereGeometry(0.07, 6, 5),
		new MeshStandardMaterial({
			color: C.roverAccent,
			emissive: new Color(C.roverAccent),
			emissiveIntensity: 1.2,
		}),
	)
	rover.statusLight.position.set(0, 0.73, -0.51)
	root.add(rover.statusLight)

	rover.drillGroup = new Group()
	rover.drillGroup.visible = false
	const arm = new Mesh(new CylinderGeometry(0.03, 0.03, 0.46, 5), sm('#888888'))
	arm.rotation.z = Math.PI / 2
	arm.position.set(0.33, 0.3, 0.5)
	const bit = new Mesh(new ConeGeometry(0.07, 0.18, 6), sm('#555555', { metalness: 0.7 }))
	bit.rotation.z = -Math.PI / 2
	bit.position.set(0.58, 0.3, 0.5)
	rover.drillGroup.add(arm, bit)
	root.add(rover.drillGroup)

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
			if (minedSet.has(`${gx},${gy}`)) {
				cellGroup.add(makeMinedPit(gx, gy))
				continue
			}
			switch (row[gx]) {
				case '#':
					cellGroup.add(makeBarrier(gx, gy))
					break
				case 'Y':
					cellGroup.add(makeGold(gx, gy))
					break
				case 'B':
					cellGroup.add(makeIce(gx, gy))
					break
				case 'G':
					cellGroup.add(makeGreen(gx, gy))
					break
				case 'S':
					cellGroup.add(makeStart(gx, gy))
					break
			}
		}
	}
	markDirty()
}

function buildPath() {
	if (pathTubeMesh) {
		pathGroup.remove(pathTubeMesh)
		pathTubeMesh.geometry.dispose()
		pathTubeMesh = null
	}
	pathTubeMat?.dispose()
	pathTubeMat = null

	const plan = props.pathPlan ?? []
	if (plan.length < 2) {
		markDirty()
		return
	}

	// Deduplicate consecutive identical cells, place just above the ground
	const pts = []
	let prevKey = null
	for (const p of plan) {
		if (typeof p.x !== 'number' || typeof p.y !== 'number') continue
		const k = `${p.x},${p.y}`
		if (k === prevKey) continue
		prevKey = k
		pts.push(toWorld(p.x, p.y, 0.05)) // y=0.05 → flush on ground plane
	}
	if (pts.length < 2) {
		markDirty()
		return
	}

	// tension:0 = straight lines through every waypoint, no fold-back
	const curve = new CatmullRomCurve3(pts, false, 'catmullrom', 0)

	pathTubeMat = new MeshLambertMaterial({
		color: C.path,
		emissive: new Color(C.path),
		emissiveIntensity: 0.65,
		transparent: true,
		opacity: 0.85,
	})
	pathTubeMesh = new Mesh(
		new TubeGeometry(curve, Math.max(pts.length * 4, 8), 0.07, 6, false),
		pathTubeMat,
	)
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
		rover.solarPanel.rotation.z = isDay.value
			? (Math.PI / 2 - dayFrac.value * Math.PI) * 0.35
			: 0
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

const roverTarget = new Vector3()
const roverCurrent = new Vector3()

function renderLoop(ts) {
	frameId = 0
	if (!renderer || !scene || !camera) return
	const dt = Math.min((ts - lastTs) / 1000, 0.05)
	lastTs = ts
	const t = ts * 0.001
	let more = false

	// ── Camera inertia ──────────────────────────────────────────────────────────
	// Pan inertia
	if (!cam.panDragging && (Math.abs(cam.vPanX) > 0.0001 || Math.abs(cam.vPanZ) > 0.0001)) {
		cam.targetX += cam.vPanX
		cam.targetZ += cam.vPanZ
		cam.vPanX *= 0.85
		cam.vPanZ *= 0.85
		_camApplyNoMark()
		more = true
	}
	// Orbit inertia
	if (!cam.orbitDragging && (Math.abs(cam.vTheta) > 0.0001 || Math.abs(cam.vPhi) > 0.0001)) {
		cam.theta += cam.vTheta
		cam.phi += cam.vPhi
		cam.vTheta *= 0.87
		cam.vPhi *= 0.87
		cam.phi = Math.max(0.12, Math.min(Math.PI * 0.48, cam.phi))
		_camApplyNoMark()
		more = true
	}
	// Zoom inertia
	if (Math.abs(cam.vZoom) > 0.001) {
		cam.radius = Math.min(cam.maxR, Math.max(cam.minR, cam.radius + cam.vZoom))
		cam.vZoom *= 0.82
		_camApplyNoMark()
		more = true
	}

	// ── Keyboard input ─────────────────────────────────────────────────────────
	if (keys.size > 0) {
		const panSpd = cam.radius * 0.018
		const rotSpd = 0.03
		const zoomSpd = cam.radius * 0.04
		const sinA = Math.sin(cam.theta)
		const cosA = Math.cos(cam.theta)

		// Pan forward/back along camera facing direction (XZ projected)
		if (keys.has('w') || keys.has('arrowup')) {
			cam.targetX -= sinA * panSpd
			cam.targetZ -= cosA * panSpd
		}
		if (keys.has('s') || keys.has('arrowdown')) {
			cam.targetX += sinA * panSpd
			cam.targetZ += cosA * panSpd
		}
		// Pan left/right (perpendicular)
		if (keys.has('a') || keys.has('arrowleft')) {
			cam.targetX -= cosA * panSpd
			cam.targetZ += sinA * panSpd
		}
		if (keys.has('d') || keys.has('arrowright')) {
			cam.targetX += cosA * panSpd
			cam.targetZ -= sinA * panSpd
		}
		// Rotate
		if (keys.has('q')) {
			cam.theta -= rotSpd
		}
		if (keys.has('e')) {
			cam.theta += rotSpd
		}
		// Zoom
		if (keys.has('+') || keys.has('=')) {
			cam.radius = Math.max(cam.minR, cam.radius - zoomSpd)
		}
		if (keys.has('-') || keys.has('_')) {
			cam.radius = Math.min(cam.maxR, cam.radius + zoomSpd)
		}

		_camApplyNoMark()
		more = true
	}

	// ── Rover lerp ─────────────────────────────────────────────────────────────
	if (rover.root && roverCurrent.distanceTo(roverTarget) > 0.002) {
		roverCurrent.lerp(roverTarget, 1 - Math.exp(-(isMoving.value ? 5 : 12) * dt))
		rover.root.position.x = roverCurrent.x
		rover.root.position.z = roverCurrent.z
		more = true
	}

	// Rover heading lerp
	if (rover.root) {
		let diff = roverHeadingTarget - roverHeadingCurrent
		while (diff > Math.PI) diff -= Math.PI * 2
		while (diff < -Math.PI) diff += Math.PI * 2
		if (Math.abs(diff) > 0.002) {
			roverHeadingCurrent += diff * (1 - Math.exp(-10 * dt))
			rover.root.rotation.y = roverHeadingCurrent
			more = true
		}
	}

	// Wheel roll
	if (isMoving.value && rover.wheels.length) {
		const roll = props.roverSpeed * 3.5 * dt
		for (const wg of rover.wheels) wg.rotation.x += roll
		more = true
	}

	// Body bob
	if (rover.root) {
		if (isMoving.value) {
			rover.root.position.y = Math.sin(t * 7) * 0.026
			rover.root.rotation.z = Math.sin(t * 3.5) * 0.016
			more = true
		} else if (
			Math.abs(rover.root.position.y) > 0.001 ||
			Math.abs(rover.root.rotation.z) > 0.001
		) {
			rover.root.position.y *= Math.exp(-8 * dt)
			rover.root.rotation.z *= Math.exp(-8 * dt)
			more = true
		}
	}

	// Drill
	if (rover.drillGroup) {
		if (rover.drillGroup.visible !== isMining.value) {
			rover.drillGroup.visible = isMining.value
			more = true
		}
		if (isMining.value) {
			rover.drillGroup.rotation.x += 7 * dt
			more = true
		}
	}

	renderer.render(scene, camera)
	if (more) frameId = requestAnimationFrame(renderLoop)
}

// ─── Combined camera state ────────────────────────────────────────────────────
// Supports both pan (XZ translate) and orbit (theta/phi rotation) simultaneously.
const cam = {
	// Look-at / target point
	targetX: 0,
	targetZ: 0,
	// Spherical coords relative to target
	theta: 0, // azimuth (Y rotation)
	phi: 0.95, // elevation from top (~54°)
	radius: 10,
	minR: 2,
	maxR: 100,
	// Pan drag state
	panDragging: false,
	panLastX: 0,
	panLastY: 0,
	vPanX: 0,
	vPanZ: 0,
	// Orbit drag state
	orbitDragging: false,
	orbitLastX: 0,
	orbitLastY: 0,
	vTheta: 0,
	vPhi: 0,
	// Zoom inertia
	vZoom: 0,
}

function _camApplyNoMark() {
	if (!camera) return
	cam.phi = Math.max(0.12, Math.min(Math.PI * 0.48, cam.phi))
	const sinP = Math.sin(cam.phi)
	const cosP = Math.cos(cam.phi)
	const sinT = Math.sin(cam.theta)
	const cosT = Math.cos(cam.theta)
	camera.position.set(
		cam.targetX + cam.radius * sinP * sinT,
		cam.radius * cosP,
		cam.targetZ + cam.radius * sinP * cosT,
	)
	camera.lookAt(cam.targetX, 0, cam.targetZ)
}
function camApply() {
	_camApplyNoMark()
	markDirty()
}

// Reset to default view
function camReset() {
	cam.targetX = 0
	cam.targetZ = 0
	cam.theta = 0
	cam.phi = 0.95
	cam.radius = cam.minR * 2.5
	cam.vPanX = 0
	cam.vPanZ = 0
	cam.vTheta = 0
	cam.vPhi = 0
	cam.vZoom = 0
	camApply()
}

// Map screen dx/dy → world XZ pan delta (accounts for current azimuth)
function screenToWorldPan(dx, dy) {
	if (!camera) return [0, 0]
	const fwd = new Vector3()
	camera.getWorldDirection(fwd)
	const right = new Vector3().crossVectors(fwd, new Vector3(0, 1, 0)).normalize()
	fwd.y = 0
	fwd.normalize()
	const scale = cam.radius * 0.003
	return [(-dx * right.x + dy * fwd.x) * scale, (-dx * right.z + dy * fwd.z) * scale]
}

// ─── Keyboard state ───────────────────────────────────────────────────────────
const keys = new Set()
function onKeyDown(e) {
	const k = e.key.toLowerCase()
	// Don't steal focus from inputs etc.
	if (e.target !== document.body && e.target.tagName !== 'CANVAS') return
	if (
		[
			'w',
			'a',
			's',
			'd',
			'q',
			'e',
			'+',
			'=',
			'-',
			'_',
			'arrowup',
			'arrowdown',
			'arrowleft',
			'arrowright',
		].includes(k)
	) {
		e.preventDefault()
		keys.add(k)
		markDirty()
	}
	if (k === 'r') camReset()
}
function onKeyUp(e) {
	keys.delete(e.key.toLowerCase())
}

// ─── Mouse / touch controls ───────────────────────────────────────────────────
// Left-drag  → pan
// Right-drag → orbit
// Wheel      → zoom
// Touch 1-finger → pan
// Touch 2-finger → pinch-zoom + two-finger pan

function onPointerDown(e) {
	if (e.button === 0) {
		// Left — pan
		cam.panDragging = true
		cam.panLastX = e.clientX
		cam.panLastY = e.clientY
		cam.vPanX = 0
		cam.vPanZ = 0
	} else if (e.button === 2) {
		// Right — orbit
		cam.orbitDragging = true
		cam.orbitLastX = e.clientX
		cam.orbitLastY = e.clientY
		cam.vTheta = 0
		cam.vPhi = 0
	}
}
function onPointerMove(e) {
	if (cam.panDragging) {
		const dx = e.clientX - cam.panLastX
		const dy = e.clientY - cam.panLastY
		const [wx, wz] = screenToWorldPan(dx, dy)
		cam.vPanX = wx
		cam.vPanZ = wz
		cam.targetX += wx
		cam.targetZ += wz
		cam.panLastX = e.clientX
		cam.panLastY = e.clientY
		camApply()
	}
	if (cam.orbitDragging) {
		cam.vTheta = (e.clientX - cam.orbitLastX) * -0.008
		cam.vPhi = (e.clientY - cam.orbitLastY) * -0.008
		cam.theta += cam.vTheta
		cam.phi += cam.vPhi
		cam.orbitLastX = e.clientX
		cam.orbitLastY = e.clientY
		camApply()
	}
}
function onPointerUp(e) {
	if (e.button === 0) cam.panDragging = false
	if (e.button === 2) cam.orbitDragging = false
}
function onContextMenu(e) {
	e.preventDefault()
}

function onWheel(e) {
	e.preventDefault()
	const delta = e.deltaY > 0 ? 1 : -1
	cam.vZoom = delta * cam.radius * 0.04
	cam.radius = Math.min(cam.maxR, Math.max(cam.minR, cam.radius + delta * cam.radius * 0.08))
	camApply()
}

// Touch
let _touches = []
let _pinchDist = 0

function onTouchStart(e) {
	_touches = Array.from(e.touches)
	if (_touches.length === 1) {
		cam.panDragging = true
		cam.panLastX = _touches[0].clientX
		cam.panLastY = _touches[0].clientY
		cam.vPanX = 0
		cam.vPanZ = 0
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
		cam.vPanX = wx
		cam.vPanZ = wz
		cam.targetX += wx
		cam.targetZ += wz
		cam.panLastX = _touches[0].clientX
		cam.panLastY = _touches[0].clientY
		camApply()
	} else if (_touches.length === 2) {
		const d = Math.hypot(
			_touches[0].clientX - _touches[1].clientX,
			_touches[0].clientY - _touches[1].clientY,
		)
		cam.radius = Math.min(cam.maxR, Math.max(cam.minR, cam.radius * (_pinchDist / d)))
		_pinchDist = d
		camApply()
	}
}
function onTouchEnd() {
	cam.panDragging = false
	cam.orbitDragging = false
}

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
	cam.minR = span * 0.25
	cam.maxR = span * 5.0
	camApply()

	renderer = new WebGLRenderer({ antialias: true })
	renderer.setPixelRatio(1)
	renderer.shadowMap.enabled = false
	canvasWrap.value.appendChild(renderer.domElement)

	ambientLight = new AmbientLight('#ffffff', 0.55)
	sunLight = new DirectionalLight('#ffe8c0', 1.2)
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
	roverCurrent.copy(sp)
	roverTarget.copy(sp)
	rover.root.position.copy(sp)

	applyLighting()
	onResize()

	attachEvents(canvasWrap.value)
	resizeObs = new ResizeObserver(onResize)
	resizeObs.observe(canvasWrap.value)

	lastTs = performance.now()
	markDirty()
})

onBeforeUnmount(() => {
	if (frameId) {
		cancelAnimationFrame(frameId)
		frameId = 0
	}
	resizeObs?.disconnect()
	if (canvasWrap.value) detachEvents(canvasWrap.value)

	clearGroup(cellGroup)
	if (pathTubeMesh) {
		pathGroup.remove(pathTubeMesh)
		pathTubeMesh.geometry.dispose()
	}
	pathTubeMat?.dispose()

	if (rover.root) {
		rover.root.traverse((o) => {
			o.geometry?.dispose()
			o.material?.dispose()
		})
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
watch(
	() => props.minedCells,
	() => buildCells(),
	{ deep: true },
)
watch(
	() => props.pathPlan,
	() => buildPath(),
	{ deep: true },
)
watch(
	() => props.roverPosition,
	() => setRoverTarget(),
	{ deep: true },
)
watch(
	() => props.timeOfDay,
	() => applyLighting(),
)
watch(
	() => props.roverStatus,
	() => updateStatusLight(),
)
</script>

<template>
	<div ref="canvasWrap" class="canvas-wrap">
		<div class="hint">
			<span
				>🖱 Left-drag: pan &nbsp;|&nbsp; Right-drag: rotate &nbsp;|&nbsp; Scroll: zoom</span
			>
			<span
				>⌨ WASD/↑↓←→: pan &nbsp;|&nbsp; Q/E: rotate &nbsp;|&nbsp; +/−: zoom &nbsp;|&nbsp; R:
				reset</span
			>
		</div>
	</div>
</template>

<style src="../styles/main.css"></style>
