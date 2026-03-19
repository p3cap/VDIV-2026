"""
Mars Rover – Vadász Dénes Informatika Verseny 2026

Energiamodell (1 tick = fél óra):
  v=1: 2/tick bruttó  | nappal: -8 nettó (töltődik) | éjjel: +2
  v=2: 8/tick bruttó  | nappal: -2 nettó (töltődik) | éjjel: +8
  v=3: 18/tick bruttó | nappal: +8 nettó (merül)    | éjjel: +18
  Nappal töltés: +10/tick
  Bányászás: 2/tick, 1 tick
  Standby: 1/tick

JAVÍTÁSOK:
  1. move_to – gear igazítása a maradék lépésszámhoz:
       Ha csak 1 blokk maradt → gear=1 (SLOW, 2 energia)
       Ha csak 2 blokk maradt → gear=2 (NORMAL, 8 energia)
       Ha 3+ blokk maradt    → a tervezett speed marad
     Ez megakadályozza hogy pl. 1 blokknyi mozgásért 18 energiát vonjon le.

  2. Klaszter logika – choose_ore klasztert is figyelembe vesz:
       Minden jelölt érc körül CLUSTER_RADIUS-on belüli szomszédokat számol.
       score = ticks - neighbor_count × CLUSTER_BONUS
       Kisebb score = vonzóbb cél → klasztereket preferálja.

  3. send_live mined – saját _mined_log lista:
       rover.mined megbízhatatlan (nem mindig frissül).
       mine_here() sikeres bányászás után log_mined()-et hív,
       ami a saját _mined_log listába írja az adatot.
       send_live() ezt a listát küldi a dashboardnak.
       
  4. mine_here – gear visszaállítása 1-re bányászás előtt:
       Álló rovernél nincs értelme 3-as geart tartani.
"""

from math import ceil

from Simulation_env import RoverSimulationWorld
from RoverClass import STATUS, GEARS
from Global import Vector2
from RoverLogger import RoverLogger

try:
    import cpp_path as cpp_mod
    CPP_AVAILABLE = True
except Exception:
    cpp_mod = None
    CPP_AVAILABLE = False

# ═══════════════════════════════════════
# KONFIGURÁCIÓ
# ═══════════════════════════════════════

BASE_URL     = "http://127.0.0.1:8000"
logger       = RoverLogger(BASE_URL)
CSV_PATH     = r"MarsRover/data/mars_map_50x50.csv"

delta_mode   = "set_time"
delta_hrs    = 0.5
tick_seconds = 1
env_speed    = 1.0
send_every   = 1
run_hrs      = 240.0
USE_SERVER   = True

BASE_POS = (0, 0)

# Energiamodell
BATTERY_CAP  = 100
ENERGY_K     = 2
DAY_CHARGE   = 10
MINE_COST    = 2
STANDBY_COST = 1

# Biztonsági tartalékok
DAY_RESERVE   = 5
NIGHT_RESERVE = 15
RETURN_MARGIN = 1.1
END_TICKS     = 30

# Klaszter konfiguráció
CLUSTER_RADIUS = 5    # ekkora körön belüli ércek számítanak klaszternek
CLUSTER_BONUS  = 2    # ennyivel csökkenti a score-t minden extra szomszéd

ORE_VALUES = {"Y": 1, "G": 1, "B": 1}

# Saját mined log – rover.mined helyett ezt használjuk
_mined_log = []

# ═══════════════════════════════════════
# SZIMULÁCIÓ
# ═══════════════════════════════════════

Sim = RoverSimulationWorld(
    run_hrs=run_hrs,
    delta_mode=delta_mode,
    set_delta_hrs=delta_hrs,
    tick_seconds=tick_seconds,
    env_speed=env_speed,
    web_logger=False,
    base_url=BASE_URL,
    send_every=send_every,
)

rover   = Sim.rover
sim     = Sim.sim
map_obj = Sim.sim.map_obj
rover.pos = Vector2(0, 0)

