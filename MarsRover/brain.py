"""
Mars Rover – kombinált stratégia
Vadász Dénes Informatika Verseny 2026

Ez a verzió a calud.py és brain.py kombinációja.

Fő elv:
1. Először BIZTONSÁG:
   - csak olyan cél választható,
     amihez van út,
     odaérünk,
     kibányásszuk,
     és még vissza is tudunk jutni a bázisra.

2. Utána OPTIMALIZÁLÁS:
   - a biztonságos célok közül pontozással választunk:
     - távolság
     - menetidő
     - várható akku
     - klaszter sűrűség
     - klaszterben maradás bónusza

3. Ha már jó klaszterben vagyunk:
   - lehetőleg ott maradunk,
   - amíg a környéken még van érc,
   - és biztonságos a további kitermelés.

4. Ha kevés az idő vagy az akku:
   - hazamegyünk.

5. Plusz javítások:
   - max speed = 3 fixen
   - mozgás közben dinamikus gear
   - bányászáskor mindig 1-es
   - közeli ércek előnyben
   - klaszter elhagyás előtt helyi takarítás
"""

from math import ceil
from pathlib import Path
import argparse
from typing import Optional
from urllib.parse import urlparse

from Simulation_env import RoverSimulationWorld
from RoverClass import STATUS, GEARS
from Global import Vector2
from RoverLogger import RoverLogger

# ---------------------------------------------------------
# Optional C++ A* backend
# ---------------------------------------------------------
# Ha a pybind11-es C++ modul elérhető, azt használjuk útkeresésre.
# Ha nem, akkor üres path-et adunk vissza.
try:
    import cpp_path as cpp_mod
    CPP_AVAILABLE = True
except Exception:
    cpp_mod = None
    CPP_AVAILABLE = False

# ---------------------------------------------------------
# Alap path / url beállítások
# ---------------------------------------------------------
MARS_ROOT = Path(__file__).resolve().parent
DEFAULT_MAP_NAME = "mars_map_50x50.csv"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"

BASE_URL = DEFAULT_BASE_URL
CSV_PATH = str(MARS_ROOT / "data" / DEFAULT_MAP_NAME)

# ---------------------------------------------------------
# Szimuláció paraméterek
# ---------------------------------------------------------
delta_mode = "set_time"
delta_hrs = 0.5          # 1 tick = 0.5 óra
tick_seconds = 1
env_speed = 1.0
send_every = 1
run_hrs = 240.0

USE_SERVER = True

# ---------------------------------------------------------
# Globális world referenciák
# ---------------------------------------------------------
Sim = None
rover = None
sim = None
map_obj = None
logger = None

# ---------------------------------------------------------
# Bázis pozíció
# ---------------------------------------------------------
# JAVÍTVA:
# nem fix (0,0), hanem a térképen az S mezőből fogjuk kiolvasni
BASE_POS = None

# ---------------------------------------------------------
# Max / min speed
# ---------------------------------------------------------
MIN_SPEED = 1
MAX_SPEED = 3

# ---------------------------------------------------------
# Érc értékek
# ---------------------------------------------------------
# Most mindegyik 1 pontot ér, de később könnyű bővíteni.
ORE_VALUES = {
    "Y": 1,
    "G": 1,
    "B": 1,
}

# ---------------------------------------------------------
# Energiamodell
# ---------------------------------------------------------
# Feladat szerint:
# - mozgás: 2 * v^2 / tick
# - nappali töltés: +10 / tick
# - bányászás: 2 / tick
# - standby: 1 / tick
BATTERY_CAP = 100
ENERGY_K = 2
DAY_CHARGE = 10
MINE_COST = 2
STANDBY_COST = 1

# ---------------------------------------------------------
# Biztonsági tartalékok
# ---------------------------------------------------------
# Nappal kisebb tartalék is elég, mert töltődik.
# Éjjel nagyobb kell, mert nincs töltés.
DAY_RESERVE = 5
NIGHT_RESERVE = 15

# ---------------------------------------------------------
# Visszaút biztonsági szorzó
# ---------------------------------------------------------
# Egy kis extra margó, hogy ne pont nullára számoljunk.
RETURN_MARGIN = 1.10

# ---------------------------------------------------------
# Ha ennyi tick van már csak hátra, befejezzük a kitermelést és hazamegyünk
# ---------------------------------------------------------
END_TICKS = 30

# ---------------------------------------------------------
# Klaszter paraméterek
# ---------------------------------------------------------
# Klaszter sugár: ezen belül tekintjük az érceket "egy környéknek"
CLUSTER_RADIUS = 10

# Sűrű klaszter bonus
DENSE_CLUSTER_BONUS = 18

# Ha már egy klaszterben vagyunk, ezt a plusz pontot kapják a helyi célok
CLUSTER_STICKINESS = 40

# ---------------------------------------------------------
# Helyi takarítás sugár
# ---------------------------------------------------------
# Ha ide beérünk egy klaszterbe, először a közeli érceket takarítjuk ki.
LOCAL_CLEANUP_RADIUS = 2

# ---------------------------------------------------------
# Path cache
# ---------------------------------------------------------
# Ugyanazt az útvonalat ne számoljuk ki újra és újra.
_path_cache = {}

# =========================================================
# ARGPARSE / INIT
# =========================================================

def _normalize_base_url(raw: str, fallback: str) -> str:
    """
    A base url normalizálása.

    Példák:
      127.0.0.1:8000  -> http://127.0.0.1:8000
      ws://...        -> http://...
      wss://...       -> https://...
    """
    raw = (raw or "").strip()
    if not raw:
        return fallback

    parsed = urlparse(raw)

    if not parsed.scheme:
        raw = f"http://{raw}"
        parsed = urlparse(raw)

    scheme = parsed.scheme.lower()

    if scheme == "ws":
        scheme = "http"
    elif scheme == "wss":
        scheme = "https"

    host = parsed.netloc or parsed.path
    if not host:
        return fallback

    return f"{scheme}://{host}"


