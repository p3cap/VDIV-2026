from Simulation_env import RoverSimulationWorld
from RoverClass import STATUS, GEARS
from Global import Vector2

import os
import sys
import requests

# -------------------------
# Alap beállítások
# -------------------------
BASE_URL = "http://127.0.0.1:8000"
CSV_PATH = r"MarsRover/data/mars_map_50x50.csv"

steps = 0
delta_mode = "set_time"
delta_hrs = 0.5
tick_seconds = 1   # 1 helyett kisebb, hogy ne legyen túl lassú
env_speed = 1.0
send_every = 1
run_hrs = 240.0

USE_SERVER = True

ORE_VALUES = {
    "Y": 1,
    "G": 1,
    "B": 1,
}

# -------------------------
# DLL path előbb, import utána
# -------------------------
msys_path = r"C:\msys64\ucrt64\bin"
if os.path.exists(msys_path):
    os.add_dll_directory(msys_path)

sys.path.append(os.path.dirname(__file__))

import cpp_path as cpp_mod  # noqa: E402

# -------------------------
# World / Sim
# -------------------------
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

rover = Sim.rover
sim = Sim.sim
map_obj = Sim.sim.map_obj

rover.pos = Vector2(0, 0)
rover.gear = GEARS.NORMAL


# -------------------------
# Küldés a backend felé
# -------------------------
def send_setup():
    if not USE_SERVER:
        return

    try:
        requests.post(
            f"{BASE_URL}/send_setup",
            json={"map_matrix": map_obj.map_data},
            timeout=2,
        )
    except Exception as e:
        print("send_setup hiba:", e)


def send_live_data(current_target=None, planned_path=None):
    if not USE_SERVER:
        return

    try:
        payload = {
            "rover_position": {"x": rover.pos.x, "y": rover.pos.y},
            "status": str(rover.status),
            "rover_battery": rover.battery,
            "current_target": (
                {"x": current_target[0], "y": current_target[1]}
                if current_target is not None else None
            ),
            "path_plan": (
                [{"x": x, "y": y} for x, y in planned_path]
                if planned_path is not None else []
            ),
        }

        requests.post(
            f"{BASE_URL}/send_data",
            json=payload,
            timeout=2,
        )
    except Exception as e:
        print("send_data hiba:", e)


# -------------------------
# Segédfüggvények
# -------------------------
def refresh_refs():
    global rover, sim, map_obj
    rover = Sim.rover
    sim = Sim.sim
    map_obj = Sim.sim.map_obj


def get_all_ores():
    ores = []
    data = map_obj.map_data

    for y in range(len(data)):
        for x in range(len(data[y])):
            tile = data[y][x]
            if tile in ORE_VALUES:
                ores.append({
                    "pos": (x, y),
                    "type": tile,
                    "value": ORE_VALUES[tile]
                })

    return ores


def get_cpp_path(start_xy, goal_xy):
    try:
        return cpp_mod.astar_from_csv(CSV_PATH, start_xy, goal_xy)
    except Exception as e:
        print("C++ A* hiba:", e)
        return []


def get_path_and_length(start_xy, goal_xy):
    path = get_cpp_path(start_xy, goal_xy)
    if not path:
        return [], None
    return path, len(path) - 1


def cluster_bonus(target_ore, ores, radius=6):
    tx, ty = target_ore["pos"]
    bonus = 0

    for ore in ores:
        if ore["pos"] == target_ore["pos"]:
            continue

        ox, oy = ore["pos"]
        manhattan = abs(tx - ox) + abs(ty - oy)

        if manhattan <= radius:
            bonus += 1

    return bonus


def choose_next_ore(current_pos_xy, ores):
    candidates = []

    for ore in ores:
        path, dist = get_path_and_length(current_pos_xy, ore["pos"])
        if dist is None:
            continue

        bonus = cluster_bonus(ore, ores, radius=6)
        score = ore["value"] * 100 + bonus * 10 - dist

        candidates.append({
            "ore": ore,
            "path": path,
            "dist": dist,
            "bonus": bonus,
            "score": score
        })

    if not candidates:
        return None

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates[0]


