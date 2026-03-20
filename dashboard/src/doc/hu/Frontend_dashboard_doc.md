# Frontend (Dashboard) – áttekintés

A vizualizáció Vite + Vue 3 alapú, amely valós idejű adatokat jelenít meg FastAPI WebSocketen keresztül. A nézetek külön oldalakon vannak, a globális adatfolyamot Pinia store kezeli.

## Fő működés röviden
1. Az app belépési pontja `dashboard/src/main.js`, itt indul a Vue app, a router és a Pinia.
2. Az `App.vue` egy globális `router-view`-t és reszponzív navigációt ad (desktop sidebar + mobil navbar).
3. A valós idejű adatok a `liveWs` store-ban futnak: WebSocket kapcsolat `ws://127.0.0.1:8000/ws`, auto-reconnecttel.
4. A nézetek a store-ból olvasnak, és props-on keresztül adják tovább a komponenseknek.

## Oldalak (Views)
- `WelcomePage.vue`: üdvözlő/landing oldal kártyákkal és modalokkal.
- `Map2dPage.vue`: 2D térkép PixiJS-sel. A map + rover pozíció + útvonal a store-ból, texture-pack váltóval (default/pixelart/minecraft), éjszakai overlay-jel és HUD panelek kapcsolásával.
- `DashboardPage.vue`: statisztikák, grafikonok. uPlot chartok + saját SVG/Canvas elemek (battery ív, cargo pie, mined scatter), LIVE/OFFLINE jelzés `isConnected` alapján.
- `Map3dPage.vue`: 3D térkép Three.js-szel, HUD és műszerek overlayként, részletes vezérléssel (egér/keyboard/touch), nappal–éj ciklussal, státusz‑fénnyel és path‑tube útvonallal.
- `DocumentationPage.vue`: beépített dokumentációs nézet (markdown betöltés `dashboard/src/doc/{hu,en}` alól), külön HU/EN váltóval és dinamikus docs-navigációval.

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
- `NavPhoneComponent.vue`: mobil navigáció.
- `SettingsComponent.vue`: bővithető nyelvváltó popup (nem külön oldal, a sidebarból nyílik).

## Használt libraryk
- `vue` – UI framework, komponensek és reaktív state.
- `vue-router` – oldal-navigáció és route alapú oldalak.
- `pinia` – globális state management (`liveWs` store).
- `pixi.js` – 2D térkép renderelés (sprite-ok, textúrák, canvas).
- `pixi-viewport` – pan/zoom/drag vezérlés a 2D térképen.
- `three` – 3D térkép renderelés (scene, camera, mesh, fények).
- `uplot` – könnyű, gyors line chartok a dashboardon.
- `animejs` – sidebar és welcome oldal animációk.
- `lucide-vue-next` – ikonok a navigációhoz.
- `marked` – markdown -> HTML konverzió a dokumentációs nézethez.
- `github-markdown-css` – markdown stílusok a dokumentációs nézethez.
- `echarts` – telepítve, de jelenleg nincs aktív használat (legacy / későbbi chartok).
- `@tresjs/core`, `@tresjs/cientos` – telepítve, de jelenleg nincs aktív használat (Three.js wrapper).



## Telepítés és futtatás

### Függőségek telepítése
`python setup/setup_deps.py`
### Szerver futtatása
`python setup/run_dev.py`


### Node verzió
- Ajánlott: `node` `^20.19.0` vagy `>=22.12.0`
