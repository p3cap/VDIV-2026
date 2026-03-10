<template>
  <div class="dashboard">
    <div class="bg-grid" />

    <!-- ── Header ── -->
    <header class="dash-header">
      <div class="header-left">
        <span class="logo-hex">⬡</span>
        <span class="logo-text">roverize</span>
      </div>
      <div class="header-center">
        <div class="time-display">
          <span class="time-label">MISSION TIME</span>
          <span class="time-value">T+{{ formatHrs(dashboard?.elapsed_hrs) }}</span>
        </div>
        <div class="time-display">
          <span class="time-label">TIME OF DAY</span>
          <span class="time-value">{{ formatTOD(dashboard?.time_of_day) }}</span>
        </div>
      </div>
      <div class="conn-badge" :class="{ connected: store.isConnected }">
        <span class="conn-dot" />
        {{ store.isConnected ? 'LIVE' : 'OFFLINE' }}
      </div>
    </header>

    <!-- ── Grid ── -->
    <main class="dash-grid">

      <!-- Status card -->
      <div class="card status-card" :class="statusAccent">
        <div class="status-icon-wrap">
          <span class="status-big-icon">{{ statusIcon }}</span>
          <span class="ring r1" />
          <span class="ring r2" />
        </div>
        <div class="status-info">
          <span class="s-label">ROVER STATUS</span>
          <span class="s-text">{{ dashboard?.rover_status?.toUpperCase() ?? '—' }}</span>
          <span class="s-sub">x:{{ dashboard?.rover_position?.x ?? 0 }} · y:{{ dashboard?.rover_position?.y ?? 0 }}</span>
        </div>
        <div class="status-stats">
          <div class="stat-item">
            <span class="stat-lbl">SPEED</span>
            <span class="stat-val">{{ dashboard?.rover_speed ?? '—' }}<em>m/s</em></span>
          </div>
          <div class="stat-item">
            <span class="stat-lbl">DISTANCE</span>
            <span class="stat-val">{{ dashboard?.rover_distance_travelled ?? '—' }}<em>m</em></span>
          </div>
        </div>
      </div>

      <!-- Battery card -->
      <div class="card battery-card">
        <div class="card-header">
          <span class="card-title">BATTERY</span>
          <span class="card-value" :style="{ color: batteryColor }">{{ dashboard?.rover_battery?.toFixed(1) ?? '—' }}%</span>
        </div>
        <div class="battery-arc-wrap">
          <svg viewBox="0 0 200 120" class="battery-svg">
            <path d="M 20 110 A 90 90 0 0 1 180 110" fill="none" stroke="#1e293b" stroke-width="14" stroke-linecap="round"/>
            <path d="M 20 110 A 90 90 0 0 1 180 110" fill="none"
              :stroke="batteryColor"
              stroke-width="14"
              stroke-linecap="round"
              :stroke-dasharray="batteryDash"
              stroke-dashoffset="0"
              style="transition: stroke-dasharray 0.6s ease, stroke 0.6s ease"
            />
            <text x="100" y="98" text-anchor="middle" fill="#f1f5f9" font-size="28" font-family="Orbitron,sans-serif" font-weight="700">{{ Math.round(dashboard?.rover_battery ?? 0) }}</text>
            <text x="100" y="114" text-anchor="middle" fill="#475569" font-size="11" font-family="JetBrains Mono,monospace">PERCENT</text>
          </svg>
        </div>
      </div>

      <!-- Distance line chart -->
      <div class="card chart-card">
        <div class="card-header">
          <span class="card-title">DISTANCE OVER TIME</span>
          <div class="legend-row">
            <span class="leg-dot" style="background:#00ffc8" /><span>Distance (m)</span>
          </div>
        </div>
        <div ref="distRef" class="uplot-wrap" />
      </div>

      <!-- Energy line chart -->
      <div class="card chart-card">
        <div class="card-header">
          <span class="card-title">ENERGY BALANCE</span>
          <div class="legend-row">
            <span class="leg-dot" style="background:#4ade80" /><span>Produce</span>
            <span class="leg-dot" style="background:#ff6b35; margin-left:10px" /><span>Consume</span>
          </div>
        </div>
        <div ref="energyRef" class="uplot-wrap" />
      </div>

      <!-- Storage pie (SVG, no lib needed) -->
      <div class="card storage-card">
        <div class="card-header">
          <span class="card-title">CARGO STORAGE</span>
        </div>
        <div class="pie-wrap">
          <svg viewBox="-1 -1 2 2" class="pie-svg" style="transform:rotate(-90deg)">
            <circle v-for="(seg, i) in pieSegments" :key="i"
              r="0.5" cx="0" cy="0"
              fill="transparent"
              :stroke="seg.color"
              stroke-width="1"
              :stroke-dasharray="`${seg.dash} ${1 - seg.dash}`"
              :stroke-dashoffset="-seg.offset"
              style="transition: stroke-dasharray 0.5s ease"
            />
          </svg>
          <div class="pie-legend">
            <div v-for="(seg, i) in pieSegments" :key="i" class="pie-leg-row">
              <span class="pie-leg-dot" :style="{ background: seg.color }" />
              <span class="pie-leg-label">{{ seg.name }}</span>
              <span class="pie-leg-val">{{ seg.value.toLocaleString() }}</span>
            </div>
          </div>
        </div>
      </div>

 

    </main>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useLiveWsStore } from '@/stores/liveWs'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'

