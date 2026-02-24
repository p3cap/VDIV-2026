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
    // setup adatok egyszer - map
    async fetchSetup() {
      try {
        const response = await fetch("http://127.0.0.1:8000/get_setup");
        if (!response.ok) throw new Error("Hálózati hiba");

        const data = await response.json();
        this.setupData = data;
      } catch (err) {
        console.error("Hiba a setup adatok lekérésekor:", err);
      }
    },

    async fetchData() {
      try {
        const response = await fetch("http://127.0.0.1:8000/get_data");
        if (!response.ok) throw new Error("Hálózati hiba");

        const data = await response.json();
        this.dashboard = data;
        console.log("Frissítve:", data.rover_position);
      } catch (err) {
        console.error("Hiba az adatok lekérésekor:", err);
      }
    },
  },

  async mounted() {
    await this.fetchSetup();
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
    <h1>Mars térkép haha</h1>

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
</style>
