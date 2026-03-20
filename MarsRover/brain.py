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
delta_hrs = 0.5
tick_seconds = 1
env_speed = 1.0
send_every = 1
run_hrs = 24.0

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
BASE_POS = None

# ---------------------------------------------------------
# Max / min speed
# ---------------------------------------------------------
MIN_SPEED = 1
MAX_SPEED = 3

# ---------------------------------------------------------
# Érc értékek
# ---------------------------------------------------------
ORE_VALUES = {
    "Y": 1,
    "G": 1,
    "B": 1,
}

# ---------------------------------------------------------
# Energiamodell
# ---------------------------------------------------------
BATTERY_CAP = 100.0
ENERGY_K = 2.0
DAY_CHARGE = 10.0
MINE_COST = 2.0
STANDBY_COST = 1.0

# ---------------------------------------------------------
# Biztonsági tartalékok
# ---------------------------------------------------------
DAY_RESERVE = 5.0
NIGHT_RESERVE = 15.0

# ---------------------------------------------------------
# Visszaút biztonsági szorzó
# ---------------------------------------------------------
RETURN_MARGIN = 1.10

# ---------------------------------------------------------
# Klaszter / cleanup
# ---------------------------------------------------------
CLUSTER_RADIUS = 10
DENSE_CLUSTER_BONUS = 18
CLUSTER_STICKINESS = 40
LOCAL_CLEANUP_RADIUS = 2

# ---------------------------------------------------------
# Path cache
# ---------------------------------------------------------
_path_cache = {}

# =========================================================
# ARGPARSE / INIT
# =========================================================

def _normalize_base_url(raw: str, fallback: str) -> str:
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
    if map_obj is not None and hasattr(map_obj, "map_data"):
        for y, row in enumerate(map_obj.map_data):
            for x, tile in enumerate(row):
                if tile == "S":
                    return (x, y)

    if rover is not None and hasattr(rover, "pos"):
        return (int(rover.pos.x), int(rover.pos.y))

    return (0, 0)


def init_world(args):
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

    BASE_POS = find_base_pos()
    rover.pos = Vector2(BASE_POS[0], BASE_POS[1])

    logger = RoverLogger(BASE_URL) if USE_SERVER else None

# =========================================================
# GEAR SEGÉD
# =========================================================

def clamp_speed(speed) -> int:
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
    if hasattr(enum_cls, "__members__"):
        return {k.upper(): v for k, v in enum_cls.__members__.items()}
    return {}


GEAR_MEMBERS = _enum_members(GEARS)

GEAR_BY_SPEED = {}
for speed, name in [(1, "SLOW"), (2, "NORMAL"), (3, "FAST")]:
    gear = GEAR_MEMBERS.get(name)
    if gear is None:
        raise ValueError(f"GEARS enum nem tartalmazza ezt a tag-et: {name}")
    GEAR_BY_SPEED[speed] = gear


def set_gear(speed: int):
    speed = clamp_speed(speed)
    rover.gear = GEAR_BY_SPEED[speed]


def current_speed() -> int:
    for speed, gear in GEAR_BY_SPEED.items():
        if rover.gear == gear:
            return clamp_speed(speed)
    return 2

# =========================================================
# REFRESH / IDŐ SEGÉDEK
# =========================================================

def refresh_refs():
    global rover, sim, map_obj
    rover = Sim.rover
    sim = Sim.sim
    map_obj = Sim.sim.map_obj


def elapsed_hrs():
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
                    if v != 0.0 or elapsed_hrs() == 0.0:
                        return v % 24.0
            except Exception:
                pass

    return float(elapsed_hrs()) % 24.0


def remaining_ticks() -> int:
    return int(max(0.0, run_hrs - elapsed_hrs()) / delta_hrs)


def is_day() -> bool:
    return (time_of_day() % 24.0) < 16.0


def reserve() -> float:
    return DAY_RESERVE if is_day() else NIGHT_RESERVE

# =========================================================
# ENERGIA SZÁMÍTÁS
# =========================================================

def move_cost(speed: int) -> float:
    speed = clamp_speed(speed)
    return float(ENERGY_K * speed * speed)


def net_move(speed: int, daytime: bool) -> float:
    return move_cost(speed) - (DAY_CHARGE if daytime else 0.0)


def net_mine(daytime: bool) -> float:
    return float(MINE_COST) - (DAY_CHARGE if daytime else 0.0)


