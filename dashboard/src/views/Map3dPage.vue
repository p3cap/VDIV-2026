<script setup>
/**
 * RoverDashboardPage.vue
 *
 * Single source of truth for the rover dashboard.
 * - Connects to the WebSocket store.
 * - Derives all display-ready data via computed properties.
 * - Passes everything down to child components via props only.
 * - No child component accesses the store directly.
 */
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { useLiveWsStore } from '@/stores/liveWs'
import Map3DComponent from '@/components/Map3DComponent.vue'
import RoverHud from '@/components/RoverHud.vue'
import RoverInstruments from '@/components/RoverInstruments.vue'

// ─── Store ────────────────────────────────────────────────────────────────────
const ws = useLiveWsStore()

onMounted(() => ws.connect())
onBeforeUnmount(() => ws.disconnect())

// ─── Raw data aliases (never mutated here) ────────────────────────────────────
const dash = computed(() => ws.dashboard ?? {})
const setup = computed(() => ws.setupData ?? {})

// ─── Guard: only render when minimum data is present ─────────────────────────
const ready = computed(
		() => setup.value.map_matrix?.length > 0 && dash.value.rover_position != null,
)

// ─── Map props ────────────────────────────────────────────────────────────────
const mapMatrix = computed(() => setup.value.map_matrix ?? [])
const roverPosition = computed(() => dash.value.rover_position ?? { x: 0, y: 0 })
const pathPlan = computed(() => dash.value.rover_path_plan ?? dash.value.path_plan ?? [])
const minedCells = computed(() => dash.value.rover_mined ?? [])

// ─── HUD props — rover status ─────────────────────────────────────────────────
const roverName = computed(() => setup.value.rover_name ?? 'ROVER-1')
const roverStatus = computed(() => dash.value.rover_status ?? 'idle')
const roverBattery = computed(() => dash.value.rover_battery ?? 0)
const roverSpeed = computed(() => dash.value.rover_speed ?? 0)
const roverStorage = computed(() => dash.value.rover_storage ?? {})
const distanceTravelled = computed(() => dash.value.rover_distance_travelled ?? 0)
const elapsedHrs = computed(() => dash.value.elapsed_hrs ?? 0)
const energyConsume = computed(() => dash.value.rover_energy_consumption ?? 0)
const energyProduce = computed(() => dash.value.rover_energy_produce ?? 0)

// ─── HUD props — time / environment ──────────────────────────────────────────
const timeOfDay = computed(() => dash.value.time_of_day ?? 0)
const dayHrs = computed(() => setup.value.day_hrs ?? 16)
const nightHrs = computed(() => setup.value.night_hrs ?? 8)
const markers = computed(() => setup.value.markers ?? {})
</script>

<template>
		<div class="map3d-page">
				<template v-if="ready">
						<!--
				Map3DComponent owns the WebGL canvas.
				It receives ONLY what it needs to render the 3-D scene.
			-->
						<Map3DComponent
								:map-matrix="mapMatrix"
								:rover-position="roverPosition"
								:path-plan="pathPlan"
								:mined-cells="minedCells"
								:rover-status="roverStatus"
								:rover-speed="roverSpeed"
								:time-of-day="timeOfDay"
								:day-hrs="dayHrs"
								:night-hrs="nightHrs"
						/>

						<!--
				RoverHud is a pure presentational overlay.
				It receives display-ready values and emits nothing.
			-->
						<RoverHud
								:rover-name="roverName"
								:rover-status="roverStatus"
								:rover-battery="roverBattery"
								:rover-speed="roverSpeed"
								:rover-storage="roverStorage"
								:rover-position="roverPosition"
								:distance-travelled="distanceTravelled"
								:elapsed-hrs="elapsedHrs"
								:energy-consume="energyConsume"
								:energy-produce="energyProduce"
								:time-of-day="timeOfDay"
								:day-hrs="dayHrs"
								:night-hrs="nightHrs"
								:markers="markers"
								:path-plan="pathPlan"
						/>

						<!--
				RoverInstruments: speedometer + gear indicator.
				Positioned bottom-right so it doesn't overlap the HUD panels.
			-->
						<div class="instruments-anchor">
								<RoverInstruments
										:rover-speed="roverSpeed"
										:rover-status="roverStatus"
										:rover-battery="roverBattery"
										:max-speed="6"
								/>
						</div>
				</template>

				<!-- Loading state while WS hasn't delivered initial data yet -->
				<div v-else class="loader">
						<span class="loader-dot" />
						<span class="loader-dot" />
						<span class="loader-dot" />
						<p>Kapcsolódás a szerverhez…</p>
				</div>
		</div>
</template>

<style src="../styles/main.css"></style>