# ═══════════════════════════════════════
# GEAR
# ═══════════════════════════════════════

def _load_gears():
    members = {}
    if hasattr(GEARS, "__members__"):
        members = {k.upper(): v for k, v in GEARS.__members__.items()}
    result = {}
    for speed, name in [(1, "SLOW"), (2, "NORMAL"), (3, "FAST")]:
        g = members.get(name)
        if g is None:
            raise ValueError(f"GEARS enum hiányzik: {name}")
        result[speed] = g
    return result

GEAR_BY_SPEED = _load_gears()

def set_gear(speed):
    rover.gear = GEAR_BY_SPEED[speed]

def current_speed():
    for s, g in GEAR_BY_SPEED.items():
        if g == rover.gear:
            return s
    return 1

# ═══════════════════════════════════════
# IDŐ
# ═══════════════════════════════════════

def time_of_day():
    for obj, attr in [(Sim, "time_of_day"), (sim, "time_of_day"), (map_obj, "time_of_day")]:
        if hasattr(obj, attr):
            return float(getattr(obj, attr))
    return 0.0

def elapsed_hrs():
    for obj, attr in [(Sim, "elapsed_hrs"), (sim, "elapsed_hrs"),
                      (Sim, "elapsed_hours"), (sim, "elapsed_hours")]:
        if hasattr(obj, attr):
            return float(getattr(obj, attr))
    return 0.0

def remaining_ticks():
    return int(max(0.0, run_hrs - elapsed_hrs()) / delta_hrs)

def is_day():
    return (time_of_day() % 24.0) < 16.0

def reserve():
    return DAY_RESERVE if is_day() else NIGHT_RESERVE

# ═══════════════════════════════════════
# ENERGIAMODELL
# ═══════════════════════════════════════

def move_cost(speed):
    """Bruttó fogyasztás 1 tickre: E = 2*v²"""
    return float(ENERGY_K * speed * speed)

def net_move(speed, day):
    """
    Nettó energiaváltozás mozgás közben 1 tickre.
    Pozitív = merül, negatív = töltődik.
    """
    return move_cost(speed) - (DAY_CHARGE if day else 0)

def net_mine(day):
    """Bányászás nettó energiaváltozása 1 tickre. Pozitív = merül."""
    return float(MINE_COST) - (DAY_CHARGE if day else 0)

def ticks_needed(dist_blocks, speed):
    return ceil(dist_blocks / speed)

def battery_after(bat, dist_blocks, speed, day):
    """Várható akkuszint az odaút + 1 tick bányászás után."""
    t            = ticks_needed(dist_blocks, speed)
    travel_delta = net_move(speed, day) * t
    mine_delta   = net_mine(day)
    total_delta  = travel_delta + mine_delta
    return max(0.0, min(BATTERY_CAP, bat - total_delta))

def energy_for_return(dist_to_base, day):
    """
    Mennyi akku szükséges a hazaúthoz.
    Nappal v=1/v=2 töltődik → csak a tartalék kell.
    Éjjel v=1-gyel (2/tick): 2 × ceil(dist × margin) + tartalék.
    """
    if day:
        return reserve()
    t = ceil(dist_to_base * RETURN_MARGIN)
    return 2.0 * t + reserve()

def safe_to_go(bat, ore_dist, base_from_ore, speed, day):
    """Igaz ha: odaér + kibányász + visszaér."""
    bat_after_mine    = battery_after(bat, ore_dist, speed, day)
    needed_for_return = energy_for_return(base_from_ore, day)
    return bat_after_mine >= needed_for_return

# ═══════════════════════════════════════
# PATH CACHE
# ═══════════════════════════════════════

_cache = {}

def astar(start, goal):
    key = (start, goal)
    if key in _cache:
        return _cache[key]
    result = []
    if CPP_AVAILABLE:
        try:
            result = cpp_mod.astar_from_csv(CSV_PATH, start, goal)
        except Exception as e:
            print("A* hiba:", e)
    _cache[key] = result
    return result

