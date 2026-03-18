# Frontend (Dashboard) – Overview

The visualization is built with Vite + Vue 3 and displays real-time data via a FastAPI WebSocket. Views are separated into pages, and the global data flow is managed by a Pinia store.

## Core Operation (Short Overview)
1. The entry point of the app is `dashboard/src/main.js`, where the Vue app, router, and Pinia are initialized.
2. `App.vue` provides a global `router-view` and responsive navigation (desktop sidebar + mobile navbar).
3. Real-time data runs in the `liveWs` store: WebSocket connection `ws://127.0.0.1:8000/ws` with auto-reconnect.
4. Views read from the store and pass the data to components via props.

## Pages (Views)
- `WelcomePage.vue`: landing page with cards and modals.
- `Map2dPage.vue`: 2D map using PixiJS. The map, rover position, and path come from the store.
- `DashboardPage.vue`: statistics and charts. uPlot charts + custom SVG/Canvas elements.
- `Map3dPage.vue`: 3D map using Three.js with HUD and instrument overlays.
- `DocumentationPage.vue`: in-app docs view (markdown loaded from `dashboard/src/doc/{hu,en}`).
- `SettingsComponent.vue`: settings (currently a placeholder).

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
- `NavPhoneComponent.vue`: mobile navigation.
- `RoverStatsComponent.vue`: placeholder.
- `SettingsComponent.vue`: placeholder.

## Libraries Used (actually used in the code)
- `vue` – UI framework, components and reactive state.
- `vue-router` – page navigation and route-based views.
- `pinia` – global state management (`liveWs` store).
- `pixi.js` – 2D map rendering (sprites, textures, canvas).
- `pixi-viewport` – pan/zoom/drag controls for the 2D map.
- `three` – 3D map rendering (scene, camera, meshes, lights).
- `uplot` – lightweight, fast line charts on the dashboard.
- `animejs` – sidebar and welcome page animations.
- `lucide-vue-next` – icon set for navigation.
- `marked` – markdown -> HTML conversion for the docs view.
- `github-markdown-css` – markdown styling for the docs view.

## Installed but currently unused
- `echarts` – no active usage in the frontend (legacy / planned charts).
- `@tresjs/core`, `@tresjs/cientos` – no active usage (Three.js wrapper).

## Installation and Running

### macOS / Linux
- Install dependencies: `python3 setup/setup_deps.py`
- Run the server: `python3 setup/run_dev.py`

### Windows
- Install dependencies: `python setup/setup_deps.py`
- Run the server: `python setup/run_dev_win.py`

### Node version
- Recommended: `node` `^20.19.0` or `>=22.12.0`