def ticks_needed(dist_blocks: int, speed: int) -> int:
    speed = clamp_speed(speed)
    return ceil(dist_blocks / speed)


def battery_after_trip_and_mine(current_battery: float, dist_blocks: int, speed: int, daytime: bool) -> float:
    speed = clamp_speed(speed)
    move_ticks = ticks_needed(dist_blocks, speed)
    delta = net_move(speed, daytime) * move_ticks + net_mine(daytime)
    after = current_battery - delta
    after = max(0.0, min(BATTERY_CAP, after))
    return after


def energy_for_return(dist_to_base: int, daytime: bool) -> float:
    dist_to_base = max(0, int(dist_to_base))
    safe_dist = ceil(dist_to_base * RETURN_MARGIN)
    return_ticks = ticks_needed(safe_dist, 1)

    if daytime:
        base_need = max(1.0 * return_ticks, 0.0)
        return base_need + DAY_RESERVE

    base_need = 2.0 * return_ticks
    return base_need + NIGHT_RESERVE


def safe_to_go(current_battery: float, ore_dist: int, base_from_ore: int, speed: int, daytime: bool) -> bool:
    speed = clamp_speed(speed)
    after = battery_after_trip_and_mine(current_battery, ore_dist, speed, daytime)
    need_back = energy_for_return(base_from_ore, daytime)
    return after >= need_back

# =========================================================
# C++ A* / PATH
# =========================================================

def astar(start_xy, goal_xy):
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
    if start_xy == goal_xy:
        return 0

    path = astar(start_xy, goal_xy)
    if not path:
        return None

    if path and tuple(path[0]) == tuple(start_xy):
        return len(path) - 1
    return len(path)


def get_path_and_dist(start_xy, goal_xy):
    if start_xy == goal_xy:
        return [start_xy], 0

    raw_path = astar(start_xy, goal_xy)
    if not raw_path:
        return [], None

    normalized = [(int(p[0]), int(p[1])) for p in raw_path]

    if normalized and normalized[0] == start_xy:
        full_path = normalized
    else:
        full_path = [start_xy] + normalized

    dist = len(full_path) - 1
    return full_path, dist

# =========================================================
# MAP / ORE SEGÉDEK
# =========================================================

def get_all_ores():
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
    for i, ore in enumerate(ores):
        if ore["pos"] == pos_xy:
            ores.pop(i)
            return True
    return False


def ore_at_pos(ores, pos_xy):
    for ore in ores:
        if ore["pos"] == pos_xy:
            return ore
    return None

# =========================================================
# KLASZTER SEGÉDEK
# =========================================================

def chebyshev_dist(a_xy, b_xy):
    return max(abs(a_xy[0] - b_xy[0]), abs(a_xy[1] - b_xy[1]))


def cluster_bonus(target_ore, ores, radius=CLUSTER_RADIUS):
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
    if anchor_xy is None:
        return []

    result = []
    for ore in ores:
        if chebyshev_dist(ore["pos"], anchor_xy) <= radius:
            result.append(ore)

    return result


def should_keep_local_harvest(ores, cluster_anchor):
    if cluster_anchor is None:
        return False

    local = ores_near_anchor(ores, cluster_anchor, radius=CLUSTER_RADIUS)
    return len(local) > 0


def ores_near_position(ores, pos_xy, radius=LOCAL_CLEANUP_RADIUS):
    result = []

    for ore in ores:
        if chebyshev_dist(ore["pos"], pos_xy) <= radius:
            result.append(ore)

    return result


