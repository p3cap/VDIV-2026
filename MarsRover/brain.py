from Simulation import Simulation
from RoverClass import Rover, STATUS, GEARS
from MapClass import Map, matrix_from_csv
from Global import Vector2
from Simulation import Simulation

import time
import os
import sys
import requests

Sim = Simulation.__new__

# -------------------------
# DLL path beállítás ELŐBB
# -------------------------
msys_path = r"C:\msys64\ucrt64\bin"
if os.path.exists(msys_path):
    os.add_dll_directory(msys_path)

# Ha a cpp_path.pyd nem ugyanabban a mappában van, mint a brain.py,
# akkor ide add hozzá a tényleges mappáját
sys.path.append(os.path.dirname(__file__))

import cpp_path as cpp_mod


CSV_PATH = r"MarsRover/data/mars_map_50x50.csv"
SERVER_URL = "http://127.0.0.1:8000"

ORE_VALUES = {
    "Y": 1,
    "G": 1,
    "B": 1,
}


msys_path = r"C:\msys64\ucrt64\bin"
if os.path.exists(msys_path):
    os.add_dll_directory(msys_path)


map_obj = Map(
    map_data=matrix_from_csv(CSV_PATH)
)

sim = Simulation(
    map_obj=map_obj,
    sim_time_multiplier=20,   # FONTOS: ne legyen brutál gyors
    run_hrs=24.0,
    day_hrs=16.0,
    night_hrs=8.0,
)

rover = Rover(
    id="test_rover",
    sim=sim
)

rover.pos = Vector2(0, 0)
rover.gear = GEARS.NORMAL


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



def move_rover_to(target_xy, planned_path):
    target_vec = Vector2(target_xy[0], target_xy[1])
    rover.path_find_to(target_vec)

    max_steps = 5000
    stuck_steps = 0
    last_pos = (rover.pos.x, rover.pos.y)

    while not same_pos_vec_and_tuple(rover.pos, target_xy):

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


def main():
    ores = get_all_ores()

    print("Talált ércek száma:", len(ores))
    print("Kezdő pozíció:", rover.pos.x, rover.pos.y)

    send_setup()
    send_live_data()

    mined_count = 0

    while rover.battery > 0 and ores:
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

        # egyszer elküldjük az új célt
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

        # a mapon is tüntesd el, ha kell
        x, y = target_xy
        map_obj.map_data[y][x] = "."

        # frissített állapot kiküldése a bányászás után
        send_live_data(current_target=None, planned_path=[])

    print("Vége.")
    print("Maradék battery:", rover.battery)
    print("Kibányászott ércek:", mined_count)
    print("Megmaradt ércek:", len(ores))


if __name__ == "__main__":
    main()