def _resolve_map_path(map_csv_path: Optional[str]) -> Path:
    """
    Térkép csv helyének feloldása.

    Először:
      - user által megadott path

    Aztán:
      - projekt/data/mars_map_50x50.csv

    Végül:
      - project parent / Data / CSV_maps / ...
    """
    if map_csv_path:
        candidate = Path(map_csv_path)
        if candidate.exists():
            return candidate

    default_path = MARS_ROOT / "data" / DEFAULT_MAP_NAME
    if default_path.exists():
        return default_path

    fallback = MARS_ROOT.parent / "Data" / "CSV_maps" / DEFAULT_MAP_NAME
    if fallback.exists():
        return fallback

    if map_csv_path:
        raise FileNotFoundError(f"map csv not found: {map_csv_path}")

    raise FileNotFoundError(f"default map csv not found: {default_path}")


def parse_args():
    """
    Parancssori argumentumok beolvasása.
    """
    parser = argparse.ArgumentParser(description="Combined safe + cluster rover runner.")

    parser.add_argument("--run-hrs", type=float, default=run_hrs)
    parser.add_argument("--delta-mode", type=str, default=delta_mode, choices=["set_time", "real_time"])
    parser.add_argument("--delta-hrs", type=float, default=delta_hrs)
    parser.add_argument("--tick-seconds", type=float, default=tick_seconds)
    parser.add_argument("--env-speed", type=float, default=env_speed)
    parser.add_argument("--send-every", type=int, default=send_every)
    parser.add_argument("--base-url", type=str, default=BASE_URL)
    parser.add_argument("--map-csv", type=str, default=None)
    parser.add_argument("--use-server", dest="use_server", action="store_true", default=USE_SERVER)
    parser.add_argument("--no-server", dest="use_server", action="store_false")

    return parser.parse_args()


def find_base_pos():
    """
    JAVÍTVA:
    A bázis pozícióját a térképen lévő 'S' mezőből keressük ki.
    Ha valamiért nincs S, fallbackként a rover aktuális pozíciója,
    végső esetben (0,0).
    """
    if map_obj is not None and hasattr(map_obj, "map_data"):
        for y, row in enumerate(map_obj.map_data):
            for x, tile in enumerate(row):
                if tile == "S":
                    return (x, y)

    if rover is not None and hasattr(rover, "pos"):
        return (int(rover.pos.x), int(rover.pos.y))

    return (0, 0)


def init_world(args):
    """
    A teljes world / sim inicializálása a parse_args eredménye alapján.
    """
    global BASE_URL, CSV_PATH, delta_mode, delta_hrs, tick_seconds
    global env_speed, send_every, run_hrs, USE_SERVER
    global Sim, rover, sim, map_obj, logger, BASE_POS

    run_hrs = float(args.run_hrs)
    delta_mode = args.delta_mode
    delta_hrs = float(args.delta_hrs)
    tick_seconds = float(args.tick_seconds)
    env_speed = float(args.env_speed)
    send_every = int(args.send_every)
    USE_SERVER = bool(args.use_server)

    BASE_URL = _normalize_base_url(args.base_url, DEFAULT_BASE_URL)
    CSV_PATH = str(_resolve_map_path(args.map_csv))

    Sim = RoverSimulationWorld(
        run_hrs=run_hrs,
        delta_mode=delta_mode,
        set_delta_hrs=delta_hrs,
        tick_seconds=tick_seconds,
        env_speed=env_speed,
        web_logger=False,
        base_url=BASE_URL,
        send_every=send_every,
        map_csv_path=CSV_PATH,
    )

    rover = Sim.rover
    sim = Sim.sim
    map_obj = Sim.sim.map_obj

    # JAVÍTVA:
    # a bázist az S mezőből vesszük
    BASE_POS = find_base_pos()

    # Kezdőpozíció a bázis
    rover.pos = Vector2(BASE_POS[0], BASE_POS[1])

    logger = RoverLogger(BASE_URL) if USE_SERVER else None

# =========================================================
# GEAR SEGÉD
# =========================================================

def clamp_speed(speed) -> int:
    """
    Biztosítja, hogy a speed mindig 1..3 között maradjon.
    """
    try:
        speed = int(speed)
    except Exception:
        speed = 1

    if speed < MIN_SPEED:
        return MIN_SPEED

    if speed > MAX_SPEED:
        return MAX_SPEED

    return speed


def _enum_members(enum_cls):
    """
    Biztonságos enum olvasás.
    Ha van __members__, abból lekérjük.
    """
    if hasattr(enum_cls, "__members__"):
        return {k.upper(): v for k, v in enum_cls.__members__.items()}
    return {}


GEAR_MEMBERS = _enum_members(GEARS)

# Sebesség -> GEARS enum
GEAR_BY_SPEED = {}
for speed, name in [(1, "SLOW"), (2, "NORMAL"), (3, "FAST")]:
    gear = GEAR_MEMBERS.get(name)
    if gear is None:
        raise ValueError(f"GEARS enum nem tartalmazza ezt a tag-et: {name}")
    GEAR_BY_SPEED[speed] = gear


def set_gear(speed: int):
    """
    A rover sebességének megfelelő gear beállítása.
    """
    speed = clamp_speed(speed)

    gear = GEAR_BY_SPEED.get(speed)
    if gear is None:
        raise ValueError(f"Nincs gear ehhez a speed-hez: {speed}")

    rover.gear = gear


def current_speed() -> int:
    """
    A rover jelenlegi gear-jéből visszaadja a sebesség értéket.
    """
    for speed, gear in GEAR_BY_SPEED.items():
        if rover.gear == gear:
            return clamp_speed(speed)
    return 2

# =========================================================
# REFRESH / IDŐ SEGÉDEK
# =========================================================

def refresh_refs():
    """
    Tick után frissítjük a referenciákat.
    """
    global rover, sim, map_obj
    rover = Sim.rover
    sim = Sim.sim
    map_obj = Sim.sim.map_obj