const store     = useLiveWsStore()
const dashboard = computed(() => store.dashboard)

// ── DOM refs ──────────────────────────────────────────────────────────────────
const distRef    = ref(null)
const energyRef  = ref(null)
const scatterRef = ref(null)

let uDist   = null
let uEnergy = null

// ── History buffers ───────────────────────────────────────────────────────────
const MAX = 80
const hTime = []   // elapsed_hrs
const hDist = []   // rover_distance_travelled
const hTick = []   // tick index
const hProd = []   // energy produce
const hCons = []   // energy consume
let tick = 0

// ── Helpers ───────────────────────────────────────────────────────────────────
const formatHrs = (h) => {
  if (h == null) return '—'
  const hh = Math.floor(h), mm = Math.round((h - hh) * 60)
  return `${String(hh).padStart(3, '0')}h ${String(mm).padStart(2, '0')}m`
}
const formatTOD = (t) => {
  if (t == null) return '—'
  const hh = Math.floor(t), mm = Math.round((t - hh) * 60)
  return `${String(hh).padStart(2, '0')}:${String(mm).padStart(2, '0')}`
}

const statusAccent = computed(() => {
  const s = dashboard.value?.rover_status
  return s === 'mine' ? 'accent-orange' : s === 'move' ? 'accent-cyan' : 'accent-gray'
})
const statusIcon = computed(() => {
  const s = dashboard.value?.rover_status
  return s === 'mine' ? '⛏' : s === 'move' ? '🚀' : '💤'
})
const batteryColor = computed(() => {
  const b = dashboard.value?.rover_battery ?? 100
  return b > 60 ? '#4ade80' : b > 25 ? '#f59e0b' : '#f87171'
})

// Arc length for battery gauge: full arc perimeter = π * r = π * 90 ≈ 282.7
// We map 0–100% → 0–282.7 of that half-circle
const ARC = Math.PI * 90
const batteryDash = computed(() => {
  const pct = (dashboard.value?.rover_battery ?? 0) / 100
  const on = pct * ARC
  return `${on} ${ARC - on}`
})

// ── Pie segments ──────────────────────────────────────────────────────────────
const PIE_COLORS = { B: '#38bdf8', Y: '#f59e0b', G: '#4ade80' }
const pieSegments = computed(() => {
  const s = dashboard.value?.rover_storage ?? { B: 0, Y: 0, G: 0 }
  const total = Object.values(s).reduce((a, b) => a + b, 0) || 1
  const circ = Math.PI * 1   // circumference of r=0.5 circle = 2π*0.5 = π
  let offset = 0
  return Object.entries(s).map(([name, value]) => {
    const frac = value / total
    const dash = frac * circ
    const seg  = { name, value, color: PIE_COLORS[name] ?? '#64748b', dash, offset }
    offset += dash
    return seg
  })
})

