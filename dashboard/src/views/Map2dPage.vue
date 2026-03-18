<script>
import { useLiveWsStore } from "@/stores/liveWs.js";
import MapComponent from "@/components/MapComponent.vue";
import RoverHud from "@/components/RoverHud.vue";
import RoverInstruments from "@/components/RoverInstruments.vue";
export default {
  name: "Map2dPage",
  components: { MapComponent, RoverHud, RoverInstruments },

  data() {
    return {
      panelLeftOpen: false,
      panelRightOpen: false,
    };
  },

  computed: {
    wsStore() {
      return useLiveWsStore();
    },
    dashboard() {
      return this.wsStore.dashboard;
    },
    setupData() {
      return this.wsStore.setupData;
    },
    ready() {
      return this.setupData?.map_matrix?.length && this.dashboard?.rover_position;
    },

    mapMatrix() {
      return this.setupData?.map_matrix || [];
    },
    roverPosition() {
      return this.dashboard?.rover_position || { x: 0, y: 0 };
    },
    pathPlan() {
      return this.dashboard?.rover_path_plan || this.dashboard?.path_plan || [];
    },
    minedCells() {
      return this.dashboard?.rover_mined || [];
    },

    roverName() {
      return this.setupData?.rover_name || "ROVER-1";
    },
    roverStatus() {
      return this.dashboard?.rover_status || "idle";
    },
    roverBattery() {
      return this.dashboard?.rover_battery ?? 0;
    },
    roverSpeed() {
      return this.dashboard?.rover_speed ?? 0;
    },
    roverStorage() {
      return this.dashboard?.rover_storage || {};
    },
    distanceTravelled() {
      return this.dashboard?.rover_distance_travelled ?? 0;
    },
    elapsedHrs() {
      return this.dashboard?.elapsed_hrs ?? 0;
    },
    energyConsume() {
      return this.dashboard?.rover_energy_consumption ?? 0;
    },
    energyProduce() {
      return this.dashboard?.rover_energy_produce ?? 0;
    },
    timeOfDay() {
      return this.dashboard?.time_of_day ?? 0;
    },
    dayHrs() {
      return this.setupData?.day_hrs ?? 16;
    },
    nightHrs() {
      return this.setupData?.night_hrs ?? 8;
    },
    markers() {
      return this.setupData?.markers || {};
    },
    totalCycle() {
      return (this.dayHrs || 0) + (this.nightHrs || 0);
    },
    isNight() {
      if (!this.totalCycle) return false;
      return (this.timeOfDay % this.totalCycle) >= this.dayHrs;
    },
  },

  mounted() {
    this.wsStore.connect();
  },

  methods: {
    toggleLeft() {
      this.panelLeftOpen = !this.panelLeftOpen;
      if (this.panelLeftOpen) this.panelRightOpen = false
    },
    toggleRight() {
      this.panelRightOpen = !this.panelRightOpen;
      if (this.panelRightOpen) this.panelLeftOpen = false
    },
  },
};

</script>

<template>
  <div class="map-container">
    <template v-if="ready">
      <MapComponent
        :roverPosition="roverPosition"
        :pathPlan="pathPlan"
        :mapMatrix="mapMatrix"
        :mined="minedCells"
      />

      <div v-if="isNight" class="night-overlay" aria-hidden="true"></div>

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

      <div class="instruments-anchor">
        <RoverInstruments
          :rover-speed="roverSpeed"
          :rover-status="roverStatus"
          :rover-battery="roverBattery"
          :max-speed="6"
        />
      </div>
    </template>

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