def elapsed_hrs():
    """
    Eddig eltelt órák száma.
    """
    for obj, attr in [
        (Sim, "elapsed_hrs"),
        (sim, "elapsed_hrs"),
        (Sim, "elapsed_hours"),
        (sim, "elapsed_hours"),
    ]:
        if hasattr(obj, attr):
            return float(getattr(obj, attr))
    return 0.0


def time_of_day():
    """
    JAVÍTVA:
    Aktuális napszak-idő lekérése.
    Több helyről is megpróbáljuk olvasni.

    Ha a sim valamiért nem frissíti jól a time_of_day értéket,
    fallbackként az eltelt órából számoljuk:
        elapsed_hrs() % 24
    Mivel a rover napfelkeltekor indul, ez jó közelítés.
    """
    for obj, attr in [
        (Sim, "time_of_day"),
        (sim, "time_of_day"),
        (map_obj, "time_of_day"),
    ]:
        if hasattr(obj, attr):
            try:
                value = getattr(obj, attr)
                if value is not None:
                    v = float(value)
                    # ha ténylegesen változik, használjuk
                    if v != 0.0 or elapsed_hrs() == 0.0:
                        return v % 24.0
            except Exception:
                pass

    return float(elapsed_hrs()) % 24.0


def remaining_ticks() -> int:
    """
    Még hátralévő tickek száma.
    """
    return int(max(0.0, run_hrs - elapsed_hrs()) / delta_hrs)


def is_day() -> bool:
    """
    Nappal akkor van, ha a 24 órás cikluson belül 0-16 közt vagyunk.
    """
    return (time_of_day() % 24.0) < 16.0


def reserve() -> float:
    """
    Aktuális minimum tartalék.
    Nappal kisebb, éjjel nagyobb.
    """
    return DAY_RESERVE if is_day() else NIGHT_RESERVE

# =========================================================
# ENERGIA SZÁMÍTÁS
# =========================================================

def move_cost(speed: int) -> float:
    """
    Bruttó mozgási fogyasztás 1 tickre.
    Képlet: 2 * v^2
    """
    speed = clamp_speed(speed)
    return float(ENERGY_K * speed * speed)


def net_move(speed: int, daytime: bool) -> float:
    """
    Nettó energiamérleg mozgás közben 1 tickre.

    Pozitív:
      merül

    Negatív:
      összességében töltődik
    """
    return move_cost(speed) - (DAY_CHARGE if daytime else 0)


def net_mine(daytime: bool) -> float:
    """
    Nettó energiamérleg bányászás közben 1 tickre.
    """
    return float(MINE_COST) - (DAY_CHARGE if daytime else 0)


def ticks_needed(dist_blocks: int, speed: int) -> int:
    """
    Hány tick kell egy adott távolság megtételéhez adott sebességgel.
    """
    speed = clamp_speed(speed)
    return ceil(dist_blocks / speed)


def battery_after_trip_and_mine(current_battery: float, dist_blocks: int, speed: int, daytime: bool) -> float:
    """
    Megbecsli mennyi akku marad:
    - az odaút után
    - plusz 1 tick bányászás után
    """
    speed = clamp_speed(speed)
    move_ticks = ticks_needed(dist_blocks, speed)
    delta = net_move(speed, daytime) * move_ticks + net_mine(daytime)
    after = current_battery - delta

    # Akku clamp
    after = max(0.0, min(BATTERY_CAP, after))
    return after


def energy_for_return(dist_to_base: int, daytime: bool) -> float:
    """
    Mennyi akku kell a hazajutáshoz.

    Nappal:
      sokkal könnyebb, mert töltődik is.
      Itt konzervatívan csak a reserve-et kérjük.

    Éjjel:
      v=1-gyel konzervatív becslés:
      tickenként nettó +2 a mozgás.
    """
    if daytime:
        return reserve()

    t = ceil(dist_to_base * RETURN_MARGIN)
    return 2.0 * t + reserve()


def safe_to_go(current_battery: float, ore_dist: int, base_from_ore: int, speed: int, daytime: bool) -> bool:
    """
    Hard safety check.

    Igaz, ha:
    - odaér
    - kibányássza
    - és utána még marad annyi akkumulátor, hogy biztonságosan visszajusson
    """
    speed = clamp_speed(speed)
    after = battery_after_trip_and_mine(current_battery, ore_dist, speed, daytime)
    need_back = energy_for_return(base_from_ore, daytime)

    return after >= need_back

# =========================================================
# C++ A* / PATH
# =========================================================

def astar(start_xy, goal_xy):
    """
    Cached A* útvonal lekérés.
    """
    key = (start_xy, goal_xy)

    if key in _path_cache:
        return _path_cache[key]

    result = []

    if CPP_AVAILABLE:
        try:
            result = cpp_mod.astar_from_csv(CSV_PATH, start_xy, goal_xy)
        except Exception as e:
            print("A* hiba:", e)

    _path_cache[key] = result
    return result


def path_dist(start_xy, goal_xy):
    """
    A két pont közti blokk távolság A* path alapján.
    Ha nincs útvonal, None.
    """
    if start_xy == goal_xy:
        return 0

    path = astar(start_xy, goal_xy)
    if not path:
        return None

    return len(path) - 1


def get_path_and_dist(start_xy, goal_xy):
    """
    Visszaadja:
    - path
    - dist
    """
    if start_xy == goal_xy:
        return [start_xy], 0

    path = astar(start_xy, goal_xy)

    if not path:
        return [], None

    return path, len(path) - 1

# =========================================================
# MAP / ORE SEGÉDEK
# =========================================================

def get_all_ores():
    """
    Beolvassa az összes ércet a térképről.
    """
    ores = []

    for y, row in enumerate(map_obj.map_data):
        for x, tile in enumerate(row):
            if tile in ORE_VALUES:
                ores.append({
                    "pos": (x, y),
                    "type": tile,
                    "value": ORE_VALUES[tile],
                })

    return ores