// ── uPlot shared opts builder ─────────────────────────────────────────────────
function makePlotOpts(el, series, yLabel = '') {
  const w = el.clientWidth  || 300
  const h = el.clientHeight || 160

  return {
    width:  w,
    height: h,
    cursor: { show: false },
    select: { show: false },
    legend: { show: false },
    scales: { x: { time: false }, y: {} },
    axes: [
      {
        stroke: '#334155',
        ticks:  { stroke: '#1e293b', width: 1 },
        grid:   { stroke: '#1e293b', width: 1 },
        values: (u, vals) => vals.map(v => v == null ? '' : String(+v.toFixed(1))),
        font:   '10px JetBrains Mono',
      },
      {
        stroke: '#334155',
        ticks:  { stroke: '#1e293b', width: 1 },
        grid:   { stroke: '#ffffff0d', width: 1 },
        label:  yLabel,
        labelFont: '10px JetBrains Mono',
        font:   '10px JetBrains Mono',
        values: (u, vals) => vals.map(v => v == null ? '' : String(+v.toFixed(1))),
      },
    ],
    series,
  }
}

// ── Init distance chart ───────────────────────────────────────────────────────
function initDist() {
  if (!distRef.value || uDist) return
  const series = [
    {},
    {
      label:  'Distance',
      stroke: '#00ffc8',
      width:  2,
      fill:   'rgba(0,255,200,0.06)',
    },
  ]
  const opts = makePlotOpts(distRef.value, series, 'm')
  const data = [
    Float64Array.from(hTime),
    Float64Array.from(hDist),
  ]
  uDist = new uPlot(opts, data, distRef.value)
}

// ── Init energy chart ─────────────────────────────────────────────────────────
function initEnergy() {
  if (!energyRef.value || uEnergy) return
  const series = [
    {},
    {
      label:  'Produce',
      stroke: '#4ade80',
      width:  2,
      fill:   'rgba(74,222,128,0.06)',
    },
    {
      label:  'Consume',
      stroke: '#ff6b35',
      width:  2,
      fill:   'rgba(255,107,53,0.06)',
    },
  ]
  const opts = makePlotOpts(energyRef.value, series, 'kW')
  const data = [
    Float64Array.from(hTick),
    Float64Array.from(hProd),
    Float64Array.from(hCons),
  ]
  uEnergy = new uPlot(opts, data, energyRef.value)
}

// ── Update line charts ────────────────────────────────────────────────────────
function updateDist() {
  if (!uDist) return
  uDist.setData([
    Float64Array.from(hTime),
    Float64Array.from(hDist),
  ])
}
function updateEnergy() {
  if (!uEnergy) return
  uEnergy.setData([
    Float64Array.from(hTick),
    Float64Array.from(hProd),
    Float64Array.from(hCons),
  ])
}