def pick_immediate_adjacent_ore(current_pos_xy, ores):
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
    best = None

    for speed in range(MAX_SPEED, MIN_SPEED - 1, -1):
        speed = clamp_speed(speed)

        if not safe_to_go(current_battery, dist_to_target, dist_target_to_base, speed, daytime):
            continue

        after_battery = battery_after_trip_and_mine(current_battery, dist_to_target, speed, daytime)
        move_ticks = ticks_needed(dist_to_target, speed)

        utility = 0.0
        utility += after_battery * 0.9
        utility -= move_ticks * 3.5

        if daytime:
            if speed == 2:
                utility += 6
            elif speed == 3 and dist_to_target >= 8 and current_battery >= 70:
                utility += 5
            elif speed == 1 and dist_to_target <= 2:
                utility += 2
        else:
            if speed == 1:
                utility += 10
            elif speed == 2 and dist_to_target <= 4 and current_battery >= 60:
                utility += 2
            elif speed == 3:
                utility -= 8

        if dist_to_target <= 2:
            if speed == 1:
                utility += 5
            elif speed == 3:
                utility -= 5

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
    daytime = is_day()

    path_to_ore, dist_to_ore = get_path_and_dist(current_pos_xy, ore["pos"])
    if dist_to_ore is None:
        return None

    _, dist_ore_to_base = get_path_and_dist(ore["pos"], BASE_POS)
    if dist_ore_to_base is None:
        return None

    speed_plan = choose_best_safe_speed(
        dist_to_target=dist_to_ore,
        current_battery=current_battery,
        dist_target_to_base=dist_ore_to_base,
        daytime=daytime,
    )

    if speed_plan is None:
        return None

    local_cluster_bonus = cluster_bonus(ore, all_ores, radius=CLUSTER_RADIUS)

    staying_bonus = 0
    if cluster_anchor is not None and chebyshev_dist(ore["pos"], cluster_anchor) <= CLUSTER_RADIUS:
        staying_bonus = CLUSTER_STICKINESS

    near_bonus = 0
    if chebyshev_dist(ore["pos"], current_pos_xy) <= LOCAL_CLEANUP_RADIUS:
        near_bonus = 60

    score = 0.0
    score += ore["value"] * 100.0
    score += local_cluster_bonus * DENSE_CLUSTER_BONUS
    score += staying_bonus
    score += near_bonus
    score += speed_plan["after_battery"] * 0.6
    score -= dist_to_ore * 3.5
    score -= speed_plan["move_ticks"] * 4.0
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

    if should_keep_local_harvest(ores, cluster_anchor):
        local_ores = ores_near_anchor(ores, cluster_anchor, radius=CLUSTER_RADIUS)
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
    if not USE_SERVER or logger is None:
        return

    try:
        logger.send_setup({"map_matrix": map_obj.map_data})
    except Exception as e:
        print("send_setup hiba:", e)


def send_live_data(current_target=None, planned_path=None):
    if not USE_SERVER or logger is None:
        return

    try:
        storage = {"Y": 0, "G": 0, "B": 0}

        for attr in ("storage", "inventory", "mined_ores"):
            value = getattr(rover, attr, None)
            if isinstance(value, dict):
                storage = value
                break

        daytime = is_day()

        if rover.status == STATUS.MINE:
            consumption = MINE_COST
        elif rover.status == STATUS.MOVE:
            consumption = move_cost(current_speed())
        else:
            consumption = STANDBY_COST

        production = DAY_CHARGE if daytime else 0.0

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
            "rover_position": {"x": int(rover.pos.x), "y": int(rover.pos.y)},
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
    refresh_refs()
    Sim.step(sleep=True)
    refresh_refs()
    send_live_data(current_target=current_target, planned_path=planned_path)

# =========================================================
# MOZGÁS SEGÉDEK
# =========================================================

def current_xy():
    return (int(rover.pos.x), int(rover.pos.y))


def normalize_path(path):
    if not path:
        return []
    return [(int(p[0]), int(p[1])) for p in path]


def trim_path_from_current(path, current_pos):
    path = normalize_path(path)
    if not path:
        return []

    if path[0] == current_pos:
        return path[1:]

    for i, p in enumerate(path):
        if p == current_pos:
            return path[i + 1:]

    return path


def next_step_chunk(path, speed):
    path = normalize_path(path)
    if not path:
        return None

    speed = clamp_speed(speed)
    idx = min(speed, len(path)) - 1
    return path[idx]


# =========================================================
# MOZGÁS
# =========================================================

