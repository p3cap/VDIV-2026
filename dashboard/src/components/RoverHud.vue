<script setup>
/**
 * RoverHud.vue
 *
 * Pure presentational overlay.
 * Receives all display data via props — no store, no side-effects, no Three.js.
 * Renders the HUD panels on top of the 3-D canvas.
 */
import { computed } from 'vue'

// ─── Props ────────────────────────────────────────────────────────────────────
const props = defineProps({
	roverName: { type: String, default: 'ROVER-1' },
	roverStatus: { type: String, default: 'idle' },
	roverBattery: { type: Number, default: 100 },
	roverSpeed: { type: Number, default: 0 },
	roverStorage: { type: Object, default: () => ({}) },
	roverPosition: { type: Object, default: () => ({ x: 0, y: 0 }) },
	distanceTravelled: { type: Number, default: 0 },
	elapsedHrs: { type: Number, default: 0 },
	energyConsume: { type: Number, default: 0 },
	energyProduce: { type: Number, default: 0 },
	timeOfDay: { type: Number, default: 12 },
	dayHrs: { type: Number, default: 16 },
	nightHrs: { type: Number, default: 8 },
	markers: { type: Object, default: () => ({}) },
	pathPlan: { type: Array, default: () => [] },
})

// ─── Derived display values ───────────────────────────────────────────────────
const totalCycle = computed(() => props.dayHrs + props.nightHrs)
const isDay = computed(() => props.timeOfDay % totalCycle.value < props.dayHrs)

const batteryColor = computed(() => {
	if (props.roverBattery > 60) return '#2ed573'
	if (props.roverBattery > 25) return '#ffa502'
	return '#ff4757'
})

const STATUS_LABELS = {
	mine: '⛏ MINING',
	move: '🚀 MOVING',
	standby: '💤 STANDBY',
	charge: '⚡ CHARGING',
	idle: '○ IDLE',
}
const statusLabel = computed(
	() => STATUS_LABELS[props.roverStatus] ?? props.roverStatus?.toUpperCase() ?? 'UNKNOWN',
)

const storageEntries = computed(() =>
	Object.entries(props.roverStorage ?? {}).filter(([, qty]) => qty > 0),
)
</script>

<template>
	<div class="hud" aria-label="Rover HUD overlay">
		<!-- ── Top bar ── -->
		<header class="top-bar">
			<span class="rover-id">{{ roverName }}</span>

			<span class="day-chip" :class="isDay ? 'day' : 'night'">
				{{ isDay ? '☀' : '🌙' }}
				<strong>{{ isDay ? 'DAY' : 'NIGHT' }}</strong>
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

<style src="../styles/main.css"></style>
