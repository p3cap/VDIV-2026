# Frontend (Dashboard) – áttekintés

A vizualizáció Vite + Vue 3 alapú , amely valós idejű adatokat jelenít meg FastAPI WebSocketen keresztül. A nézetek külön oldalakon vannak, a globális adatfolyamot Pinia store kezeli.

## Fő működés röviden
1. Az app belépési pontja `dashboard/src/main.js`, itt indul a Vue app, a router és a Pinia.
2. Az `App.vue` egy globális `router-view`-t és reszponzív navigációt ad (desktop sidebar + mobil navbar).
3. A valós idejű adatok a `liveWs` store-ban futnak: WebSocket kapcsolat `ws://127.0.0.1:8000/ws`, auto-reconnecttel.
4. A nézetek a store-ból olvasnak, és props-on keresztül adják tovább a komponenseknek.

## Oldalak (Views)
- `MapPage.vue`: 2D térkép PixiJS-sel. A map  + rover pozíció + útvonal a store-ból.
- `DashboardPage.vue`: statisztikák, grafikonok. uPlot chartok + saját SVG/Canvas elemek.
- `Map3dPage.vue`: 3D térkép Three.js-szel, HUD és műszerek overlayként.
- `WelcomePage.vue`: egy üdvözlő oldal általános adatokkal.

## Adatfolyam és state
- `stores/liveWs.js`
  - kezeli a `snapshot`, `setup`, `live`, `mined` csomagokat
  - `connect()` auto-reconnect logikával
  - `dashboard`, `setupData`, `mined` állapotokból épülnek a UI-k

## Komponensek
- `MapComponent.vue`: PixiJS + pixi-viewport, 2D grid render, rover animáció, útvonal rajzolás.
- `Map3DComponent.vue`: Three.js, egyedi geometriák, fények, kamera-vezérlés, útvonal cső.
- `RoverHud.vue`: tiszta presentational overlay a 3D nézethez.
- `RoverInstruments.vue`: műszerek (sebesség, állapot, akku).
- `NavComponent.vue`: animejs animált, ikonos sidebar.
- `NavbarPhoneComponent.vue`: mobil navigáció.
- `ChartComponent.vue`: ECharts wrapper (opciós, több helyen használható).
- `HeatMap.vue`: ECharts heatmap, map mátrix 
vizualizáció.
- `SettingsComponent.vue`: Beállítások folytatni kell !!!!.
## Használt libraryk (a kódban ténylegesen)
- `vue` – UI framework
- `vue-router` – oldal-navigáció
- `pinia` – state management
- `pixi.js`, `pixi-viewport` – 2D térkép renderelés
- `three` – 3D térkép renderelés
- `uplot` – teljesítménybarát vonaldiagramok
- `echarts` – heatmap / általános chartok
- `animejs` – animációk
- `lucide-vue-next` – ikonok

## Telepítés és futtatás

### macOS / linux:
- Függőségek telepítése: `python3 setup_deps.py`
- Szerver futtatása: `python3 run_dev_win.py`

### Windows:
- Függőségek telepítése: `python setup_deps.py`
- Szerver futtatása: `python run_dev_win.py`

```