def move_to(target_xy, path=None, initial_speed=1, allow_abort_for_home=True):
    """
    Stabilabb mozgás:
    - ha kell, minden tick előtt újrapath-el
    - nem bízik vakon a régi remaining listában
    - hazafelé hívható úgy is, hogy ne abortáljon
    """
    target_xy = (int(target_xy[0]), int(target_xy[1]))
    timeout = 8000
    stuck_limit = 40
    stuck = 0
    last_pos = current_xy()

    while True:
        pos = current_xy()

        if pos == target_xy:
            return True

        if allow_abort_for_home and target_xy != BASE_POS:
            if must_go_home(pos, rover.battery):
                print("Mozgás közben haza kell fordulni.")
                return False

        live_path, dist_now = get_path_and_dist(pos, target_xy)
        if dist_now is None or not live_path:
            print(f"Nincs út a célhoz: {pos} -> {target_xy}")
            return False

        remaining = trim_path_from_current(live_path, pos)
        if not remaining:
            return pos == target_xy

        live_speed = choose_live_speed(
            current_pos_xy=pos,
            target_xy=target_xy,
            current_battery=rover.battery,
        )
        live_speed = clamp_speed(live_speed)

        if initial_speed is not None:
            live_speed = min(live_speed, clamp_speed(initial_speed))

        if dist_now <= 2:
            live_speed = 1

        step_target = next_step_chunk(remaining, live_speed)
        if step_target is None:
            return pos == target_xy

        set_gear(live_speed)
        rover.path_find_to(Vector2(step_target[0], step_target[1]))
        send_live_data(current_target=target_xy, planned_path=live_path)
        world_step(current_target=target_xy, planned_path=live_path)

        if rover.battery <= 0:
            print("Lemerült mozgás közben.")
            return False

        new_pos = current_xy()

        if new_pos == target_xy:
            return True

        if new_pos == last_pos:
            stuck += 1
        else:
            stuck = 0

        last_pos = new_pos

        if stuck >= stuck_limit:
            print(f"Mozgás beragadt. pos={new_pos}, target={target_xy}")
            return False

        timeout -= 1
        if timeout <= 0:
            print(f"Mozgás timeout. pos={new_pos}, target={target_xy}")
            return False

# =========================================================
# BÁNYÁSZÁS
# =========================================================

def mine_here(target_xy, path):
    set_gear(1)
    rover.mine()

    waited = 0
    stuck = 0
    last_status = rover.status
    timeout = 5000

    while rover.status == STATUS.MINE:
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

def force_go_home_stepwise():
    """
    Végső mentőöv:
    mindig újratervez, mindig lassan megy, nem abortál vissza.
    """
    timeout = 12000
    stuck = 0
    last_pos = current_xy()

    while True:
        pos = current_xy()

        if pos == BASE_POS:
            return True

        path_home, dist_home = get_path_and_dist(pos, BASE_POS)
        if dist_home is None or not path_home:
            print("Kényszerített hazamenet: nincs út haza.")
            return False

        remaining = trim_path_from_current(path_home, pos)
        if not remaining:
            return pos == BASE_POS

        next_cell = remaining[0]

        set_gear(1)
        rover.path_find_to(Vector2(next_cell[0], next_cell[1]))
        send_live_data(current_target=BASE_POS, planned_path=path_home)
        world_step(current_target=BASE_POS, planned_path=path_home)

        if rover.battery <= 0:
            print("Lemerült hazamenet közben.")
            return False

        new_pos = current_xy()

        if new_pos == BASE_POS:
            return True

        if new_pos == last_pos:
            stuck += 1
        else:
            stuck = 0

        last_pos = new_pos

        if stuck >= 60:
            print(f"Kényszerített hazamenet beragadt. pos={new_pos}")
            return False

        timeout -= 1
        if timeout <= 0:
            print("Kényszerített hazamenet timeout.")
            return False


def go_home(reason=""):
    print(f"Hazafelé indulás. Ok: {reason}")

    pos = current_xy()

    if pos == BASE_POS:
        print(f"Már a bázison vagyunk. Akku: {rover.battery:.1f}")
        return True

    path_home, dist_home = get_path_and_dist(pos, BASE_POS)
    if dist_home is None or not path_home:
        print("Nincs út haza.")
        return False

    speed_plan = choose_best_safe_speed(
        dist_to_target=dist_home,
        current_battery=rover.battery,
        dist_target_to_base=0,
        daytime=is_day(),
    )

    start_speed = speed_plan["speed"] if speed_plan is not None else 1

    # 1. normál hazamenet
    ok = move_to(
        BASE_POS,
        path=path_home,
        initial_speed=start_speed,
        allow_abort_for_home=False,
    )

    if ok and current_xy() == BASE_POS:
        print(f"Hazaértünk. Akku: {rover.battery:.1f}")
        return True

    print("Normál hazamenet nem sikerült, kényszerített hazamenet indul...")

    # 2. végső fallback: lépésenként, újratervezve
    ok_force = force_go_home_stepwise()
    if ok_force and current_xy() == BASE_POS:
        print(f"Hazaértünk fallback-kel. Akku: {rover.battery:.1f}")
        return True

    print(f"Nem sikerült pontosan a bázisra érni. Pozíció: {current_xy()}")
    return False


