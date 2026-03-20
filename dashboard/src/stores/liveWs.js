import { defineStore } from "pinia";

export const useLiveWsStore = defineStore("liveWs", {
  state: () => ({
    dashboard: null,
    setupData: null,
    mined: [],
    ws: null,
    reconnectTimer: null,
    isUnmounting: false,
    isConnected: false,
  }),

  actions: {
    _normalizeLive(payload) {
      if (!payload || typeof payload !== "object") return payload;
      const p = { ...payload };

      // Normalize status strings to frontend-expected values.
      const rawStatus = String(p.rover_status ?? "").toLowerCase();
      const statusMap = {
        mining: "mine",
        mine: "mine",
        moving: "move",
        move: "move",
        idle: "idle",
        standby: "standby",
        charge: "charge",
        dead: "dead",
      };
      if (rawStatus) p.rover_status = statusMap[rawStatus] ?? rawStatus;

      // Normalize energy field name
      if (p.rover_energy_produce == null && p.rover_energy_production != null) {
        p.rover_energy_produce = p.rover_energy_production;
      }

      return p;
    },

    handlePacket(packet) {
      if (!packet || typeof packet !== "object") return;
      const { type, payload } = packet;

      if (type === "snapshot" && payload) {
        if (payload.setup) this.setupData = payload.setup;
        if (payload.live) {
          const live = this._normalizeLive(payload.live);
          this.dashboard = live;
          if (Array.isArray(live?.rover_mined)) this.mined = live.rover_mined;
        }
        if (payload.mined) this.mined = payload.mined;
        return;
      }
      if (type === "setup" && payload) this.setupData = payload;
      if (type === "live" && payload) {
        const live = this._normalizeLive(payload);
        this.dashboard = live;
        if (Array.isArray(live?.rover_mined)) this.mined = live.rover_mined;
      }
      if (type === "mined" && Array.isArray(payload)) {
        this.mined = payload;
      }
    },

    connect() {
      if (this.ws) return;
      this.isUnmounting = false;

      this.ws = new WebSocket("ws://127.0.0.1:8000/ws");

      this.ws.onopen = () => {
        this.isConnected = true;
      };

      this.ws.onmessage = (event) => {
        try {
          const packet = JSON.parse(event.data);
          this.handlePacket(packet);
        } catch (e) {
          console.error("Invalid WS packet", e);
        }
      };

      this.ws.onerror = (e) => {
        console.error("WS error", e);
      };

      this.ws.onclose = () => {
        this.isConnected = false;
        this.ws = null;
        if (!this.isUnmounting && !this.reconnectTimer) {
          this.reconnectTimer = setTimeout(() => {
            this.reconnectTimer = null;
            this.connect();
          }, 1500);
        }
      };
    },

    disconnect() {
      this.isUnmounting = true;
      if (this.reconnectTimer) {
        clearTimeout(this.reconnectTimer);
        this.reconnectTimer = null;
      }
      if (this.ws) {
        this.ws.close();
        this.ws = null;
      }
      this.isConnected = false;
    },
  },
});