def remove_ore(ores, pos_xy):
    """
    A kibányászott érc eltávolítása az aktív listából.
    """
    for i, ore in enumerate(ores):
        if ore["pos"] == pos_xy:
            ores.pop(i)
            return True
    return False


def ore_at_pos(ores, pos_xy):
    """
    Visszaadja az adott pozíción lévő ércet, ha van.
    """
    for ore in ores:
        if ore["pos"] == pos_xy:
            return ore
    return None

# =========================================================
# KLASZTER SEGÉDEK
# =========================================================

def chebyshev_dist(a_xy, b_xy):
    """
    Diagonális mozgás miatt a klaszter közelséghez jó közelítés a Chebyshev-távolság.
    """
    return max(abs(a_xy[0] - b_xy[0]), abs(a_xy[1] - b_xy[1]))


def cluster_bonus(target_ore, ores, radius=CLUSTER_RADIUS):
    """
    Megnézi, hány másik érc van a cél körül a megadott sugaron belül.
    """
    tx, ty = target_ore["pos"]
    bonus = 0

    for ore in ores:
        if ore["pos"] == target_ore["pos"]:
            continue

        ox, oy = ore["pos"]
        if max(abs(tx - ox), abs(ty - oy)) <= radius:
            bonus += 1

    return bonus


def ores_near_anchor(ores, anchor_xy, radius=CLUSTER_RADIUS):
    """
    Az anchor körüli ércek kigyűjtése.
    """
    if anchor_xy is None:
        return []

    result = []

    for ore in ores:
        if chebyshev_dist(ore["pos"], anchor_xy) <= radius:
            result.append(ore)

    return result


def should_keep_local_harvest(ores, cluster_anchor):
    """
    Megmondja, hogy érdemes-e még a jelenlegi klaszterben maradni.
    """
    if cluster_anchor is None:
        return False

    local = ores_near_anchor(ores, cluster_anchor, radius=CLUSTER_RADIUS)
    return len(local) > 0


def ores_near_position(ores, pos_xy, radius=LOCAL_CLEANUP_RADIUS):
    """
    Aktuális pozícióhoz közeli ércek kigyűjtése.
    Ez segít, hogy ne hagyja ott a közvetlen közelben lévő érceket.
    """
    result = []

    for ore in ores:
        if chebyshev_dist(ore["pos"], pos_xy) <= radius:
            result.append(ore)

    return result


def pick_immediate_adjacent_ore(current_pos_xy, ores):
    """
    Ha a roveren vagy közvetlenül mellette van érc,
    azt azonnal vegyük előre.

    Ez javítja:
    - ne menjen át érceken
    - ne hagyjon ott közeli érceket
    """
    close = ores_near_position(ores, current_pos_xy, radius=1)
    if not close:
        return None

    best = None
    best_dist = None

    for ore in close:
        d = path_dist(current_pos_xy, ore["pos"])
        if d is None:
            continue

        if best is None or d < best_dist:
            best = ore
            best_dist = d

    return best

# =========================================================
# SEBESSÉGVÁLASZTÁS
# =========================================================

def choose_best_safe_speed(dist_to_target: int, current_battery: float, dist_target_to_base: int, daytime: bool):
    """
    Dinamikus, biztonságos sebességválasztó.

    Nem csak azt nézi, hogy mi a leggyorsabb,
    hanem hogy:
    - elérjük-e a célt
    - kibányásszuk-e
    - visszaérünk-e a bázisra
    - mennyire éri meg az adott sebesség most
    """
    best = None

    for speed in range(MAX_SPEED, MIN_SPEED - 1, -1):
        speed = clamp_speed(speed)

        # Hard safety: csak biztonságos sebesség maradhat bent
        if not safe_to_go(current_battery, dist_to_target, dist_target_to_base, speed, daytime):
            continue

        after_battery = battery_after_trip_and_mine(current_battery, dist_to_target, speed, daytime)
        move_ticks = ticks_needed(dist_to_target, speed)

        utility = 0.0

        # Maradjon akku
        utility += after_battery * 0.9

        # Kevesebb tick jobb
        utility -= move_ticks * 3.5

        # Nappali preferencia
        if daytime:
            if speed == 2:
                utility += 6
            elif speed == 3 and dist_to_target >= 8 and current_battery >= 70:
                utility += 5
            elif speed == 1 and dist_to_target <= 2:
                utility += 2

        # Éjszakai preferencia
        else:
            if speed == 1:
                utility += 10
            elif speed == 2 and dist_to_target <= 4 and current_battery >= 60:
                utility += 2
            elif speed == 3:
                utility -= 8

        # Ha már nagyon közel van a cél, ne akarjon feleslegesen gyors lenni
        if dist_to_target <= 2:
            if speed == 1:
                utility += 5
            elif speed == 3:
                utility -= 5

        # Ha nagyon kevés az akku, óvatosabb legyen
        if current_battery < 25:
            if speed == 1:
                utility += 8
            elif speed == 2:
                utility += 1
            elif speed == 3:
                utility -= 10

        if best is None or utility > best["utility"]:
            best = {
                "speed": clamp_speed(speed),
                "after_battery": after_battery,
                "move_ticks": move_ticks,
                "utility": utility,
            }

    return best


def choose_live_speed(current_pos_xy, target_xy, current_battery):
    """
    Mozgás közben, tickenként újra eldönti a megfelelő sebességet.

    Ez a kulcs ahhoz, hogy ne ragadjon be egy gear-be.
    """
    daytime = is_day()

    dist_to_target = path_dist(current_pos_xy, target_xy)
    if dist_to_target is None:
        return 1

    dist_target_to_base = path_dist(target_xy, BASE_POS)
    if dist_target_to_base is None:
        return 1

    plan = choose_best_safe_speed(
        dist_to_target=dist_to_target,
        current_battery=current_battery,
        dist_target_to_base=dist_target_to_base,
        daytime=daytime,
    )

    if plan is None:
        return 1

    return clamp_speed(plan["speed"])