def remove_mined_ore(ores, pos_xy):
    for i, ore in enumerate(ores):
        if ore["pos"] == pos_xy:
            ores.pop(i)
            return True
    return False


def same_pos_vec_and_tuple(vec, xy):
    return vec.x == xy[0] and vec.y == xy[1]


def world_step(current_target=None, planned_path=None):
    refresh_refs()
    Sim.step(sleep=True)
    refresh_refs()
    send_live_data(current_target=current_target, planned_path=planned_path)


# -------------------------
# Végrehajtás
# -------------------------
def move_rover_to(target_xy, planned_path):
    target_vec = Vector2(target_xy[0], target_xy[1])
    rover.path_find_to(target_vec)

    max_steps = 5000
    stuck_steps = 0
    last_pos = (rover.pos.x, rover.pos.y)

    while not same_pos_vec_and_tuple(rover.pos, target_xy):
        world_step(current_target=target_xy, planned_path=planned_path)

        current_pos = (rover.pos.x, rover.pos.y)

        if rover.battery <= 0:
            print("Lemerült mozgás közben.")
            return False

        if current_pos == last_pos:
            stuck_steps += 1
        else:
            stuck_steps = 0

        last_pos = current_pos

        if stuck_steps >= 80:
            print("A rover nem halad tovább.")
            return False

        max_steps -= 1
        if max_steps <= 0:
            print("Mozgás timeout.")
            return False

    return True


def mine_current_tile(target_xy, planned_path):
    rover.mine()

    max_steps = 5000
    stuck_steps = 0
    last_status = rover.status

    while rover.status == STATUS.MINE:
        world_step(current_target=target_xy, planned_path=planned_path)

        if rover.battery <= 0:
            print("Lemerült bányászás közben.")
            return False

        if rover.status == last_status:
            stuck_steps += 1
        else:
            stuck_steps = 0

        last_status = rover.status

        if stuck_steps >= 80:
            print("A bányászás nem halad tovább.")
            return False

        max_steps -= 1
        if max_steps <= 0:
            print("Bányászás timeout.")
            return False

    return True


# -------------------------
# Main
# -------------------------
def main():
    refresh_refs()

    ores = get_all_ores()

    print("Talált ércek száma:", len(ores))
    print("Kezdő pozíció:", rover.pos.x, rover.pos.y)

    send_setup()
    send_live_data(current_target=None, planned_path=[])

    mined_count = 0

    while rover.battery > 0 and ores:
        # JAVÍTVA: (x, y) kell, nem (y, x)
        current_pos = (rover.pos.x, rover.pos.y)

        best = choose_next_ore(current_pos, ores)
        if best is None:
            print("Nincs több elérhető érc.")
            break

        target_ore = best["ore"]
        target_xy = target_ore["pos"]
        planned_path = best["path"]

        print(
            f"Következő cél: {target_xy}, "
            f"típus: {target_ore['type']}, "
            f"dist: {best['dist']}"
        )

        send_live_data(current_target=target_xy, planned_path=planned_path)

        ok_move = move_rover_to(target_xy, planned_path)
        if not ok_move:
            break

        ok_mine = mine_current_tile(target_xy, planned_path)
        if not ok_mine:
            break

        removed = remove_mined_ore(ores, target_xy)
        if removed:
            mined_count += 1
            print(f"Kibányászva: {target_xy} | Összesen kibányászva: {mined_count}")
        else:
            print("Nem sikerült törölni a kibányászott ércet:", target_xy)

        x, y = target_xy
        map_obj.map_data[y][x] = "."

        send_setup()
        send_live_data(current_target=None, planned_path=[])

    print("Vége.")
    print("Maradék battery:", rover.battery)
    print("Kibányászott ércek:", mined_count)
    print("Megmaradt ércek:", len(ores))

    try:
        Sim.close()
    except Exception:
        pass


if __name__ == "__main__":
    main()