// ── Scatter canvas ────────────────────────────────────────────────────────────
function drawScatter() {
  const canvas = scatterRef.value
  if (!canvas) return

  const dpr = window.devicePixelRatio || 1
  const W = canvas.offsetWidth  || 300
  const H = canvas.offsetHeight || 200
  canvas.width  = W * dpr
  canvas.height = H * dpr
  const ctx = canvas.getContext('2d')
  ctx.scale(dpr, dpr)

  ctx.clearRect(0, 0, W, H)
  ctx.fillStyle = '#060c14'
  ctx.fillRect(0, 0, W, H)

  const mined = store.mined ?? []
  const pos   = dashboard.value?.rover_position

  // Determine bounds
  const allX = [...mined.map(p => p.x), pos?.x ?? 0]
  const allY = [...mined.map(p => p.y), pos?.y ?? 0]
  const minX = Math.min(...allX) - 1
  const maxX = Math.max(...allX) + 1
  const minY = Math.min(...allY) - 1
  const maxY = Math.max(...allY) + 1
  const pad  = 28

  const toSX = (x) => pad + ((x - minX) / (maxX - minX || 1)) * (W - pad * 2)
  const toSY = (y) => H - pad - ((y - minY) / (maxY - minY || 1)) * (H - pad * 2)

  // Grid lines
  ctx.strokeStyle = '#ffffff08'
  ctx.lineWidth = 1
  for (let gx = Math.ceil(minX); gx <= Math.floor(maxX); gx++) {
    const sx = toSX(gx)
    ctx.beginPath(); ctx.moveTo(sx, pad); ctx.lineTo(sx, H - pad); ctx.stroke()
    ctx.fillStyle = '#334155'
    ctx.font = '9px JetBrains Mono'
    ctx.textAlign = 'center'
    ctx.fillText(gx, sx, H - 10)
  }
  for (let gy = Math.ceil(minY); gy <= Math.floor(maxY); gy++) {
    const sy = toSY(gy)
    ctx.beginPath(); ctx.moveTo(pad, sy); ctx.lineTo(W - pad, sy); ctx.stroke()
    ctx.fillStyle = '#334155'
    ctx.font = '9px JetBrains Mono'
    ctx.textAlign = 'right'
    ctx.fillText(gy, pad - 4, sy + 3)
  }

  // Mined tiles
  mined.forEach(p => {
    const sx = toSX(p.x), sy = toSY(p.y)
    ctx.beginPath()
    ctx.roundRect(sx - 7, sy - 7, 14, 14, 2)
    ctx.fillStyle   = 'rgba(255,107,53,0.25)'
    ctx.strokeStyle = '#ff6b35'
    ctx.lineWidth   = 1.5
    ctx.fill()
    ctx.stroke()
  })

  // Rover position
  if (pos) {
    const sx = toSX(pos.x), sy = toSY(pos.y)
    // glow
    const grd = ctx.createRadialGradient(sx, sy, 0, sx, sy, 16)
    grd.addColorStop(0, 'rgba(0,255,200,0.4)')
    grd.addColorStop(1, 'rgba(0,255,200,0)')
    ctx.fillStyle = grd
    ctx.beginPath(); ctx.arc(sx, sy, 16, 0, Math.PI * 2); ctx.fill()
    // dot
    ctx.beginPath(); ctx.arc(sx, sy, 5, 0, Math.PI * 2)
    ctx.fillStyle   = '#00ffc8'
    ctx.strokeStyle = '#ffffff'
    ctx.lineWidth   = 1.5
    ctx.fill(); ctx.stroke()
  }
}

// ── Push one data point into history ─────────────────────────────────────────
function pushHistory() {
  const d = store.dashboard
  if (!d) return

  hTime.push(d.elapsed_hrs ?? tick)
  hDist.push(d.rover_distance_travelled ?? 0)
  hTick.push(tick)
  hProd.push(d.rover_energy_produce ?? 0)
  hCons.push(d.rover_energy_consumption ?? 0)
  tick++

  if (hTime.length > MAX) { hTime.shift(); hDist.shift() }
  if (hTick.length > MAX) { hTick.shift(); hProd.shift(); hCons.shift() }
}

// ── Reflow on resize ──────────────────────────────────────────────────────────
function reflow() {
  if (uDist && distRef.value) {
    uDist.setSize({ width: distRef.value.clientWidth, height: distRef.value.clientHeight })
  }
  if (uEnergy && energyRef.value) {
    uEnergy.setSize({ width: energyRef.value.clientWidth, height: energyRef.value.clientHeight })
  }
  drawScatter()
}