# =========================================================
# CANDIDATE ÉPÍTÉS
# =========================================================

def build_candidate(current_pos_xy, ore, current_battery, all_ores, cluster_anchor=None):
    """
    Egy adott ércből candidate objektumot készít.

    Lépések:
    1. megnézzük van-e path oda
    2. megnézzük van-e path onnan a bázisra
    3. kiválasztjuk a legjobb BIZTONSÁGOS sebességet
    4. kiszámoljuk a score-t
    """
    daytime = is_day()

    # Path a rover jelenlegi helyéről az ércig
    path_to_ore, dist_to_ore = get_path_and_dist(current_pos_xy, ore["pos"])
    if dist_to_ore is None:
        return None

    # Path az érctől a bázisig
    _, dist_ore_to_base = get_path_and_dist(ore["pos"], BASE_POS)
    if dist_ore_to_base is None:
        return None

    # Legjobb biztonságos speed kiválasztása
    speed_plan = choose_best_safe_speed(
        dist_to_target=dist_to_ore,
        current_battery=current_battery,
        dist_target_to_base=dist_ore_to_base,
        daytime=daytime,
    )

    if speed_plan is None:
        return None

    # Klaszter sűrűség
    local_cluster_bonus = cluster_bonus(ore, all_ores, radius=CLUSTER_RADIUS)

    # Ha az aktuális klaszterben van, kap plusz pontot
    staying_bonus = 0
    if cluster_anchor is not None and chebyshev_dist(ore["pos"], cluster_anchor) <= CLUSTER_RADIUS:
        staying_bonus = CLUSTER_STICKINESS

    # Közeli takarítás bónusz
    # Ha nagyon közel van hozzánk, ezt erősen preferáljuk.
    near_bonus = 0
    if chebyshev_dist(ore["pos"], current_pos_xy) <= LOCAL_CLEANUP_RADIUS:
        near_bonus = 60

    # Score kiszámítása
    score = 0.0

    # Érc érték
    score += ore["value"] * 100.0

    # Klaszter sűrűség
    score += local_cluster_bonus * DENSE_CLUSTER_BONUS

    # Klaszterben maradás
    score += staying_bonus

    # Közeli takarítás
    score += near_bonus

    # Várható maradék akku
    score += speed_plan["after_battery"] * 0.6

    # Távolság büntetés
    score -= dist_to_ore * 3.5

    # Tick költség büntetés
    score -= speed_plan["move_ticks"] * 4.0

    # A bázistól nagyon messzi cél kapjon kis büntetést
    score -= dist_ore_to_base * 1.5

    return {
        "ore": ore,
        "path": path_to_ore,
        "dist": dist_to_ore,
        "base_dist": dist_ore_to_base,
        "speed": speed_plan["speed"],
        "after_battery": speed_plan["after_battery"],
        "move_ticks": speed_plan["move_ticks"],
        "cluster_bonus": local_cluster_bonus,
        "staying_bonus": staying_bonus,
        "score": score,
    }

# =========================================================
# CÉLVÁLASZTÁS
# =========================================================

def choose_best_global_ore(current_pos_xy, ores, current_battery, cluster_anchor=None):
    """
    Globális célválasztás az összes érc közül.

    Csak a biztonságos candidate-ek maradnak bent,
    és azok közül a legjobb score győz.
    """
    candidates = []

    for ore in ores:
        cand = build_candidate(
            current_pos_xy=current_pos_xy,
            ore=ore,
            current_battery=current_battery,
            all_ores=ores,
            cluster_anchor=cluster_anchor,
        )

        if cand is not None:
            candidates.append(cand)

    if not candidates:
        return None

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates[0]


def choose_best_local_ore(current_pos_xy, local_ores, current_battery, all_ores, cluster_anchor):
    """
    Ha már van aktív klaszterünk, akkor csak a helyi ércek közül választunk.
    """
    candidates = []

    for ore in local_ores:
        cand = build_candidate(
            current_pos_xy=current_pos_xy,
            ore=ore,
            current_battery=current_battery,
            all_ores=all_ores,
            cluster_anchor=cluster_anchor,
        )

        if cand is not None:
            candidates.append(cand)

    if not candidates:
        return None

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates[0]


def choose_target(current_pos_xy, ores, current_battery, cluster_anchor=None):
    """
    Kombinált célválasztás.

    Prioritás:
    1. ha közvetlen közelben van érc, azt azonnal vegyük
    2. ha van aktív klaszter, előbb abból válasszunk
    3. ha nincs, globális választás
    """
    # -------------------------------------------------
    # 1. Közvetlen közeli érc mindig előnyt élvez
    # -------------------------------------------------
    immediate = pick_immediate_adjacent_ore(current_pos_xy, ores)
    if immediate is not None:
        immediate_candidate = build_candidate(
            current_pos_xy=current_pos_xy,
            ore=immediate,
            current_battery=current_battery,
            all_ores=ores,
            cluster_anchor=cluster_anchor,
        )
        if immediate_candidate is not None:
            return immediate_candidate

    # -------------------------------------------------
    # 2. Ha van aktív klaszter, abból próbálunk választani
    # -------------------------------------------------
    if should_keep_local_harvest(ores, cluster_anchor):
        local_ores = ores_near_anchor(ores, cluster_anchor, radius=CLUSTER_RADIUS)

        # Először a nagyon közeli helyi érceket takarítsuk ki
        very_local = ores_near_position(local_ores, current_pos_xy, radius=LOCAL_CLEANUP_RADIUS)

        if very_local:
            best_local_cleanup = choose_best_local_ore(
                current_pos_xy=current_pos_xy,
                local_ores=very_local,
                current_battery=current_battery,
                all_ores=ores,
                cluster_anchor=cluster_anchor,
            )
            if best_local_cleanup is not None:
                return best_local_cleanup

        best_local = choose_best_local_ore(
            current_pos_xy=current_pos_xy,
            local_ores=local_ores,
            current_battery=current_battery,
            all_ores=ores,
            cluster_anchor=cluster_anchor,
        )

        if best_local is not None:
            return best_local

    # -------------------------------------------------
    # 3. Ha nincs értelmes lokális cél, globálisan választunk
    # -------------------------------------------------
    return choose_best_global_ore(
        current_pos_xy=current_pos_xy,
        ores=ores,
        current_battery=current_battery,
        cluster_anchor=cluster_anchor,
    )