def path_dist(start, goal):
    if start == goal:
        return 0
    p = astar(start, goal)
    return len(p) - 1 if p else None

# ═══════════════════════════════════════
# MAP
# ═══════════════════════════════════════

def get_all_ores():
    ores = []
    for y, row in enumerate(map_obj.map_data):
        for x, tile in enumerate(row):
            if tile in ORE_VALUES:
                ores.append({"pos": (x, y), "type": tile})
    return ores

def remove_ore(ores, pos):
    for i, o in enumerate(ores):
        if o["pos"] == pos:
            ores.pop(i)
            return

# ═══════════════════════════════════════
# SEBESSÉGVÁLASZTÁS
# ═══════════════════════════════════════

def pick_speed(ore_dist, bat, base_dist, day):
    """
    Legnagyobb biztonságos sebesség, vagy None.
    Nappal: 3→2→1 sorrendben próbál.
    Éjjel:  max v=2 (v=3 = 18/tick, túl kockázatos).
    """
    candidates = (3, 2, 1) if day else (2, 1)
    for speed in candidates:
        if safe_to_go(bat, ore_dist, base_dist, speed, day):
            return speed
    return None

# ═══════════════════════════════════════
# KLASZTER LOGIKA
# ═══════════════════════════════════════

def find_cluster(center_pos, ores, radius=CLUSTER_RADIUS):
    """
    Megkeresi a center_pos közelében (radius blokkon belül) lévő érceket
    az aktuális ores listából.
    Gyors Manhattan pre-filter, majd pontos path_dist ellenőrzés.
    Visszaadja a listát (távolság, ore) párként, távolság szerint rendezve.
    Maga a center_pos-on lévő érc is benne lehet (d=0).
    """
    cluster = []
    cx, cy  = center_pos
    for ore in ores:
        ox, oy = ore["pos"]
        if abs(ox - cx) + abs(oy - cy) > radius * 2:
            continue
        d = path_dist(center_pos, ore["pos"])
        if d is not None and d <= radius:
            cluster.append((d, ore))
    cluster.sort(key=lambda x: x[0])
    return cluster

def choose_ore(pos, ores, bat):
    """
    Klaszter-tudatos célválasztás.

    Minden elérhető ércre kiszámolja:
      score = ticks_to_ore - neighbor_count × CLUSTER_BONUS

    neighbor_count = hány más érc van CLUSTER_RADIUS-on belül az ércnél.
    Kisebb score = vonzóbb cél → klaszteres területeket preferálja.

    FONTOS: ez csak az ELSŐ célt adja vissza.
    A klaszter többi tagját collect_cluster() bányássza ki sorban.
    """
    day        = is_day()
    best_score = None
    best       = None

    for ore in ores:
        d_ore = path_dist(pos, ore["pos"])
        if d_ore is None:
            continue

        d_base = path_dist(ore["pos"], BASE_POS)
        if d_base is None:
            continue

        speed = pick_speed(d_ore, bat, d_base, day)
        if speed is None:
            continue

        t = ticks_needed(d_ore, speed)

        neighbors      = find_cluster(ore["pos"], ores, CLUSTER_RADIUS)
        # Önmaga (d=0) nem számít szomszédnak
        neighbor_count = sum(1 for d, o in neighbors if o["pos"] != ore["pos"])

        score = t - neighbor_count * CLUSTER_BONUS

        if best_score is None or score < best_score:
            best_score = score
            best = {
                "ore":     ore,
                "path":    astar(pos, ore["pos"]),
                "dist":    d_ore,
                "ticks":   t,
                "speed":   speed,
                "after":   battery_after(bat, d_ore, speed, day),
                "cluster": neighbor_count,
                "score":   score,
            }

    return best

