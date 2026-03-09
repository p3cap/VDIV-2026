<script setup>
/**
 * RoverHud.vue
 *
 * Pure presentational overlay.
 * Receives all display data via props — no store, no side-effects, no Three.js.
 * Renders the HUD panels on top of the 3-D canvas.
 */
import { computed } from "vue";

// ─── Props ────────────────────────────────────────────────────────────────────
const props = defineProps({
  roverName:          { type: String, default: "ROVER-1" },
  roverStatus:        { type: String, default: "idle" },
  roverBattery:       { type: Number, default: 100 },
  roverSpeed:         { type: Number, default: 0 },
  roverStorage:       { type: Object, default: () => ({}) },
  roverPosition:      { type: Object, default: () => ({ x: 0, y: 0 }) },
  distanceTravelled:  { type: Number, default: 0 },
  elapsedHrs:         { type: Number, default: 0 },
  energyConsume:      { type: Number, default: 0 },
  energyProduce:      { type: Number, default: 0 },
  timeOfDay:          { type: Number, default: 12 },
  dayHrs:             { type: Number, default: 16 },
  nightHrs:           { type: Number, default: 8 },
  markers:            { type: Object, default: () => ({}) },
  pathPlan:           { type: Array,  default: () => [] },
});

// ─── Derived display values ───────────────────────────────────────────────────
const totalCycle = computed(() => props.dayHrs + props.nightHrs);
const isDay      = computed(() => (props.timeOfDay % totalCycle.value) < props.dayHrs);

const batteryColor = computed(() => {
  if (props.roverBattery > 60) return "#2ed573";
  if (props.roverBattery > 25) return "#ffa502";
  return "#ff4757";
});

const STATUS_LABELS = {
  mine:    "⛏ MINING",
  move:    "🚀 MOVING",
  standby: "💤 STANDBY",
  charge:  "⚡ CHARGING",
  idle:    "○ IDLE",
};
const statusLabel = computed(() =>
  STATUS_LABELS[props.roverStatus] ?? props.roverStatus?.toUpperCase() ?? "UNKNOWN",
);

const storageEntries = computed(() =>
  Object.entries(props.roverStorage ?? {}).filter(([, qty]) => qty > 0),
);
</script>

<template>
  <div class="hud" aria-label="Rover HUD overlay">

    <!-- ── Top bar ── -->
    <header class="top-bar">
      <span class="rover-id">{{ roverName }}</span>

      <span class="day-chip" :class="isDay ? 'day' : 'night'">
        {{ isDay ? "☀" : "🌙" }}
        <strong>{{ isDay ? "DAY" : "NIGHT" }}</strong>
        <span class="tod">{{ timeOfDay.toFixed(1) }}h</span>
      </span>
    </header>

    <!-- ── Left panel: Status + Battery ── -->
    <aside class="panel panel--left" aria-label="Rover status">
      <h2 class="panel-title">STATUS</h2>

      <dl class="stat-list">
        <div class="stat-row">
          <dt>Mode</dt>
          <dd>
            <span class="status-badge" :data-status="roverStatus">
              {{ statusLabel }}
            </span>
          </dd>
        </div>
        <div class="stat-row">
          <dt>Position</dt>
          <dd class="mono">{{ roverPosition.x ?? 0 }}, {{ roverPosition.y ?? 0 }}</dd>
        </div>
        <div class="stat-row">
          <dt>Speed</dt>
          <dd>{{ roverSpeed }} cell/h</dd>
        </div>
        <div class="stat-row">
          <dt>Distance</dt>
          <dd>{{ distanceTravelled }} cells</dd>
        </div>
        <div class="stat-row">
          <dt>Elapsed</dt>
          <dd>{{ elapsedHrs.toFixed(1) }} hrs</dd>
        </div>
      </dl>

      <hr class="divider" />

      <h2 class="panel-title">BATTERY</h2>

      <div class="battery-wrap">
        <div class="battery-track">
          <div
            class="battery-fill"
            :style="{ width: `${roverBattery}%`, '--color': batteryColor }"
          />
        </div>
        <span class="battery-pct" :style="{ color: batteryColor }">
          {{ roverBattery.toFixed(0) }}%
        </span>
      </div>

      <dl class="stat-list mt-6">
        <div class="stat-row">
          <dt>⚡ Produce</dt>
          <dd class="green">+{{ energyProduce.toFixed(1) }}/h</dd>
        </div>
        <div class="stat-row">
          <dt>🔋 Consume</dt>
          <dd class="orange">-{{ energyConsume.toFixed(1) }}/h</dd>
        </div>
      </dl>
    </aside>

    <!-- ── Right panel: Cargo + Legend ── -->
    <aside class="panel panel--right" aria-label="Cargo and map legend">
      <h2 class="panel-title">CARGO</h2>

      <ul v-if="storageEntries.length" class="cargo-list">
        <li v-for="[key, qty] in storageEntries" :key="key" class="cargo-item">
          <span class="ore-dot" :data-ore="key" aria-hidden="true" />
          <span class="ore-name">{{ markers[key] ?? key }}</span>
          <span class="ore-qty mono">{{ qty.toLocaleString() }}</span>
        </li>
      </ul>
      <p v-else class="empty-label">Empty</p>

      <hr class="divider" />

      <h2 class="panel-title">LEGEND</h2>

      <ul class="legend-list">
        <li v-for="(label, sym) in markers" :key="sym" class="legend-item">
          <span class="ore-dot" :data-ore="sym" aria-hidden="true" />
          <span class="legend-sym mono">{{ sym }}</span>
          <span class="legend-lbl">{{ label }}</span>
        </li>
      </ul>
    </aside>

    <!-- ── Path badge ── -->
    <div v-if="pathPlan.length" class="path-badge" role="status">
      <span class="path-pulse" aria-hidden="true">◈</span>
      PATH · {{ pathPlan.length }} waypoints
    </div>

  </div>