# =========================================================
# BACKEND / LOGGER
# =========================================================

def send_setup():
    """
    Kezdeti setup adatok elküldése a backendnek.
    """
    if not USE_SERVER or logger is None:
        return

    try:
        logger.send_setup({"map_matrix": map_obj.map_data})
    except Exception as e:
        print("send_setup hiba:", e)


def send_live_data(current_target=None, planned_path=None):
    """
    Live állapot küldése a backendnek / front-endnek.
    """
    if not USE_SERVER or logger is None:
        return

    try:
        # -------------------------------------------------
        # Storage kigyűjtés
        # -------------------------------------------------
        storage = {"Y": 0, "G": 0, "B": 0}

        for attr in ("storage", "inventory", "mined_ores"):
            value = getattr(rover, attr, None)
            if isinstance(value, dict):
                storage = value
                break

        # -------------------------------------------------
        # Fogyasztás / termelés
        # -------------------------------------------------
        daytime = is_day()

        if rover.status == STATUS.MINE:
            consumption = MINE_COST
        elif rover.status == STATUS.MOVE:
            consumption = move_cost(current_speed())
        else:
            consumption = STANDBY_COST

        production = DAY_CHARGE if daytime else 0

        # -------------------------------------------------
        # Kibányászott koordináták normalizálása
        # -------------------------------------------------
        raw_mined = getattr(rover, "mined", [])
        rover_mined = []

        if raw_mined:
            if isinstance(raw_mined[0], dict):
                rover_mined = raw_mined
            else:
                for m in raw_mined:
                    if hasattr(m, "x") and hasattr(m, "y"):
                        rover_mined.append({"x": int(m.x), "y": int(m.y)})
                    else:
                        rover_mined.append({"x": int(m[0]), "y": int(m[1])})

        payload = {
            "time_of_day": float(time_of_day()),
            "elapsed_hrs": float(elapsed_hrs()),
            "rover_position": {
                "x": int(rover.pos.x),
                "y": int(rover.pos.y),
            },
            "rover_battery": float(rover.battery),
            "rover_storage": {
                "B": int(storage.get("B", 0)),
                "Y": int(storage.get("Y", 0)),
                "G": int(storage.get("G", 0)),
            },
            "rover_speed": int(current_speed()),
            "rover_status": (
                "mine" if rover.status == STATUS.MINE else
                "move" if rover.status == STATUS.MOVE else
                "idle" if rover.status == STATUS.IDLE else
                "dead" if rover.status == STATUS.DEAD else
                "unknown"
            ),
            "rover_distance_travelled": float(getattr(rover, "distance_travelled", 0)),
            "rover_path_plan": (
                [{"x": int(x), "y": int(y)} for x, y in planned_path]
                if planned_path is not None else []
            ),
            "current_target": (
                {"x": int(current_target[0]), "y": int(current_target[1])}
                if current_target else None
            ),
            "rover_energy_consumption": float(consumption),
            "rover_energy_produce": float(production),
            "rover_mined": rover_mined,
        }

        logger.send_live(payload)

    except Exception as e:
        print("send_live_data hiba:", type(e).__name__, str(e))

# =========================================================
# WORLD STEP
# =========================================================

def world_step(current_target=None, planned_path=None):
    """
    Egy teljes world step:
    - ref frissítés
    - Sim.step()
    - ref frissítés
    - live adatküldés
    """
    refresh_refs()
    Sim.step(sleep=True)
    refresh_refs()
    send_live_data(current_target=current_target, planned_path=planned_path)

# =========================================================
# MOZGÁS
# =========================================================

def move_to(target_xy, path, initial_speed):
    """
    Dinamikus mozgás a célhoz.

    Javítások:
    - nem ragad egy gear-be
    - max speed = 3
    - közel a célhoz visszavesz 1-esbe
    - bármikor újraszámolható a live speed
    """
    plan = [{"x": int(p[0]), "y": int(p[1])} for p in path] if path else []

    remaining = list(path)

    # ha a path eleje az aktuális pozíció, levágjuk
    if remaining and (remaining[0][0], remaining[0][1]) == (rover.pos.x, rover.pos.y):
        remaining = remaining[1:]

    timeout = 5000

    while remaining:
        current_pos = (rover.pos.x, rover.pos.y)

        # Ha menet közben már haza kell menni, megszakíthatjuk
        if must_go_home(current_pos, rover.battery) and target_xy != BASE_POS:
            print("Mozgás közben haza kell fordulni.")
            return False

        # tickenként új gear választás
        live_speed = choose_live_speed(
            current_pos_xy=current_pos,
            target_xy=target_xy,
            current_battery=rover.battery,
        )

        live_speed = clamp_speed(live_speed)

        # ha már nagyon közel a cél, inkább finoman közelítsünk
        dist_now = path_dist(current_pos, target_xy)
        if dist_now is not None and dist_now <= 2:
            live_speed = 1

        set_gear(live_speed)

        # a következő tick alatt maximum live_speed blokkot akarunk menni
        step_count = min(live_speed, len(remaining))
        step_end = remaining[step_count - 1]
        step_target = (step_end[0], step_end[1])

        rover.path_find_to(Vector2(step_target[0], step_target[1]))
        world_step(current_target=target_xy, planned_path=path)

        if rover.battery <= 0:
            print("Lemerült mozgás közben.")
            return False

        rover_pos = (rover.pos.x, rover.pos.y)

        # levágjuk az útból a már bejárt részt
        while remaining and (remaining[0][0], remaining[0][1]) == rover_pos:
            remaining = remaining[1:]

        if remaining:
            idx = None
            for i, p in enumerate(remaining):
                if (p[0], p[1]) == rover_pos:
                    idx = i
                    break
            if idx is not None:
                remaining = remaining[idx + 1:]

        timeout -= 1
        if timeout <= 0:
            print("Mozgás timeout.")
            return False

    # végső biztosítás
    if rover.pos.x != target_xy[0] or rover.pos.y != target_xy[1]:
        set_gear(1)
        rover.path_find_to(Vector2(target_xy[0], target_xy[1]))
        world_step(current_target=target_xy, planned_path=path)

    return True

