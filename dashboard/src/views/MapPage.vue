<script>
import { useLiveWsStore } from "@/stores/liveWs.js";
import MapComponent from "@/components/MapComponent.vue";

export default {
  name: "MapTestPage",
  components: { MapComponent },

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
  },

  mounted() {
    this.wsStore.connect();
  },
};
</script>

<template>
  <div class="map-container">
    <MapComponent
      v-if="setupData?.map_matrix?.length && dashboard?.rover_position"
      :roverPosition="dashboard.rover_position || { x: 0, y: 0 }"
      :pathPlan="dashboard.rover_path_plan || []"
      :mapMatrix="setupData.map_matrix"
      :mined = "dashboard.rover_mined || []"
    />
    <div v-else class="loader">Kapcsolodas a szerverhez...</div>
  </div>
</template>

<style scoped>
.loader {
  text-align: center;
  padding: 50px;
}
.map-container {
  display: flex;
  flex-direction: row;
  width: 100vw;
  height: 100vh;
  align-items: center;
  justify-content: center;
}
</style>
