<script setup>
import { computed, onBeforeUnmount, onMounted } from "vue";
import Map3DComponent from "@/components/Map3DComponent.vue";
import { useLiveWsStore } from "@/stores/liveWs";

const wsStore = useLiveWsStore();

const dashboard = computed(() => wsStore.dashboard);
const setupData = computed(() => wsStore.setupData);

onMounted(() => {
  wsStore.connect();
});

onBeforeUnmount(() => {
  wsStore.disconnect();
});
</script>

<template>
  <div class="page">
    <Map3DComponent
      v-if="setupData?.map_matrix?.length && dashboard?.rover_position"
      :roverPosition="dashboard.rover_position || { x: 0, y: 0 }"
      :pathPlan="dashboard.path_plan || []"
      :mapMatrix="setupData.map_matrix"
    />
    <div v-else class="loader">Kapcsolodas a szerverhez...</div>
  </div>
</template>

<style scoped>
.page {
  width: 100vw;
  height: 100vh;
}

.loader {
  width: 100%;
  height: 100%;
  display: grid;
  place-items: center;
}
</style>
