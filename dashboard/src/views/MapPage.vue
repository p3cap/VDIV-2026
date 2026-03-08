<script>
import MapComponent from "@/components/MapComponent.vue";
import marsMap from "@/data/marsMap.json";

export default {
  name: "MapTestPage",
  components: { MapComponent },

  data() {
    return {
      dashboard: null,
      setupData: null,
      fallbackMapMatrix: marsMap.grid || [],
      ws: null,
      reconnectTimer: null,
      isUnmounting: false,
    };
  },

  computed: {
    mapMatrixToRender() {
      return this.setupData?.map_matrix?.length
        ? this.setupData.map_matrix
        : this.fallbackMapMatrix;
    },
    roverPositionToRender() {
      return this.dashboard?.rover_position || { x: 0, y: 0 };
    },
    pathPlanToRender() {
      return this.dashboard?.path_plan || [];
    },
    isUsingFallbackMap() {
      return !this.setupData?.map_matrix?.length;
    },
  },

  methods: {
    handlePacket(packet) {
      if (!packet || typeof packet !== "object") return;

      const { type, payload } = packet;

      if (type === "snapshot" && payload) {
        if (payload.setup) this.setupData = payload.setup;
        if (payload.live) this.dashboard = payload.live;
        return;
      }

      if (type === "setup" && payload) {
        this.setupData = payload;
        return;
      }

      if (type === "live" && payload) {
        this.dashboard = payload;
      }
    },

    connectWebSocket() {
      this.ws = new WebSocket("ws://127.0.0.1:8000/ws");

      this.ws.onopen = () => {
        console.log("WebSocket connected.");
      };

      this.ws.onmessage = (event) => {
        try {
          const packet = JSON.parse(event.data);
          this.handlePacket(packet);
        } catch (err) {
          console.error("Invalid WebSocket JSON packet:", err);
        }
      };

      this.ws.onerror = (err) => {
        console.error("WebSocket error:", err);
      };

      this.ws.onclose = () => {
        this.ws = null;
        if (!this.isUnmounting && !this.reconnectTimer) {
          this.reconnectTimer = setTimeout(() => {
            this.reconnectTimer = null;
            this.connectWebSocket();
          }, 1500);
        }
      };
    },
  },

  mounted() {
    this.connectWebSocket();
  },

  beforeUnmount() {
    this.isUnmounting = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  },
};
</script>

<template>
  <div class="map-container">
    <MapComponent
      v-if="mapMatrixToRender.length"
      :roverPosition="roverPositionToRender"
      :pathPlan="pathPlanToRender"
      :mapMatrix="mapMatrixToRender"
    />
    <div v-else class="loader">Map data is not available yet.</div>
    <div v-if="isUsingFallbackMap" class="hint">
      Showing local map fallback. Start rover/server data stream for live map setup.
    </div>
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

.hint {
  position: absolute;
  bottom: 16px;
  left: 16px;
  padding: 8px 12px;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.7);
  color: #d6d6d6;
  font-size: 12px;
}

.map-container {
  position: relative;
  display: flex;
  flex-direction: row;
  width: 100vw;
  height: 100vh;
  align-items: center;
  justify-content: center;
}
</style>
