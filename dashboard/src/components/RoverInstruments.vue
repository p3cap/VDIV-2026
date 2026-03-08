<script setup>
/**
 * RoverInstruments.vue
 *
 * Pure presentational instruments panel.
 * - Speedometer: SVG arc gauge, needle sweeps 0 → maxSpeed.
 * - Gear display: shows current operating mode as a styled gear badge.
 *
 * Arc geometry:
 *   Start: 225° (bottom-left, 7 o'clock position)
 *   Sweep: 270° clockwise
 *   End:   135° (bottom-right, 5 o'clock position)
 *
 *   SVG angles measured clockwise from 3 o'clock (standard canvas convention).
 *   0°=right, 90°=down, 180°=left, 270°=up.
 *   So 225° = bottom-left, 225+270=495 mod 360 = 135° = bottom-right. ✓
 *
 *   The arc always sweeps clockwise (sweep-flag = 1).
 *   large-arc-flag = 1 when the swept angle exceeds 180°.
 */
import { computed, ref, watch, onBeforeUnmount } from "vue";

const props = defineProps({
  roverSpeed:   { type: Number, default: 0 },
  roverStatus:  { type: String, default: "idle" },
  maxSpeed:     { type: Number, default: 6 },
  roverBattery: { type: Number, default: 100 },
});

// ─── SVG canvas constants ─────────────────────────────────────────────────────
const W  = 180;          // viewBox width
const H  = 160;          // viewBox height
const CX = W / 2;        // centre X
const CY = H / 2 + 8;   // centre Y (shifted down slightly for label room)
const R  = 68;           // arc radius

const START_DEG = 225;   // 7 o'clock
const SWEEP_DEG = 270;   // full sweep
// END_DEG = (225 + 270) % 360 = 135  (5 o'clock)

// ─── Geometry helpers ─────────────────────────────────────────────────────────
function pt(deg, r = R) {
  const rad = (deg * Math.PI) / 180;
  return { x: CX + r * Math.cos(rad), y: CY + r * Math.sin(rad) };
}

/** SVG arc path string, always sweeping clockwise. */
function arcPath(startDeg, sweepDeg, r = R) {
  if (sweepDeg <= 0) return "";
  // Clamp to just under 360 — a full-circle arc collapses in SVG
  const clampedSweep = Math.min(sweepDeg, 359.99);
  const endDeg = startDeg + clampedSweep;
  const s    = pt(startDeg, r);
  const e    = pt(endDeg,   r);
  const large = clampedSweep > 180 ? 1 : 0;
  return `M ${s.x.toFixed(2)} ${s.y.toFixed(2)} A ${r} ${r} 0 ${large} 1 ${e.x.toFixed(2)} ${e.y.toFixed(2)}`;
}

// ─── Smooth animated speed value ─────────────────────────────────────────────
// All arc/needle calculations are driven by displaySpeed, not the raw prop,
// so the needle visually follows the same smooth value as the readout text.
const displaySpeed = ref(props.roverSpeed);
let animFrame = 0;

function animateSpeed() {
  const diff = props.roverSpeed - displaySpeed.value;
  if (Math.abs(diff) > 0.004) {
    displaySpeed.value += diff * 0.14;
    animFrame = requestAnimationFrame(animateSpeed);
  } else {
    displaySpeed.value = props.roverSpeed;
  }
}

watch(() => props.roverSpeed, () => {
  cancelAnimationFrame(animFrame);
  animFrame = requestAnimationFrame(animateSpeed);
}, { immediate: true });

onBeforeUnmount(() => cancelAnimationFrame(animFrame));

// ─── Derived arc geometry ─────────────────────────────────────────────────────
const frac = computed(() => Math.min(1, Math.max(0, displaySpeed.value / props.maxSpeed)));

// Full background arc (always 270°)
const bgArc = arcPath(START_DEG, SWEEP_DEG);

// Value arc grows from START_DEG by frac * SWEEP_DEG
const valueArc = computed(() => {
  const sweep = frac.value * SWEEP_DEG;
  return sweep < 0.5 ? "" : arcPath(START_DEG, sweep);
});

// Needle tip — same angle as value arc end
const needleTip = computed(() => pt(START_DEG + frac.value * SWEEP_DEG, R - 6));

// Tick marks: one per integer speed step (0 … maxSpeed)
const ticks = computed(() =>
  Array.from({ length: props.maxSpeed + 1 }, (_, i) => {
    const deg   = START_DEG + (i / props.maxSpeed) * SWEEP_DEG;
    const isMajor = i % 2 === 0;
    return {
      inner: pt(deg, R - (isMajor ? 13 : 8)),
      outer: pt(deg, R + 5),
      label: isMajor ? pt(deg, R - 22) : null,
      value: i,
    };
  }),
);

// Arc stroke colour: green → amber → red
const arcColor = computed(() => {
  const f = frac.value;
  if (f < 0.45) return "#2ed573";
  if (f < 0.78) return "#ffa502";
  return "#ff4757";
});

// ─── Gear / mode display ──────────────────────────────────────────────────────
const GEARS = {
  idle:    { label: "N", name: "IDLE",    color: "#556070" },
  standby: { label: "P", name: "STANDBY", color: "#556070" },
  move:    { label: "D", name: "DRIVE",   color: "#44d1ff" },
  mine:    { label: "M", name: "MINING",  color: "#ffaa00" },
  charge:  { label: "C", name: "CHARGE",  color: "#2ed573" },
};
const gear = computed(() =>
  GEARS[props.roverStatus] ?? { label: "?", name: props.roverStatus?.toUpperCase() ?? "—", color: "#556070" },
);

