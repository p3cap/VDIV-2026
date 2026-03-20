# Szerver dokumentáció

## Koncepció
A szerver egy kis FastAPI alapú backend, amely a rover oldal és a dashboard között helyezkedik el.  
Eltárolja a legfrissebb konfigurációs (setup) és élő rover adatokat, HTTP-n keresztül elérhetővé teszi őket, valamint WebSocketen keresztül valós időben továbbítja a frissítéseket.

---

## Fő komponensek

### ⚙️ FastAPI alkalmazás
A backend központi objektuma.

#### Feladatai
- HTTP és WebSocket kommunikáció kezelése
- A legfrissebb rover állapot memóriában tárolása
- Új setup/live adatok broadcastolása a csatlakozott klienseknek

#### Tárolt adatok
- `latest_data`: legfrissebb élő rover adat `[dict[str, Any]]`
- `setup_data`: legfrissebb konfiguráció `[dict[str, Any]]`

---

### 🔌 ConnectionManager osztály
Egyszerű kapcsolatkezelő az aktív WebSocket kliensekhez.

#### Fontos változók
- `connections`: aktív kapcsolatok `[list[WebSocket]]`

#### Függvények
- `connect(self, ws: WebSocket)`  
  → WebSocket kapcsolat elfogadása és tárolása
- `disconnect(self, ws: WebSocket)`  
  → Kapcsolat eltávolítása
- `send(self, ws: WebSocket, data: dict[str, Any])`  
  → Egy JSON csomag küldése egy kliensnek
- `broadcast(self, data: dict[str, Any], exclude: WebSocket | None = None)`  
  → Üzenet küldése minden kliensnek (opcionálisan egy kivételével)

---

## 🌐 HTTP végpontok

- `GET /get_data`  
  → Legfrissebb élő rover adatok lekérése

- `GET /get_setup`  
  → Legfrissebb konfiguráció lekérése

- `POST /send_data`  
  → Élő rover adat frissítése és broadcast (`live` esemény)

- `POST /send_setup`  
  → Setup adat frissítése és broadcast (`setup` esemény)

---

## 🔄 WebSocket végpont

- `WS /ws`

#### Funkciók
- Dashboard és adatküldő kliensek csatlakoztatása
- Csatlakozás után azonnali `snapshot` küldése
- `ping` → `pong` válasz
- `snapshot` kérés → aktuális állapot visszaküldése
- JSON üzenetek fogadása (`type` + `payload`)

#### Támogatott üzenettípusok
- `live` / `publish_live`  
  → Élő rover adat frissítése + broadcast

- `setup` / `publish_setup`  
  → Konfiguráció frissítése + broadcast

---

## Fő függvények

- `get_data()`  
  → HTTP handler az élő adatokhoz

- `get_setup()`  
  → HTTP handler a setup adatokhoz

- `send_data(data)`  
  → Élő adatok mentése és broadcast

- `send_setup(data)`  
  → Setup adatok mentése és broadcast

- `ws_endpoint(ws)`  
  → WebSocket handler (snapshot, ping, frissítések kezelése)