def collect_cluster(first_ore_pos, ores, mined_count):
    """
    Miután a rover megérkezett az első érchez és kibányászta azt,
    ez a függvény végigbányássza a klaszter összes maradék tagját.

    FIX: A klaszter tagjait az ELSŐ érc pozíciójától mérjük (first_ore_pos),
    nem az aktuális roverpozíciótól. Ez megakadályozza hogy a rover
    kilépjen a klaszterből ha néhány blokkot mozgott a klaszteren belül.

    A "maradt a klaszterből" lista az elején rögzítődik (snapshot),
    majd a rover sorban végigmegy rajtuk legközelebbi-először sorrendben.

    Visszatér: (sikeres: bool, kibányászott db száma)
    """
    collected = 0

    # Klaszter snapshot: az első érc körüli CLUSTER_RADIUS-on belüli
    # összes érc rögzítése az induláskor. Ez a lista nem változik közben
    # (kivéve amit kibányászunk – remove_ore törli az ores-ból).
    cluster_members = set(
        o["pos"]
        for d, o in find_cluster(first_ore_pos, ores, CLUSTER_RADIUS)
        if o["pos"] != first_ore_pos
    )
    print(f"  Klaszter snapshot: {len(cluster_members)} tag")

    while True:
        pos = (rover.pos.x, rover.pos.y)

        # Hazaút ellenőrzés minden érc előtt
        if must_go_home(pos, rover.battery):
            return True, collected

        # Csak a klaszter eredeti tagjait nézzük (akik még az ores-ban vannak)
        remaining_members = [o for o in ores if o["pos"] in cluster_members]

        if not remaining_members:
            # Klaszter teljesen kész
            break

        # Legközelebbi klasztertag a jelenlegi pozícióból
        best_d    = None
        best_ore  = None
        for o in remaining_members:
            d = path_dist(pos, o["pos"])
            if d is not None and (best_d is None or d < best_d):
                best_d   = d
                best_ore = o

        if best_ore is None:
            break

        nearby = [(best_d, best_ore)]  # kompatibilis a régi struktúrával

        d_next, next_ore = best_d, best_ore

        d_base = path_dist(next_ore["pos"], BASE_POS)
        if d_base is None:
            break

        speed = pick_speed(d_next, rover.battery, d_base, is_day())
        if speed is None:
            # Nincs elég akku a következő érchez – hagyjuk abba
            print(f"  Klaszter: nincs eleg akku a kovetkezohoz {next_ore['pos']}, megszakitas")
            break

        path = astar(pos, next_ore["pos"])
        if not path:
            # Nincs útvonal (nem valószínű, de kezeljük)
            break

        print(
            f"  Klaszter -> {next_ore['pos']} ({next_ore['type']}) | "
            f"dist={d_next} speed={speed} | "
            f"bat: {rover.battery:.1f}"
        )

        if not move_to(next_ore["pos"], path, speed):
            return False, collected

        if not mine_here(next_ore["pos"], next_ore["type"], path):
            return False, collected

        remove_ore(ores, next_ore["pos"])
        collected += 1

        print(f"  Klaszter [{collected}] akku={rover.battery:.1f} maradt={len(ores)}")

    return True, collected

# ═══════════════════════════════════════
# BACKEND / LOGGING
# ═══════════════════════════════════════

def refresh():
    global rover, sim, map_obj
    rover   = Sim.rover
    sim     = Sim.sim
    map_obj = Sim.sim.map_obj

def send_setup():
    if not USE_SERVER:
        return
    try:
        logger.send_setup({"map_matrix": map_obj.map_data})
    except Exception as e:
        print("send_setup hiba:", e)