// ─── Battery colour ───────────────────────────────────────────────────────────
const battColor = computed(() => {
  if (props.roverBattery > 60) return "#2ed573";
  if (props.roverBattery > 25) return "#ffa502";
  return "#ff4757";
});
</script>

<template>
  <div class="instruments">

    <!-- ── Speedometer ── -->
    <div class="card speedo-card">
      <p class="card-title">SPEED</p>

      <svg :viewBox="`0 0 ${W} ${H}`" class="speedo-svg" aria-label="Speedometer">

        <!-- Background arc (static) -->
        <path :d="bgArc" fill="none" stroke="#1a2530" stroke-width="9" stroke-linecap="round" />

        <!-- Value arc (grows with speed) -->
        <path
          v-if="valueArc"
          :d="valueArc"
          fill="none"
          :stroke="arcColor"
          stroke-width="9"
          stroke-linecap="round"
        />

        <!-- Tick marks + labels -->
        <g v-for="tk in ticks" :key="tk.value">
          <line
            :x1="tk.inner.x" :y1="tk.inner.y"
            :x2="tk.outer.x" :y2="tk.outer.y"
            :stroke="tk.value === 0 || tk.value === maxSpeed ? '#ff6b35' : '#2a3a4a'"
            :stroke-width="tk.label ? 2 : 1.5"
            stroke-linecap="round"
          />
          <text
            v-if="tk.label"
            :x="tk.label.x" :y="tk.label.y + 3"
            text-anchor="middle"
            class="speedo-tick-label"
          >{{ tk.value }}</text>
        </g>

        <!-- Needle -->
        <line
          :x1="CX" :y1="CY"
          :x2="needleTip.x" :y2="needleTip.y"
          :stroke="arcColor"
          stroke-width="2.5"
          stroke-linecap="round"
        />
        <circle :cx="CX" :cy="CY" r="5" :fill="arcColor" />
        <circle :cx="CX" :cy="CY" r="2" fill="#07080c" />

        <!-- Digital readout -->
        <text :x="CX" :y="CY + 20" text-anchor="middle" class="speedo-value">
          {{ displaySpeed.toFixed(1) }}
        </text>
        <text :x="CX" :y="CY + 32" text-anchor="middle" class="speedo-unit">cell/h</text>

      </svg>
    </div>

    <!-- ── Gear indicator ── -->
    <div class="card gear-card">
      <p class="card-title">GEAR</p>

      <div class="gear-display">
        <div
          class="gear-letter"
          :style="{ color: gear.color, borderColor: gear.color, boxShadow: `0 0 14px ${gear.color}44` }"
        >
          {{ gear.label }}
        </div>
        <div class="gear-name" :style="{ color: gear.color }">{{ gear.name }}</div>
      </div>

      <!-- Mini battery bar -->
      <div class="batt-mini">
        <span class="batt-label">PWR</span>
        <div class="batt-track">
          <div
            class="batt-fill"
            :style="{ width: roverBattery + '%', background: battColor, boxShadow: `0 0 6px ${battColor}` }"
          />
        </div>
        <span class="batt-pct" :style="{ color: battColor }">{{ roverBattery.toFixed(0) }}%</span>
      </div>
    </div>

  </div>
</template>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Exo+2:wght@600;800&display=swap');

.instruments {
  display: flex;
  flex-direction: column;
  gap: 8px;
  pointer-events: none;
}

/* ── Card shell ── */
.card {
  background: linear-gradient(155deg, rgba(6, 10, 18, 0.92), rgba(2, 5, 10, 0.96));
  border: 1px solid rgba(255, 107, 53, 0.16);
  border-radius: 10px;
  padding: 10px 12px 8px;
  backdrop-filter: blur(6px);
}

.card-title {
  margin: 0 0 6px;
  font-family: 'Exo 2', sans-serif;
  font-size: 0.54rem;
  font-weight: 800;
  letter-spacing: 0.26em;
  text-transform: uppercase;
  color: #ff6b35;
}

/* ── Speedometer SVG ── */
.speedo-card { width: 184px; }

.speedo-svg {
  display: block;
  width: 100%;
  height: auto;
  overflow: visible;
}

.speedo-value {
  font-family: 'Share Tech Mono', monospace;
  font-size: 20px;
  fill: #dce3e8;
}

.speedo-unit {
  font-family: 'Exo 2', sans-serif;
  font-size: 7px;
  fill: #44566a;
  letter-spacing: 0.12em;
}

.speedo-tick-label {
  font-family: 'Share Tech Mono', monospace;
  font-size: 9px;
  fill: #44566a;
}

/* ── Gear display ── */
.gear-card { width: 184px; }

.gear-display {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}

.gear-letter {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  border: 2px solid;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: 'Share Tech Mono', monospace;
  font-size: 1.6rem;
  font-weight: 700;
  flex-shrink: 0;
  transition: color 0.3s ease, border-color 0.3s ease, box-shadow 0.3s ease;
}

.gear-name {
  font-family: 'Exo 2', sans-serif;
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  transition: color 0.3s ease;
}

/* ── Battery mini ── */
.batt-mini {
  display: flex;
  align-items: center;
  gap: 6px;
}

.batt-label {
  font-family: 'Share Tech Mono', monospace;
  font-size: 0.55rem;
  color: #44566a;
  letter-spacing: 0.1em;
  flex-shrink: 0;
}

.batt-track {
  flex: 1;
  height: 6px;
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.05);
  overflow: hidden;
}

.batt-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.5s ease, background 0.5s ease;
}

.batt-pct {
  font-family: 'Share Tech Mono', monospace;
  font-size: 0.58rem;
  min-width: 28px;
  text-align: right;
  transition: color 0.5s ease;
}
</style>