def must_go_home(current_pos_xy, current_battery: float) -> bool:
    dist_home = path_dist(current_pos_xy, BASE_POS)
    if dist_home is None:
        return False

    safe_dist_home = ceil(dist_home * RETURN_MARGIN)
    ticks_home_needed = ticks_needed(safe_dist_home, 1)
    time_buffer = 2

    if remaining_ticks() <= ticks_home_needed + time_buffer:
        print(
            f"Időlimit miatt haza kell menni. "
            f"remaining={remaining_ticks()} | need_home={ticks_home_needed + time_buffer}"
        )
        return True

    need_back = energy_for_return(dist_home, is_day())
    if current_battery <= need_back:
        print(f"Kevés akku, haza kell menni. bat={current_battery:.1f}, need={need_back:.1f}")
        return True

    return False

# =========================================================
# HELYI TAKARÍTÁS
# =========================================================

def cleanup_nearby_ores(ores, cluster_anchor):
    cleaned = 0

    while True:
        current_pos = current_xy()

        if must_go_home(current_pos, rover.battery):
            break

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

    current_pos = current_xy()

    if current_pos != target_xy:
        ok_move = move_to(target_xy, path, speed, allow_abort_for_home=True)
        if not ok_move:
            return False, None

    if current_xy() != target_xy:
        print(f"Nem sikerült pontosan a célmezőre állni: {current_xy()} != {target_xy}")
        return False, None

    ok_mine = mine_here(target_xy, path)
    if not ok_mine:
        return False, None

    rover.last_mined = Vector2(target_xy[0], target_xy[1])

    removed = remove_ore(ores, target_xy)
    if not removed:
        print("Figyelem: a kibányászott érc nem volt törölhető a listából:", target_xy)

    return True, target_xy

# =========================================================
# MAIN
# =========================================================

def main():
    global BASE_POS

    args = parse_args()
    init_world(args)
    refresh_refs()

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
    cluster_anchor = None
    went_home_for_end = False

    while rover.battery > 0 and ores:
        current_pos = current_xy()

        if must_go_home(current_pos, rover.battery):
            ok_home = go_home("akku vagy időlimit")
            if not ok_home:
                break

            went_home_for_end = True
            break

        best = choose_target(
            current_pos_xy=current_pos,
            ores=ores,
            current_battery=rover.battery,
            cluster_anchor=cluster_anchor,
        )

        if best is None:
            if not is_day():
                print("Nincs biztonságos cél éjjel, várakozás nappalig...")
                set_gear(1)
                world_step(current_target=None, planned_path=[])
                continue

            print("Nincs több biztonságosan elérhető érc.")
            break

        if cluster_anchor is None:
            cluster_anchor = best["ore"]["pos"]

        ok, _ = mine_one_target(ores, best)
        if not ok:
            print("A cél kibányászása sikertelen volt.")
            if current_xy() != BASE_POS:
                go_home("sikertelen cél után")
            break

        mined_count += 1

        cleaned_now = cleanup_nearby_ores(ores, cluster_anchor)
        mined_count += cleaned_now

        if must_go_home(current_xy(), rover.battery):
            ok_home = go_home("cleanup után időlimit vagy akku")
            if not ok_home:
                break

            went_home_for_end = True
            break

        if not should_keep_local_harvest(ores, cluster_anchor):
            cluster_anchor = None

        print(
            f"[{mined_count}] "
            f"akku={rover.battery:.1f} | "
            f"maradék_érc={len(ores)} | "
            f"hátralévő_tick={remaining_ticks()} | "
            f"{'nap' if is_day() else 'éj'}"
        )

    if not went_home_for_end:
        if current_xy() != BASE_POS:
            go_home("szimuláció vége")

    storage = {"Y": 0, "G": 0, "B": 0}
    for attr in ("storage", "inventory", "mined_ores"):
        value = getattr(rover, attr, None)
        if isinstance(value, dict):
            storage = value
            break

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
    final_pos = current_xy()
    print(f"Bázison van: {'IGEN' if final_pos == BASE_POS else 'NEM'} | pozíció={final_pos}")
    print("=" * 60)

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