def send_live(path_plan=None, status_override=None, speed_override=None):
    if not USE_SERVER:
        return
    try:
        storage = {"Y": 0, "G": 0, "B": 0}
        for attr in ("storage", "inventory", "mined_ores"):
            v = getattr(rover, attr, None)
            if isinstance(v, dict):
                storage = v
                break

        day = is_day()
        # Ha explicit override jön (pl. world_step-től), azt használjuk.
        # Ez javítja azt a hibát, hogy mozgás közben idle-t mutatott:
        # a Sim.step() után a rover már idle státuszra áll, de mi tudjuk
        # hogy az adott tickben mozgott/bányászott.
        eff_status = status_override if status_override is not None else rover.status
        eff_speed  = speed_override  if speed_override  is not None else current_speed()
        if eff_status == STATUS.MINE:
            cons = MINE_COST
        elif eff_status == STATUS.MOVE:
            cons = move_cost(eff_speed)
        else:
            cons = STANDBY_COST
        prod = DAY_CHARGE if day else 0

        payload = {
            "time_of_day":              float(time_of_day()),
            "elapsed_hrs":              float(elapsed_hrs()),
            "rover_position":           {"x": int(rover.pos.x), "y": int(rover.pos.y)},
            "rover_battery":            float(rover.battery),
            "rover_storage":            {k: int(storage.get(k, 0)) for k in ("B", "Y", "G")},
            "rover_speed":              int(eff_speed),
            "rover_status": (
                "mine" if eff_status == STATUS.MINE else
                "move" if eff_status == STATUS.MOVE else
                "dead" if rover.status == STATUS.DEAD else
                "idle"
            ),
            "rover_distance_travelled": int(getattr(rover, "distance_travelled", 0)),
            "rover_path_plan":          path_plan or [],
            "rover_energy_consumption": float(cons),
            "rover_energy_produce":     float(prod),
            # JAVÍTÁS: saját _mined_log, nem a megbízhatatlan rover.mined
            "rover_mined":              list(_mined_log),
        }
        logger.send_live(payload)
    except Exception as e:
        print("send_live hiba:", type(e).__name__, e)

def log_mined(pos, ore_type):
    """Kibányászott érc rögzítése. Ezt hívja mine_here() sikeres bányászás után."""
    _mined_log.append({
        "x":    int(pos[0]),
        "y":    int(pos[1]),
        "type": ore_type,
        "time": float(elapsed_hrs()),
    })

# ═══════════════════════════════════════
# WORLD STEP
# ═══════════════════════════════════════

def world_step(path_plan=None, status_override=None, speed_override=None):
    refresh()
    # Státuszt és sebességet a step ELŐTT rögzítjük, mert utána a szimuláció
    # már idle-re állíthatja a rovert (ezért mutatott idle-t mozgás közben).
    pre_status = status_override or rover.status
    pre_speed  = speed_override  or current_speed()
    Sim.step(sleep=True)
    refresh()
    send_live(path_plan, status_override=pre_status, speed_override=pre_speed)

# ═══════════════════════════════════════
# MOZGÁS
# ═══════════════════════════════════════

def move_to(target, path, speed):
    """
    Végiglépteti a path-t tickenként, a maradék lépésszámhoz igazított gearrel.

    JAVÍTÁS – actual_speed = min(speed, steps_remaining):
      Ha speed=3 de csak 2 blokk van hátra → gear=2 (8 energia, nem 18)
      Ha speed=3 de csak 1 blokk van hátra → gear=1 (2 energia, nem 18)
      Ha speed=2 de csak 1 blokk van hátra → gear=1 (2 energia, nem 8)

    A feladatleírás szerint a sebesség = "blokk/fél óra", tehát
    ha 1 blokkot teszünk meg egy tickben, a tényleges sebesség 1,
    függetlenül attól, milyen gearben volt beállítva a rover.
    """
    plan = [{"x": int(p[0]), "y": int(p[1])} for p in path] if path else []

    remaining = list(path)

    # Levágjuk a start pozíciót
    if remaining and (remaining[0][0], remaining[0][1]) == (rover.pos.x, rover.pos.y):
        remaining = remaining[1:]

    timeout = 5000

    while remaining:
        steps_left = len(remaining)

        # JAVÍTÁS: ténylegesen megtett blokkszámhoz igazított gear
        actual_speed = max(1, min(speed, steps_left))

        # A tick végpontja: actual_speed lépéssel arrébb (vagy a path vége)
        step_end    = remaining[actual_speed - 1]
        step_target = (step_end[0], step_end[1])

        set_gear(actual_speed)
        rover.path_find_to(Vector2(step_target[0], step_target[1]))
        world_step(plan, status_override=STATUS.MOVE, speed_override=actual_speed)

        if rover.battery <= 0:
            print("Lemerult mozgas kozben.")
            return False

        # Levágjuk a megtett lépéseket a remaining listából
        rover_pos = (rover.pos.x, rover.pos.y)

        # Közvetlen egyezés az elejéről
        while remaining and (remaining[0][0], remaining[0][1]) == rover_pos:
            remaining = remaining[1:]

        # Ha speed>1 és a rover közbülső ponton áll, keressük meg
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
            print("Mozgas timeout.")
            return False

    # Végső korrekció ha egy blokkal eltért
    if rover.pos.x != target[0] or rover.pos.y != target[1]:
        set_gear(1)
        rover.path_find_to(Vector2(target[0], target[1]))
        world_step(plan, status_override=STATUS.MOVE, speed_override=1)

    return True

