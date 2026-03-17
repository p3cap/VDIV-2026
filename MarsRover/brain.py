"""
Mars Rover – Vadász Dénes Informatika Verseny 2026

Feladatleírás szerinti energiamodell:
  1 tick = fél óra
  Sebesség v = 1/2/3 blokk/tick
  Mozgási fogyasztás: E = 2 * v² /tick
    v=1: 2/tick   v=2: 8/tick   v=3: 18/tick
  Nappal töltés: +10/tick
  Bányászás: 2/tick, 1 tick ideig tart
  Standby: 1/tick

Nappal nettó mozgás:
  v=1: 2-10 = -8  (töltődik!)
  v=2: 8-10 = -2  (töltődik!)
  v=3: 18-10 = +8 (merül)

Éjjel nettó mozgás:
  v=1: +2   v=2: +8   v=3: +18

Döntési logika: mindig a LEGKÖZELEBBI elérhető ércet választja.
Az energiakorlát kizárja a túl messze lévő célokat.
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

# Energiamodell – feladatleírás szerint
BATTERY_CAP  = 100
ENERGY_K     = 2
DAY_CHARGE   = 10
MINE_COST    = 2
STANDBY_COST = 1

# Biztonsági tartalékok
DAY_RESERVE   = 5
NIGHT_RESERVE = 15
RETURN_MARGIN = 1.1   # 10% margó a hazaútra
END_TICKS     = 30    # ennyi tick maradt -> hazamegyünk

ORE_VALUES = {"Y": 1, "G": 1, "B": 1}

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
    return 2

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
    return float(MINE_COST) - (DAY_CHARGE if day else 0)

def ticks_needed(dist_blocks, speed):
    return ceil(dist_blocks / speed)

def battery_after(bat, dist_blocks, speed, day):
    """Várható akkuszint az odaút + 1 tick bányászás után."""
    t     = ticks_needed(dist_blocks, speed)
    delta = net_move(speed, day) * t + net_mine(day)
    return max(0.0, min(BATTERY_CAP, bat - delta))

def energy_for_return(dist_to_base, day):
    """
    Mennyi akku kell a hazaúthoz.
    Nappal: töltődik menet közben, elég a tartalék.
    Éjjel: v=1, nettó +2/tick, konzervatív becslés.
    """
    if day:
        return reserve()
    t = ceil(dist_to_base * RETURN_MARGIN)
    return 2.0 * t + reserve()

def safe_to_go(bat, ore_dist, base_from_ore, speed, day):
    """Igaz ha odaér + kibányász + visszaér."""
    after  = battery_after(bat, ore_dist, speed, day)
    needed = energy_for_return(base_from_ore, day)
    return after >= needed

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
    """Legnagyobb biztonságos sebesség (3>2>1), vagy None."""
    for speed in (3, 2, 1):
        if safe_to_go(bat, ore_dist, base_dist, speed, day):
            return speed
    return None

# ═══════════════════════════════════════
# CÉLVÁLASZTÁS – LEGKÖZELEBBI ÉRC
# ═══════════════════════════════════════

def choose_ore(pos, ores, bat):
    """
    Greedy: a legkevesebb tickbe kerülő elérhető ércet választja.
    Elérhető = van elég akku oda + bányász + vissza.
    Nincs klaszter logika, nincs ugrálás.
    """
    day        = is_day()
    best_ticks = None
    best       = None

    for ore in ores:
        d_ore  = path_dist(pos, ore["pos"])
        if d_ore is None:
            continue

        d_base = path_dist(ore["pos"], BASE_POS)
        if d_base is None:
            continue

        speed = pick_speed(d_ore, bat, d_base, day)
        if speed is None:
            continue

        t = ticks_needed(d_ore, speed)
        if best_ticks is None or t < best_ticks:
            best_ticks = t
            best = {
                "ore":   ore,
                "path":  astar(pos, ore["pos"]),
                "dist":  d_ore,
                "ticks": t,
                "speed": speed,
                "after": battery_after(bat, d_ore, speed, day),
            }

    return best

# ═══════════════════════════════════════
# BACKEND
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

def send_live(path_plan=None):
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
        if rover.status == STATUS.MINE:
            cons = MINE_COST
        elif rover.status == STATUS.MOVE:
            cons = move_cost(current_speed())
        else:
            cons = STANDBY_COST
        prod = DAY_CHARGE if day else 0

        raw_mined = getattr(rover, "mined", [])
        if raw_mined and not isinstance(raw_mined[0], dict):
            mined = [
                {"x": int(m.x), "y": int(m.y)} if hasattr(m, "x")
                else {"x": int(m[0]), "y": int(m[1])}
                for m in raw_mined
            ]
        else:
            mined = raw_mined

        payload = {
            "time_of_day":              float(time_of_day()),
            "elapsed_hrs":              float(elapsed_hrs()),
            "rover_position":           {"x": int(rover.pos.x), "y": int(rover.pos.y)},
            "rover_battery":            float(rover.battery),
            "rover_storage":            {k: int(storage.get(k, 0)) for k in ("B", "Y", "G")},
            "rover_speed":              int(current_speed()),
            "rover_status": (
                "mine" if rover.status == STATUS.MINE else
                "move" if rover.status == STATUS.MOVE else
                "dead" if rover.status == STATUS.DEAD else
                "idle"
            ),
            "rover_distance_travelled": int(getattr(rover, "distance_travelled", 0)),
            "rover_path_plan":          path_plan or [],
            "rover_energy_consumption": float(cons),
            "rover_energy_produce":     float(prod),
            "rover_mined":              mined,
        }
        logger.send_live(payload)
    except Exception as e:
        print("send_live hiba:", type(e).__name__, e)

# ═══════════════════════════════════════
# WORLD STEP
# ═══════════════════════════════════════

def world_step(path_plan=None):
    refresh()
    Sim.step(sleep=True)
    refresh()
    send_live(path_plan)

# ═══════════════════════════════════════
# MOZGÁS
# ═══════════════════════════════════════

def move_to(target, path, speed):
    """
    Kézzel lépteti végig a path-t, tickenként pontosan 'speed' blokkot haladva.

    A feladatleírás szerint v=2 azt jelenti: 1 tick alatt 2 blokk.
    Ezért a path-t 'speed' méretű szeletekre vágjuk, és minden szelet
    VÉGPONTJÁRA hívjuk a path_find_to-t, majd 1 tick-et lépünk.

    Így garantált hogy:
      - 1 tick alatt pontosan 'speed' blokk (vagy kevesebb az utolsó ticknél)
      - Nem ugrik át blokkokat
      - Az energiafogyasztás pontosan stimmel
    """
    plan = [{"x": int(p[0]), "y": int(p[1])} for p in path] if path else []

    # A path az A*-tól jön: path[0] = start, path[-1] = cél
    # Lépjük végig 'speed' lépésenként
    remaining = list(path)

    # Levágjuk a start pozíciót ha az egyenlő a rover pozíciójával
    if remaining and (remaining[0][0], remaining[0][1]) == (rover.pos.x, rover.pos.y):
        remaining = remaining[1:]

    timeout = 5000

    while remaining:
        # Következő tick célpontja: 'speed' lépéssel arrébb, vagy a path vége
        step_end = remaining[min(speed, len(remaining)) - 1]
        step_target = (step_end[0], step_end[1])

        set_gear(speed)
        rover.path_find_to(Vector2(step_target[0], step_target[1]))
        world_step(plan)

        if rover.battery <= 0:
            print("Lemerult mozgas kozben.")
            return False

        # Levágjuk a már megtett lépéseket
        rover_pos = (rover.pos.x, rover.pos.y)
        while remaining and (remaining[0][0], remaining[0][1]) == rover_pos:
            remaining = remaining[1:]
        # Ha a rover tovább lépett (speed > 1), vágjuk le a közbülső pontokat is
        if remaining:
            # megkeressük hol tartunk a path-ban
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

    # Végső ellenőrzés
    if rover.pos.x != target[0] or rover.pos.y != target[1]:
        # Lehet hogy egy lépéssel túlment – egy utolsó path_find_to a célra
        rover.path_find_to(Vector2(target[0], target[1]))
        world_step(plan)

    return True

# ═══════════════════════════════════════
# BÁNYÁSZÁS
# ═══════════════════════════════════════

def mine_here(target, path):
    plan    = [{"x": int(p[0]), "y": int(p[1])} for p in path] if path else []
    rover.mine()

    stuck   = 0
    last_st = rover.status
    waited  = 0
    timeout = 5000

    while rover.status == STATUS.MINE:
        world_step(plan)

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
            f"speed={target['speed']} | "
            f"bat: {rover.battery:.1f}->{target['after']:.1f} | "
            f"{'nap' if is_day() else 'ej'}"
        )

        if not move_to(ore["pos"], target["path"], target["speed"]):
            break

        if not mine_here(ore["pos"], target["path"]):
            break

        rover.last_mined = Vector2(ore["pos"][0], ore["pos"][1])
        remove_ore(ores, ore["pos"])
        mined += 1

        print(f"[{mined}] akku={rover.battery:.1f} maradt={len(ores)} {'nap' if is_day() else 'ej'}")

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