# =========================================================
# BÁNYÁSZÁS
# =========================================================

def mine_here(target_xy, path):
    """
    Bányászás közben mindig 1-es gear-t használunk.

    Ennek az oka:
    - bányászásnál nincs értelme gyors fokozatban maradni
    - a következő indulás előtt majd úgyis újra választunk sebességet
    """
    set_gear(1)
    rover.mine()

    waited = 0
    stuck = 0
    last_status = rover.status
    timeout = 5000

    while rover.status == STATUS.MINE:
        # bányászás alatt is fixen 1-es
        set_gear(1)

        world_step(current_target=target_xy, planned_path=path)

        if rover.battery <= 0:
            print("Lemerült bányászás közben.")
            return False

        waited += 1

        if waited > 3:
            if rover.status == last_status:
                stuck += 1
            else:
                stuck = 0

        last_status = rover.status

        if stuck >= 20:
            print("A bányászás beragadt.")
            return False

        timeout -= 1
        if timeout <= 0:
            print("Bányászás timeout.")
            return False

    return True

# =========================================================
# HAZATÉRÉS
# =========================================================

def go_home(reason=""):
    """
    Hazavezeti a rovert a bázisra.

    Ha már otthon van:
      - csak várakozunk / töltünk egy kicsit

    Ha nincs otthon:
      - A* útvonal a bázisra
      - a legjobb biztonságos speed kiválasztása
      - visszamenés
    """
    print(f"Hazafelé indulás. Ok: {reason}")

    current_pos = (rover.pos.x, rover.pos.y)

    if current_pos != BASE_POS:
        path_home = astar(current_pos, BASE_POS)

        if not path_home:
            print("Nincs út haza.")
            return False

        dist_home = len(path_home) - 1

        # Hazafelé már nincs további cél, csak menjünk haza biztonságosan
        speed_plan = choose_best_safe_speed(
            dist_to_target=dist_home,
            current_battery=rover.battery,
            dist_target_to_base=0,
            daytime=is_day(),
        )

        start_speed = speed_plan["speed"] if speed_plan is not None else 1

        ok = move_to(BASE_POS, path_home, start_speed)
        if not ok:
            return False

    # Otthon egy kicsit feltöltünk
    waited = 0
    while rover.battery < 80 and waited < 400:
        set_gear(1)
        world_step(current_target=None, planned_path=[])
        waited += 1

    print(f"Hazaértünk. Akku: {rover.battery:.1f}")
    return True


def must_go_home(current_pos_xy, current_battery: float) -> bool:
    """
    Eldönti, hogy most azonnal haza kell-e menni.

    Fő esetek:
    - kevés idő van már hátra
    - kevés az akku a biztonságos visszatéréshez
    """
    dist_home = path_dist(current_pos_xy, BASE_POS)

    if dist_home is None:
        return False

    # Ha a szimuláció a vége felé jár, ne kezdjünk új célba
    if remaining_ticks() <= END_TICKS:
        return True

    # Ha az aktuális akku már közel van a minimálisan szükséges hazatéréshez
    need_back = energy_for_return(dist_home, is_day())

    if current_battery <= need_back:
        print(f"Kevés akku, haza kell menni. bat={current_battery:.1f}, need={need_back:.1f}")
        return True

    return False

# =========================================================
# HELYI TAKARÍTÁS
# =========================================================

def cleanup_nearby_ores(ores, cluster_anchor):
    """
    Kibányászás után még kitakarítjuk a közvetlen környezetet,
    hogy ne hagyjuk ott a mellettünk lévő érceket.

    Ez külön javítja ezt a hibát:
    - "nem szedi ki a körülötte lévő összes ércet"
    """
    cleaned = 0

    while True:
        current_pos = (rover.pos.x, rover.pos.y)

        # Először a közvetlenül közeli érceket nézzük
        nearby = ores_near_position(ores, current_pos, radius=LOCAL_CLEANUP_RADIUS)

        if not nearby:
            break

        best_local = choose_best_local_ore(
            current_pos_xy=current_pos,
            local_ores=nearby,
            current_battery=rover.battery,
            all_ores=ores,
            cluster_anchor=cluster_anchor,
        )

        if best_local is None:
            break

        ok, _ = mine_one_target(ores, best_local)
        if not ok:
            break

        cleaned += 1

    return cleaned

# =========================================================
# EGY CÉL KIBÁNYÁSZÁSA
# =========================================================

def mine_one_target(ores, target_pack):
    """
    Egy teljes célkezelés:
    - odamegyünk
    - kibányásszuk
    - töröljük az ércet az aktív listából
    """
    target_ore = target_pack["ore"]
    target_xy = target_ore["pos"]
    path = target_pack["path"]
    speed = target_pack["speed"]

    print(
        f"-> cél: {target_xy} ({target_ore['type']}) | "
        f"dist={target_pack['dist']} | "
        f"base_dist={target_pack['base_dist']} | "
        f"speed={speed} | "
        f"cluster_bonus={target_pack['cluster_bonus']} | "
        f"stay_bonus={target_pack['staying_bonus']} | "
        f"score={target_pack['score']:.1f} | "
        f"akku_utána={target_pack['after_battery']:.1f} | "
        f"{'nap' if is_day() else 'éj'}"
    )

    send_live_data(current_target=target_xy, planned_path=path)

    # Ha már rajta állunk az érces mezőn, nem kell külön mozogni
    current_pos = (rover.pos.x, rover.pos.y)

    if current_pos != target_xy:
        ok_move = move_to(target_xy, path, speed)
        if not ok_move:
            return False, None

    # Bányászás
    ok_mine = mine_here(target_xy, path)
    if not ok_mine:
        return False, None

    # last_mined logoláshoz
    rover.last_mined = Vector2(target_xy[0], target_xy[1])

    # Ore eltávolítása a listából
    removed = remove_ore(ores, target_xy)
    if not removed:
        print("Figyelem: a kibányászott érc nem volt törölhető a listából:", target_xy)

    return True, target_xy