# ═══════════════════════════════════════
# BÁNYÁSZÁS
# ═══════════════════════════════════════

def mine_here(ore_pos, ore_type, path):
    """
    Bányászás az aktuális pozícióban.

    JAVÍTÁS 1 – gear visszaállítása 1-re:
      Álló rovernél nincs értelme magasabb gearben lenni.
      set_gear(1) hívás rover.mine() előtt.

    JAVÍTÁS 2 – mined státusz azonnali küldése:
      rover.mine() után azonnal send_live()-t hívunk,
      hogy a dashboard "mine" státuszt kapjon még a world_step előtt.

    JAVÍTÁS 3 – log_mined() hívás sikeres bányászás után:
      A saját _mined_log-ba kerül az érc adatai (x, y, type, time).
      send_live() ezt a listát küldi, nem a rover.mined-et.
    """
    plan = [{"x": int(p[0]), "y": int(p[1])} for p in path] if path else []

    # JAVÍTÁS 1: gear visszaállítása 1-re bányászás előtt
    set_gear(1)
    rover.mine()

    # Azonnali "mine" státusz küldése override-dal
    send_live(plan, status_override=STATUS.MINE)

    stuck   = 0
    last_st = rover.status
    waited  = 0
    timeout = 5000

    while rover.status == STATUS.MINE:
        world_step(plan, status_override=STATUS.MINE)

        if rover.battery <= 0:
            print("Lemerult banyaszas kozben.")
            return False

        waited += 1
        if waited > 3:
            stuck = stuck + 1 if rover.status == last_st else 0
        last_st = rover.status

        if stuck >= 20:
            print("Banyaszas beragadt.")
            return False

        timeout -= 1
        if timeout <= 0:
            print("Banyaszas timeout.")
            return False

    # JAVÍTÁS 3: sikeres bányászás → saját log + azonnali küldés
    log_mined(ore_pos, ore_type)
    # rover.last_mined: a szimuláció belső állapotához szükséges (doc3-ból)
    rover.last_mined = Vector2(ore_pos[0], ore_pos[1])
    send_live(plan)

    return True

# ═══════════════════════════════════════
# VISSZATÉRÉS
# ═══════════════════════════════════════

def go_home(reason=""):
    print(f"Hazafele ({reason})...")
    pos = (rover.pos.x, rover.pos.y)

    if pos != BASE_POS:
        p = astar(pos, BASE_POS)
        if not p:
            print("Nincs ut haza!")
            return False
        d     = len(p) - 1
        speed = pick_speed(d, rover.battery, 0, is_day()) or 1
        if not move_to(BASE_POS, p, speed):
            return False

    waited = 0
    while rover.battery < 80 and waited < 400:
        world_step([])
        waited += 1

    print(f"Otthon, akku: {rover.battery:.1f}")
    return True

