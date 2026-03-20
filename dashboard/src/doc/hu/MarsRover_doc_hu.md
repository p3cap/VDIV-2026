# Mars Rover dokumentáció

## Koncepció
A Mars-járó modul egy kis Python szimulációs csomag. Tartalmazza a rover logikáját, a térképet, az idő/nappal–éjszaka szimulációt, valamint egy világkezelő réteget, amely képes az egész rendszert léptetni, és opcionálisan élő adatokat küldeni a dashboardnak/szervernek.

---

## Fő komponensek

### 🚗 Rover osztály
A fő, vezérelhető rover objektum.

#### Konstruktor paraméterek
- `id`: rover neve / azonosítója `[str]`
- `sim`: aktív szimulációs objektum `[Simulation]`
- `map_csv_path`: opcionális térkép elérési útvonal `[str | None]`

#### Enum típusok
- `STATUS`: `MINE`, `IDLE`, `MOVE`, `DEAD`  
  → A rover aktuális állapota  
- `GEARS`: `SLOW`, `NORMAL`, `FAST`  
  → Mozgási sebesség előbeállítások  

#### Fontos változók
- `battery`: aktuális akkumulátortöltöttség `[float]`
- `status`: aktuális állapot `[STATUS]`
- `pos`: aktuális pozíció `[Vector2]`
- `start_pos`: kezdőpozíció `[Vector2]`
- `path`: tervezett útvonal `[Vector2 list]`
- `gear`: aktuális sebességfokozat `[GEARS]`
- `move_progress`: előrehaladás a következő lépés felé `[float]`
- `mine_process_hrs`: hátralévő bányászati idő `[float]`
- `storage`: begyűjtött ásványok `[dict[str, int]]`
- `distance_travelled`: megtett távolság mezőkben `[int]`
- `mined`: kibányászott koordináták listája `[list]`

#### Függvények
- `movement_cost(self, delta_hrs: float)`  
  → Mozgás energiaigénye adott időintervallumban
- `energy_consumed(self, delta_hrs: float)`  
  → Energiafogyasztás az aktuális állapot alapján
- `energy_produced(self, delta_hrs: float)`  
  → Nappali töltésből származó energia
- `path_find_to(self, goal: Vector2)`  
  → Útvonaltervezés célponthoz
- `mine(self)`  
  → Bányászat indítása
- `mine_finished(self)`  
  → Bányászat lezárása
- `update(self, delta_hrs: float)`  
  → Állapot frissítése (folyamatosan hívandó)
- `get_live_data(self, delta_hrs: float)`  
  → Élő adatok lekérése
- `get_setup_data(self)`  
  → Statikus konfigurációs adatok

---

### 🗺️ Map osztály
Rácsalapú Mars térkép.

#### Konstruktor paraméterek
- `map_data`: 2D térkép mátrix `[list[list[str]]]`
- `path_marker`: járható mező `[str]`
- `barrier_marker`: akadály `[str]`
- `rover_marker`: kezdőpozíció `[str]`
- `mineral_markers`: ásvány mezők `[list[str]]`

#### Fontos változók
- `map_data`: teljes térkép `[list[list[str]]]`
- `width`: szélesség `[int]`
- `height`: magasság `[int]`
- `path_marker`: járható mező
- `barrier_marker`: akadály
- `rover_marker`: kezdőpont
- `mineral_markers`: ásvány típusok
- `marker_descriptions`: jelölők leírásai `[dict[str, str]]`

#### Függvények
- `get_poses_of_tiles(self, tile_names: list[str], limit: int = -1)`  
  → Adott típusú mezők pozíciói
- `get_tile(self, position: Vector2)`  
  → Mező lekérdezése
- `set_tile(self, position: Vector2, value: str)`  
  → Mező módosítása
- `is_valid_pos(self, pos: Vector2)`  
  → Érvényes pozíció ellenőrzése

---

### ⏱️ Simulation osztály
Idő- és nappal/éjszaka ciklus kezelése.

#### Konstruktor paraméterek
- `map_obj`: aktív térkép `[Map]`
- `run_hrs`: teljes futási idő `[float]`
- `sim_time_multiplier`: szimuláció sebesség `[float]`
- `day_hrs`: nappal hossza `[float]`
- `night_hrs`: éjszaka hossza `[float]`

#### Fontos változók
- `map_obj`: térkép
- `run_hrs`: teljes futási idő
- `elapsed_hrs`: eltelt idő
- `day_hrs`: nappal hossza
- `night_hrs`: éjszaka hossza
- `is_day`: nappal/éjszaka állapot `[bool]`
- `is_running`: fut-e a szimuláció `[bool]`

#### Függvények
- `update(self, delta_hrs: float)`  
  → Idő előrehaladása
- `get_daytime_in_interval(self, start_hrs: float, end_hrs: float)`  
  → Nappali idő kiszámítása adott intervallumban

---

### 🌍 RoverSimulationWorld osztály
Magas szintű vezérlő az egész szimulációhoz.

#### Konstruktor paraméterek
- `run_hrs`: teljes futási idő `[float]`
- `delta_mode`: léptetési mód `[str]`
- `set_delta_hrs`: fix lépésméret `[float]`
- `tick_seconds`: várakozási idő lépések között `[float]`
- `env_speed`: valós idejű sebesség szorzó `[float]`
- `web_logger`: adatküldés engedélyezése `[bool]`
- `base_url`: szerver URL `[str]`
- `send_every`: adatküldés gyakorisága `[int]`
- `map_csv_path`: egyedi térkép `[str | None]`

#### Fontos változók
- `sim`: aktuális szimuláció `[Simulation]`
- `rover`: aktuális rover `[Rover]`
- `map_path`: térkép fájl útvonal `[Path]`
- `map_template`: alap térkép `[list[list[str]]]`
- `last_send_ok`: utolsó küldés eredménye `[bool | None]`

#### Függvények
- `reset(self)`  
  → Teljes rendszer újraindítása
- `step(self, sleep: bool = False)`  
  → Egy lépés végrehajtása
- `minerals(self)`  
  → Aktuális ásványok lekérdezése
- `close(self)`  
  → Logger kapcsolat lezárása