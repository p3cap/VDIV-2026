<script>
import MapComponent from "@/components/MapComponent.vue";

export default {
  name: "MapTestPage",
  components: { MapComponent },

  data() {
    return {
      dashboard: null, // Kezdetben üres
      polling: null,   // Itt tároljuk az időzítőt, hogy le tudjuk állítani
    };
  },

  methods: {
    async fetchData() {
      try {
        const response = await fetch("http://127.0.0.1:8000/get_data");
        if (!response.ok) throw new Error("Hálózati hiba");
        
        const data = await response.json();
        this.dashboard = data; // A Vue reaktivitása miatt a térkép azonnal frissül!
        console.log("Frissítve:", data.rover_position);
      } catch (err) {
        console.error("Hiba az adatok lekérésekor:", err);
      }
    }
  },

  mounted() {
    // Első lekérés azonnal
    this.fetchData();
    // Utána 2 másodpercenként
    this.polling = setInterval(this.fetchData, 1000);
  },

  beforeUnmount() {
    // Fontos: ha elnavigálunk az oldalról, állítsuk le a lekérést!
    clearInterval(this.polling);
  }
};
</script>
<template>
  <div class="map-container">
    <h1>Mars térkép haha</h1>

    <MapComponent
      v-if="dashboard"
      :roverPosition="dashboard.rover_position"
      :pathPlan="dashboard.path_plan"
    />
    <div v-else class="loader">Kapcsolódás a szerverhez...</div>
  </div>

</template>
<style scoped>
h1 {
  text-align: center;
  margin-bottom: 16px;
  color: #e2703a; /* Marsi narancs */
}
.loader {
  text-align: center;
  padding: 50px;
}
</style>