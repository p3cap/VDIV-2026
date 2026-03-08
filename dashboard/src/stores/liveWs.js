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
    handlePacket(packet) {
      if (!packet || typeof packet !== "object") return;
      const { type, payload } = packet;

      if (type === "snapshot" && payload) {
        if (payload.setup) this.setupData = payload.setup;
        if (payload.live) this.dashboard = payload.live;
        if (payload.mined) this.mined.push(...payload.mined); // <-- add mined tiles
        return;
      }
      if (type === "setup" && payload) this.setupData = payload;
      if (type === "live" && payload) this.dashboard = payload;
      if (type === "mined" && Array.isArray(payload)) {
        this.mined.push(...payload); // <-- append new mined tiles reactively
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