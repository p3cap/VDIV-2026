<script>
import MapComponent from "@/components/MapComponent.vue";

export default {
  name: "MapTestPage",
  components: { MapComponent },

  data() {
    return {
      dashboard: null,
      setupData: null,
      polling: null,
    };
  },

  methods: {
    async fetchData() {
      try {
        const [setupResponse, dataResponse] = await Promise.all([
          fetch("http://127.0.0.1:8000/get_setup"),
          fetch("http://127.0.0.1:8000/get_data"),
        ]);

        if (!setupResponse.ok || !dataResponse.ok) throw new Error("Hálózati hiba");

        const [setup, data] = await Promise.all([
          setupResponse.json(),
          dataResponse.json(),
        ]);

        this.setupData = setup;
        this.dashboard = data;
        console.log("Frissítve:", data.rover_position);
      } catch (err) {
        console.error("Hiba a setup/live adatok lekérésekor:", err);
      }
    },
  },

  mounted() {
    this.fetchData();
    this.polling = setInterval(this.fetchData, 1000);
  },

  beforeUnmount() {
    clearInterval(this.polling);
  },
};
</script>

<template>
  <div class="map-container">
    <MapComponent
      v-if="dashboard && setupData?.map_matrix?.length"
      :roverPosition="dashboard.rover_position"
      :pathPlan="dashboard.path_plan"
      :mapMatrix="setupData.map_matrix"
    />
    <div v-else class="loader">Kapcsolódás a szerverhez...</div>
  </div>
</template>

<style scoped>
h1 {
  text-align: center;
  margin-bottom: 16px;
  color: #e2703a;
}

.loader {
  text-align: center;
  padding: 50px;
}
.map-container{
  display: flex;
  flex-direction: row;
  width: 100vw;
  height: 100vh;
  align-items: center;
  justify-content: center;
}
</style>