</template>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Exo+2:wght@300;600;800&display=swap');

/* ── Shell ─────────────────────────────────────────────────────────────── */
.hud {
  position: absolute;
  inset: 0;
  pointer-events: none;   /* canvas stays interactive beneath */
  font-family: 'Exo 2', sans-serif;
}

/* ── Top bar ────────────────────────────────────────────────────────────── */
.top-bar {
  position: absolute;
  top: 0; left: 80px; right: 0;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  background: linear-gradient(to bottom, rgba(0, 0, 0, 0.72), transparent);
}

.rover-id {
  font-family: 'Share Tech Mono', monospace;
  font-size: 0.95rem;
  letter-spacing: 0.25em;
  color: #ff6b35;
  text-shadow: 0 0 14px rgba(255, 107, 53, 0.45);
  text-transform: uppercase;
}

.day-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 11px;
  border-radius: 20px;
  font-size: 0.68rem;
  font-weight: 600;
  letter-spacing: 0.1em;
}
.day-chip.day {
  background: rgba(255, 180, 0, 0.14);
  color: #ffd070;
  border: 1px solid rgba(255, 200, 0, 0.22);
}
.day-chip.night {
  background: rgba(60, 80, 200, 0.14);
  color: #8898ff;
  border: 1px solid rgba(100, 120, 255, 0.2);
}
.tod {
  font-family: 'Share Tech Mono', monospace;
}

/* ── Panels ─────────────────────────────────────────────────────────────── */
.panel {
  position: absolute;
  top: 48px;
  width: 192px;
  padding: 12px 14px;
  background: linear-gradient(155deg, rgba(6, 10, 18, 0.91), rgba(2, 5, 10, 0.95));
  border: 1px solid rgba(255, 107, 53, 0.16);
  border-radius: 9px;
  backdrop-filter: blur(7px);
  color: #bcc8d8;
}
.panel--left  { left: 90px; }
.panel--right { right: 60px; }

.panel-title {
  margin: 0 0 8px;
  font-size: 0.56rem;
  font-weight: 800;
  letter-spacing: 0.24em;
  text-transform: uppercase;
  color: #ff6b35;
}

