# Frontend (Dashboard) – Overview

The visualization is built with Vite + Vue 3 and displays real-time data via a FastAPI WebSocket. Views are separated into pages, and the global data flow is managed by a Pinia store.

## Core Operation (Short Overview)
1. The entry point of the app is `dashboard/src/main.js`, where the Vue app, router, and Pinia are initialized.
2. `App.vue` provides a global `router-view` and responsive navigation (desktop sidebar + mobile navbar).
3. Real-time data runs in the `liveWs` store: WebSocket connection `ws://127.0.0.1:8000/ws` with auto-reconnect.
4. Views read from the store and pass the data to components via props.

## Pages (Views)
- `MapPage.vue`: 2D map using PixiJS. The map, rover position, and path come from the store.
- `DashboardPage.vue`: statistics and charts. uPlot charts + custom SVG/Canvas elements.
- `Map3dPage.vue`: 3D map using Three.js with HUD and instrument overlays.
- `WelcomePage.vue`: a welcome page with general information.

## Data Flow and State
- `stores/liveWs.js`
  - handles `snapshot`, `setup`, `live`, and `mined` packets
  - `connect()` with auto-reconnect logic
  - UI states are built from `dashboard`, `setupData`, and `mined`

## Components
- `MapComponent.vue`: PixiJS + pixi-viewport, 2D grid rendering, rover animation, path drawing.
- `Map3DComponent.vue`: Three.js, custom geometries, lights, camera controls, path tube rendering.
- `RoverHud.vue`: pure presentational overlay for the 3D view.
- `RoverInstruments.vue`: instruments (speed, status, battery).
- `NavComponent.vue`: animejs-animated icon sidebar.
- `NavbarPhoneComponent.vue`: mobile navigation.
- `ChartComponent.vue`: ECharts wrapper (optional, reusable).
- `HeatMap.vue`: ECharts heatmap for map matrix visualization.
- `SettingsComponent.vue`: Settings (to be continued).

## Libraries Used (actually used in the code)
- `vue` – UI framework
- `vue-router` – page navigation
- `pinia` – state management
- `pixi.js`, `pixi-viewport` – 2D map rendering
- `three` – 3D map rendering
- `uplot` – performance-friendly, dynamic charts
- `echarts` – heatmaps / general charts
- `animejs` – animations
- `lucide-vue-next` – icons

## Installation and Running

### macOS / Linux
- Install dependencies: `python3 setup_deps.py`
- Run the server: `python3 run_dev_win.py`

### Windows
- Install dependencies: `python setup_deps.py`
- Run the server: `python run_dev_win.py`