# =========================================================
# MAIN
# =========================================================

def main():
    """
    Fő vezérlő ciklus.
    """
    global BASE_POS

    args = parse_args()
    init_world(args)
    refresh_refs()

    # Induláskor összes érc beolvasása
    ores = get_all_ores()

    print(f"Talált ércek száma: {len(ores)}")
    print(f"Bázis pozíció: {BASE_POS}")
    print(f"Kezdő pozíció: {rover.pos.x}, {rover.pos.y}")
    print(f"Run hours: {run_hrs} | Tick hours: {delta_hrs} | Összes tick: {int(run_hrs / delta_hrs)}")
    print("Energiamodell:")
    for v in (1, 2, 3):
        print(
            f"  v={v} | brutto={move_cost(v):.0f}/tick | "
            f"nappal nettó={net_move(v, True):+.0f} | "
            f"éjjel nettó={net_move(v, False):+.0f}"
        )
    print()

    send_setup()
    send_live_data(current_target=None, planned_path=[])

    mined_count = 0

    # Aktív klaszter középpont
    # Ha találunk egy jó zónát, ide rögzítjük.
    cluster_anchor = None

    # Jelzi, hogy időlimit miatt már elindultunk haza
    went_home_for_end = False

    while rover.battery > 0 and ores:
        current_pos = (rover.pos.x, rover.pos.y)

        # -------------------------------------------------
        # Ha haza kell menni, ne kezdjünk új célba
        # -------------------------------------------------
        if must_go_home(current_pos, rover.battery):
            ok_home = go_home("akku vagy időlimit")
            if not ok_home:
                break

            if remaining_ticks() <= END_TICKS:
                went_home_for_end = True
                break

            # Ha hazaértünk, az aktív klasztert elengedjük
            cluster_anchor = None
            continue

        # -------------------------------------------------
        # Célválasztás
        # -------------------------------------------------
        best = choose_target(
            current_pos_xy=current_pos,
            ores=ores,
            current_battery=rover.battery,
            cluster_anchor=cluster_anchor,
        )

        # -------------------------------------------------
        # Ha nincs biztonságos cél
        # -------------------------------------------------
        if best is None:
            # Éjjel várhatunk, hátha nappal újra jobb lesz a helyzet
            if not is_day():
                print("Nincs biztonságos cél éjjel, várakozás nappalig...")
                set_gear(1)
                world_step(current_target=None, planned_path=[])
                continue

            print("Nincs több biztonságosan elérhető érc.")
            break

        # -------------------------------------------------
        # Ha még nincs aktív klaszter, az új cél lesz az anchor
        # -------------------------------------------------
        if cluster_anchor is None:
            cluster_anchor = best["ore"]["pos"]

        # -------------------------------------------------
        # Cél kibányászása
        # -------------------------------------------------
        ok, mined_xy = mine_one_target(ores, best)

        if not ok:
            print("A cél kibányászása sikertelen volt.")
            break

        mined_count += 1

        # -------------------------------------------------
        # Kibányászás után helyi takarítás
        # -------------------------------------------------
        cleaned_now = cleanup_nearby_ores(ores, cluster_anchor)
        mined_count += cleaned_now

        # -------------------------------------------------
        # Ha kiürült a klaszter, elengedjük
        # -------------------------------------------------
        if not should_keep_local_harvest(ores, cluster_anchor):
            cluster_anchor = None

        print(
            f"[{mined_count}] "
            f"akku={rover.battery:.1f} | "
            f"maradék_érc={len(ores)} | "
            f"hátralévő_tick={remaining_ticks()} | "
            f"{'nap' if is_day() else 'éj'}"
        )

    # -----------------------------------------------------
    # Szimuláció végén próbáljunk hazajutni
    # -----------------------------------------------------
    if not went_home_for_end:
        if (rover.pos.x, rover.pos.y) != BASE_POS:
            go_home("szimuláció vége")

    # -----------------------------------------------------
    # Végső storage összegzés
    # -----------------------------------------------------
    storage = {"Y": 0, "G": 0, "B": 0}
    for attr in ("storage", "inventory", "mined_ores"):
        value = getattr(rover, attr, None)
        if isinstance(value, dict):
            storage = value
            break

    # -----------------------------------------------------
    # Végső statisztika
    # -----------------------------------------------------
    print("\n" + "=" * 60)
    print("SZIMULÁCIÓ VÉGE")
    print("=" * 60)
    print(
        f"Kibányászott: {mined_count} | "
        f"B={storage.get('B', 0)} "
        f"Y={storage.get('Y', 0)} "
        f"G={storage.get('G', 0)}"
    )
    print(f"Megmaradt ércek: {len(ores)}")
    print(f"Végső akku: {rover.battery:.1f}")
    print(f"Eltelt idő: {elapsed_hrs():.1f} h")
    print(f"Path cache méret: {len(_path_cache)}")
    final_pos = (rover.pos.x, rover.pos.y)
    print(f"Bázison van: {'IGEN' if final_pos == BASE_POS else 'NEM'} | pozíció={final_pos}")
    print("=" * 60)

    # -----------------------------------------------------
    # Lezárás
    # -----------------------------------------------------
    try:
        if Sim is not None:
            Sim.close()
    except Exception:
        pass

    try:
        if logger is not None:
            logger.close()
    except Exception:
        pass


if __name__ == "__main__":
    main()