/* ── Stat list ──────────────────────────────────────────────────────────── */
.stat-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.stat-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 2.5px 0;
  font-size: 0.72rem;
}
.stat-row dt { color: #46566a; }
.stat-row dd { margin: 0; color: #ccd8e6; font-weight: 600; }
.stat-row dd.green  { color: #2ed573; }
.stat-row dd.orange { color: #ffa502; }

.mt-6 { margin-top: 6px; }
.mono { font-family: 'Share Tech Mono', monospace; }

/* ── Status badge ───────────────────────────────────────────────────────── */
.status-badge {
  font-size: 0.62rem;
  padding: 1px 7px;
  border-radius: 4px;
  font-weight: 700;
}
.status-badge[data-status="mine"]    { background: rgba(255, 107, 53, 0.18); color: #ff8c5a; }
.status-badge[data-status="move"]    { background: rgba(68, 209, 255, 0.14); color: #44d1ff; }
.status-badge[data-status="standby"] { background: rgba(80, 80, 90, 0.16);   color: #778899; }
.status-badge[data-status="charge"]  { background: rgba(255, 210, 0, 0.14);  color: #ffd700; }
.status-badge[data-status="idle"]    { background: rgba(60, 60, 70, 0.14);   color: #666677; }

/* ── Divider ────────────────────────────────────────────────────────────── */
.divider {
  border: none;
  border-top: 1px solid rgba(255, 107, 53, 0.12);
  margin: 9px 0;
}

/* ── Battery ────────────────────────────────────────────────────────────── */
.battery-wrap {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 2px;
}
.battery-track {
  flex: 1;
  height: 9px;
  border-radius: 5px;
  background: rgba(255, 255, 255, 0.06);
  overflow: hidden;
}
.battery-fill {
  height: 100%;
  border-radius: 5px;
  background: var(--color, #2ed573);
  box-shadow: 0 0 8px var(--color, #2ed573);
  transition: width 0.5s ease, background 0.5s ease, box-shadow 0.5s ease;
}
.battery-pct {
  font-size: 0.6rem;
  font-family: 'Share Tech Mono', monospace;
  min-width: 30px;
  text-align: right;
  transition: color 0.5s ease;
}

/* ── Cargo ──────────────────────────────────────────────────────────────── */
.cargo-list,
.legend-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.cargo-item {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 2.5px 0;
  font-size: 0.7rem;
}
.ore-name { color: #7a8a9a; font-size: 0.66rem; }
.ore-qty  { margin-left: auto; color: #ccd8e6; }
.empty-label {
  font-size: 0.65rem;
  color: #2e3a4a;
  font-style: italic;
}

/* ── Legend ─────────────────────────────────────────────────────────────── */
.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 1.5px 0;
  font-size: 0.64rem;
}
.legend-sym { color: #8aaa99; width: 13px; }
.legend-lbl { color: #6070a0; }

/* ── Ore dots ───────────────────────────────────────────────────────────── */
.ore-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.ore-dot[data-ore="Y"] { background: #f4c542; box-shadow: 0 0 5px #ffaa00; }
.ore-dot[data-ore="B"] { background: #a8d8f0; box-shadow: 0 0 5px #44aaff; }
.ore-dot[data-ore="G"] { background: #2ed573; box-shadow: 0 0 5px #00ff88; }
.ore-dot[data-ore="S"] { background: #ff6b35; box-shadow: 0 0 4px #ff6b35; }
.ore-dot[data-ore="#"] { background: #4a2a14; }
.ore-dot[data-ore="."] { background: #2a1a0a; }

/* ── Path badge ─────────────────────────────────────────────────────────── */
.path-badge {
  position: absolute;
  bottom: 16px;
  left: 50%;
  transform: translateX(-50%);
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 5px 18px;
  background: rgba(4, 8, 16, 0.84);
  border: 1px solid rgba(68, 209, 255, 0.22);
  border-radius: 20px;
  font-size: 0.67rem;
  letter-spacing: 0.14em;
  color: #44d1ff;
  white-space: nowrap;
}
.path-pulse {
  animation: pathPulse 1.6s ease-in-out infinite;
}
@keyframes pathPulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.3; }
}
</style>