def must_go_home(pos, bat):
    d = path_dist(pos, BASE_POS)
    if d is None:
        return False
    if remaining_ticks() <= END_TICKS:
        return True
    needed = energy_for_return(d, is_day())
    if bat <= needed:
        print(f"Alacsony akku ({bat:.1f} <= {needed:.1f}), hazafele")
        return True
    return False

# ═══════════════════════════════════════
# FŐPROGRAM
# ═══════════════════════════════════════

def main():
    refresh()
    ores = get_all_ores()

    print(f"Ercek: {len(ores)}  |  {run_hrs}h = {int(run_hrs/delta_hrs)} tick")
    print("Energiamodell (1 tick = 0.5 ora):")
    for v in (1, 2, 3):
        print(f"  v={v}: {move_cost(v):.0f}/tick brutto | "
              f"nappal {net_move(v,True):+.0f} | "
              f"ejjel {net_move(v,False):+.0f}")
    print()
    print("Sebesség logika:")
    print("  Nappal: v=3>v=2>v=1 (ha biztonságos)")
    print("  Éjjel:  max v=2 (v=3 kizárva)")
    print(f"Klaszter: r={CLUSTER_RADIUS} blokk, bonus={CLUSTER_BONUS} tick/szomszed")
    print()

    send_setup()
    send_live()

    mined     = 0
    went_home = False

    while rover.battery > 0 and ores:
        pos = (rover.pos.x, rover.pos.y)

        if must_go_home(pos, rover.battery):
            go_home("akku / idolimit")
            if remaining_ticks() <= END_TICKS:
                went_home = True
                break
            continue

        target = choose_ore(pos, ores, rover.battery)

        if target is None:
            if not is_day():
                world_step([])
                continue
            print("Nincs elheto erc.")
            break

        ore = target["ore"]
        print(
            f"-> {ore['pos']} ({ore['type']}) | "
            f"dist={target['dist']} ticks={target['ticks']} "
            f"speed={target['speed']} score={target['score']:.1f} "
            f"cluster={target['cluster']} | "
            f"bat: {rover.battery:.1f}->{target['after']:.1f} | "
            f"{'nap' if is_day() else 'ej'}"
        )

        if not move_to(ore["pos"], target["path"], target["speed"]):
            break

        if not mine_here(ore["pos"], ore["type"], target["path"]):
            break

        remove_ore(ores, ore["pos"])
        mined += 1
        print(f"[{mined}] akku={rover.battery:.1f} maradt={len(ores)} {'nap' if is_day() else 'ej'}")

        # Ha volt klaszter, bányásszuk ki az összes szomszédot is
        if target["cluster"] > 0:
            print(f"  Klaszter indul ({target['cluster']} szomszed a kozelben)")
            ok, extra = collect_cluster(ore["pos"], ores, mined)
            mined += extra
            if not ok:
                break

    if not went_home:
        if (rover.pos.x, rover.pos.y) != BASE_POS:
            go_home("szimulaio vege")

    storage = {"Y": 0, "G": 0, "B": 0}
    for attr in ("storage", "inventory", "mined_ores"):
        v = getattr(rover, attr, None)
        if isinstance(v, dict):
            storage = v
            break

    print("\n" + "=" * 50)
    print("SZIMULAIO VEGE")
    print("=" * 50)
    print(f"Kibanyaszott : {mined}  (B={storage.get('B',0)} Y={storage.get('Y',0)} G={storage.get('G',0)})")
    print(f"Megmaradt    : {len(ores)} erc")
    print(f"Vegso akku   : {rover.battery:.1f}")
    print(f"Eltelt       : {elapsed_hrs():.1f} h")
    print(f"Cache        : {len(_cache)} bejegyzes")
    print(f"Mined log    : {len(_mined_log)} bejegyzes")
    pos = (rover.pos.x, rover.pos.y)
    print(f"Bazis        : {'OK' if pos == BASE_POS else 'NEM OK'} {pos}")
    print("=" * 50)

    try:
        Sim.close()
    except Exception:
        pass
    try:
        logger.close()
    except Exception:
        pass


if __name__ == "__main__":
    main()