// ── Main update (called on every WS packet) ───────────────────────────────────
async function onData() {
  if (!store.dashboard) return
  pushHistory()

  if (!uDist || !uEnergy) {
    await nextTick()
    initDist()
    initEnergy()
  }

  updateDist()
  updateEnergy()
  drawScatter()
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────
onMounted(() => {
  store.connect()
  window.addEventListener('resize', reflow)
  // If data already in store
  if (store.dashboard) onData()
})

onBeforeUnmount(() => {
  store.disconnect()
  window.removeEventListener('resize', reflow)
  uDist?.destroy()
  uEnergy?.destroy()
})

watch(() => store.dashboard, onData, { deep: true })
watch(() => store.mined,     drawScatter, { deep: true })
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;600;700&family=Orbitron:wght@400;700;900&display=swap');

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

.dashboard {
  position: relative;
  width: calc(100% - 68px);
  min-height: 100vh;
  background: #060c14;
  color: #e2e8f0;
  font-family: 'JetBrains Mono', monospace;
  overflow-x: hidden;
  padding-bottom: 32px;
  margin-left: 68px;
  margin-top: 68px;
}

.bg-grid {
  position: fixed; inset: 0; pointer-events: none; z-index: 0;
  background-image:
    linear-gradient(rgba(0,255,200,.022) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0,255,200,.022) 1px, transparent 1px);
  background-size: 36px 36px;
}

