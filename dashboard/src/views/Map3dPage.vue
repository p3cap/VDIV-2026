<script setup>
/**
 * RoverDashboardPage.vue
 *
 * Single source of truth for the rover dashboard.
 * - Connects to the WebSocket store.
 * - Derives all display-ready data via computed properties.
 * - Passes everything down to child components via props only.
 * - No child component accesses the store directly.
 *
 * Responsive additions:
 * - panelLeftOpen / panelRightOpen toggle HUD panels on ≤1024px
 * - instruments-anchor promoted to page-level so CSS can reposition it as a
 *   full-width bottom bar on tablet/mobile
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
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
const mapMatrix     = computed(() => setup.value.map_matrix ?? [])
const roverPosition = computed(() => dash.value.rover_position ?? { x: 0, y: 0 })
const pathPlan      = computed(() => dash.value.rover_path_plan ?? dash.value.path_plan ?? [])
const minedCells    = computed(() => dash.value.rover_mined ?? [])

// ─── HUD props — rover status ─────────────────────────────────────────────────
const roverName        = computed(() => setup.value.rover_name ?? 'ROVER-1')
const roverStatus      = computed(() => dash.value.rover_status ?? 'idle')
const roverBattery     = computed(() => dash.value.rover_battery ?? 0)
const roverSpeed       = computed(() => dash.value.rover_speed ?? 0)
const roverStorage     = computed(() => dash.value.rover_storage ?? {})
const distanceTravelled= computed(() => dash.value.rover_distance_travelled ?? 0)
const elapsedHrs       = computed(() => dash.value.elapsed_hrs ?? 0)
const energyConsume    = computed(() => dash.value.rover_energy_consumption ?? 0)
const energyProduce    = computed(() => dash.value.rover_energy_produce ?? 0)

// ─── HUD props — time / environment ──────────────────────────────────────────
const timeOfDay = computed(() => dash.value.time_of_day ?? 0)
const dayHrs    = computed(() => setup.value.day_hrs ?? 16)
const nightHrs  = computed(() => setup.value.night_hrs ?? 8)
const markers   = computed(() => setup.value.markers ?? {})

// ─── Responsive: HUD panel toggle state ──────────────────────────────────────
// Only used on tablet/mobile (≤1024px). Desktop always shows panels via CSS.
const panelLeftOpen  = ref(false)
const panelRightOpen = ref(false)

function toggleLeft()  { panelLeftOpen.value  = !panelLeftOpen.value }
function toggleRight() { panelRightOpen.value = !panelRightOpen.value }
</script>

<template>
  <div class="map3d-page">
    <template v-if="ready">

      <!-- 3-D canvas -->
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

      <!-- HUD overlay (receives open-state flags for panel visibility) -->
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
        :panel-left-open="panelLeftOpen"
        :panel-right-open="panelRightOpen"
        @toggle-left="toggleLeft"
        @toggle-right="toggleRight"
      />

      <!--
        instruments-anchor lives at page level so the responsive CSS can
        turn it into a full-width fixed bottom bar on tablet / mobile.
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

    <!-- Loading state -->
    <div v-else class="loader">
      <div class="loader-dots">
        <span class="loader-dot" />
        <span class="loader-dot" />
        <span class="loader-dot" />
      </div>
      <p>Kapcsolódás a szerverhez…</p>
    </div>
  </div>
</template>

<style src="../styles/main.css"></style>