/* Header */
.dash-header {
  position: sticky; top: 0; z-index: 100;
  display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px;
  padding: 12px 20px;
  border-bottom: 1px solid rgba(0,255,200,.1);
  background: rgba(6,12,20,.94);
  backdrop-filter: blur(14px);
}
.header-left  { display: flex; align-items: center; gap: 10px; }
.logo-hex     { font-size: 20px; color: #00ffc8; animation: spin 14s linear infinite; display:block; }
@keyframes spin { to { transform: rotate(360deg); } }
.logo-text    { font-family:'Orbitron',sans-serif; font-size:15px; font-weight:900; letter-spacing:.1em; }
.logo-text em { color:#00ffc8; font-style:normal; }

.header-center { display:flex; gap:24px; flex-wrap:wrap; }
.time-display  { display:flex; flex-direction:column; align-items:center; gap:2px; }
.time-label    { font-size:9px; color:#475569; letter-spacing:.12em; }
.time-value    { font-size:13px; font-weight:600; color:#e2e8f0; }

.conn-badge   { display:flex; align-items:center; gap:6px; font-size:10px; font-weight:700; letter-spacing:.12em; color:#475569; }
.conn-badge.connected { color:#00ffc8; }
.conn-dot     { width:7px; height:7px; border-radius:50%; background:currentColor; flex-shrink:0; }
.conn-badge.connected .conn-dot { animation: blink 1s ease-in-out infinite; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:.15} }

/* Grid */
.dash-grid {
  position: relative; z-index: 1;
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  grid-auto-rows: auto;
  gap: 12px;
  padding: 14px;
}

/* Cards */
.card {
  background: rgba(255,255,255,.024);
  border: 1px solid rgba(255,255,255,.07);
  border-radius: 8px;
  padding: 14px;
  min-width: 0;
  animation: fadeUp .4s both;
  transition: border-color .3s;
}
.card:hover { border-color: rgba(0,255,200,.15); }
@keyframes fadeUp { from{opacity:0;transform:translateY(10px)} to{opacity:1;transform:none} }

.status-card  { grid-column: span 3; animation-delay:.04s; display:flex; flex-direction:column; gap:14px; }
.battery-card { grid-column: span 3; animation-delay:.08s; }
.chart-card   { grid-column: span 6; animation-delay:.12s; }
.storage-card { grid-column: span 4; animation-delay:.16s; }
.scatter-card { grid-column: span 8; animation-delay:.20s; }

/* Card header */
.card-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:10px; gap:6px; flex-wrap:wrap; }
.card-title  { font-size:9px; letter-spacing:.16em; color:#475569; font-weight:700; }
.card-value  { font-family:'Orbitron',sans-serif; font-size:18px; font-weight:700; }
.legend-row  { display:flex; align-items:center; gap:5px; font-size:10px; color:#64748b; flex-wrap:wrap; }
.leg-dot     { display:inline-block; width:7px; height:7px; border-radius:50%; flex-shrink:0; }

/* uPlot wrapper — must have explicit size */
.uplot-wrap {
  width: 100%;
  height: 170px;
  overflow: hidden;
}
/* uPlot internal overrides */
:deep(.uplot) { width: 100% !important; }
:deep(.u-wrap) { width: 100% !important; }

/* Status card */
.status-icon-wrap {
  position:relative; width:52px; height:52px;
  display:flex; align-items:center; justify-content:center;
}
.status-big-icon { font-size:26px; position:relative; z-index:1; }
.ring { position:absolute; border-radius:50%; border:1px solid currentColor; opacity:.2; }
.r1   { width:100%; height:100%; animation:rp 2s ease-out infinite; }
.r2   { width:140%; height:140%; animation:rp 2s .6s ease-out infinite; }
@keyframes rp { from{transform:scale(.7);opacity:.4} to{transform:scale(1.5);opacity:0} }
.accent-orange .status-icon-wrap { color:#ff6b35; }
.accent-cyan   .status-icon-wrap { color:#00ffc8; }
.accent-gray   .status-icon-wrap { color:#475569; }
.accent-orange { border-color:rgba(255,107,53,.2); }
.accent-cyan   { border-color:rgba(0,255,200,.2); }
.status-info   { display:flex; flex-direction:column; gap:3px; }
.s-label { font-size:9px; color:#475569; letter-spacing:.14em; }
.s-text  { font-family:'Orbitron',sans-serif; font-size:18px; font-weight:900; }
.accent-orange .s-text { color:#ff6b35; }
.accent-cyan   .s-text { color:#00ffc8; }
.accent-gray   .s-text { color:#64748b; }
.s-sub   { font-size:10px; color:#475569; }
.status-stats  { display:flex; gap:16px; margin-top:auto; }
.stat-item { display:flex; flex-direction:column; gap:2px; }
.stat-lbl  { font-size:9px; color:#334155; letter-spacing:.12em; }
.stat-val  { font-size:14px; font-weight:700; color:#e2e8f0; }
.stat-val em { font-size:10px; color:#475569; font-style:normal; margin-left:2px; }

/* Battery arc */
.battery-arc-wrap { display:flex; justify-content:center; align-items:center; padding-top:4px; }
.battery-svg { width:100%; max-width:180px; }

/* Storage pie */
.pie-wrap { display:flex; align-items:center; gap:16px; height:160px; }
.pie-svg  { width:130px; height:130px; flex-shrink:0; overflow:visible; }
.pie-legend { display:flex; flex-direction:column; gap:8px; flex:1; }
.pie-leg-row { display:flex; align-items:center; gap:8px; font-size:11px; }
.pie-leg-dot { width:9px; height:9px; border-radius:2px; flex-shrink:0; }
.pie-leg-label { color:#94a3b8; flex:1; }
.pie-leg-val   { font-weight:700; color:#e2e8f0; font-family:'Orbitron',sans-serif; font-size:12px; }

/* Scatter canvas */
.scatter-canvas {
  display:block; width:100%; height:220px;
  border-radius:4px; background:#060c14;
}

/* Responsive */
@media  (max-width: 576px) {
  .dash-grid {
    grid-template-columns: repeat(6, 1fr);
    gap: 10px;
    padding: 10px;
  }
  .dashboard {
    width: 100%;
    margin-left: 0px;
  }
  .status-card,
  .battery-card,
  .scatter-card {
    grid-column: span 3;
  }
  .storage-card {
    grid-column: span 6;
  }

  .chart-card {
    grid-column: span 6;
  }
}

/* Large tablets / small laptops */
@media (min-width: 577px) and (max-width: 1100px) {
  .status-card,
  .battery-card,
  .chart-card {
    grid-column: span 4;
  }

  .storage-card,
  .scatter-card {
    grid-column: span 6;
  }
}

/* Optional: extra-large screens (desktop) */
@media (min-width: 1101px) {
  .dash-grid {
    grid-template-columns: repeat(12, 1fr);
    gap: 12px;
    padding: 12px;
  }

  .status-card,
  .battery-card,
  .chart-card {
    grid-column: span 4;
  }

  .storage-card,
  .scatter-card {
    grid-column: span 6;
  }
}
</style>