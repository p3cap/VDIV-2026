from Simulation import Simulation
from RoverClass import Rover, STATUS, GEARS
from MapClass import Map, matrix_from_csv
from Global import Vector2

import time
import os

# -------------------------
# C++ modul betöltés
# -------------------------
msys_path = r"C:\msys64\ucrt64\bin"
if os.path.exists(msys_path):
    os.add_dll_directory(msys_path)

import cpp_path as cpp_mod


# -------------------------
# Konfig
# -------------------------
CSV_PATH = r"MarsRover/data/mars_map_50x50.csv"

# Ha a feladatban más értékek vannak az érctípusokra, itt írd át
ORE_VALUES = {
    "Y": 1,
    "G": 1,
    "B": 1,
}


# -------------------------
# Map + Simulation + Rover
# -------------------------
map_obj = Map(
    map_data=matrix_from_csv(CSV_PATH)
)

sim = Simulation(
    map_obj=map_obj,
    sim_time_multiplier=15000,
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


# -------------------------
# Segédfüggvények
# -------------------------
def server_step(dt=0.5, sleep_sec=0.01):
    sim.update(dt)
    rover.update(dt)
    time.sleep(sleep_sec)


def same_pos_vec_and_tuple(vec: Vector2, xy: tuple[int, int]) -> bool:
    return vec.x == xy[0] and vec.y == xy[1]


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
    """
    C++ A* hívás.
    Visszaad: [(x,y), (x,y), ...]
    """
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
    """
    Bónusz, ha a cél körül több másik érc is van.
    """
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
    """
    Kiválasztja a következő célércet.

    score = value*100 + cluster_bonus*10 - distance
    """
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


def move_rover_to(target_xy):
    """
    Megadjuk a rovernek a célt, és megvárjuk, míg odaér.
    """
    target_vec = Vector2(target_xy[0], target_xy[1])
    rover.path_find_to(target_vec)

    max_steps = 20000
    steps = 0

    while not same_pos_vec_and_tuple(rover.pos, target_xy):
        server_step()
        steps += 1

        if steps >= max_steps:
            print("Mozgás timeout:", target_xy)
            return False

        if rover.battery <= 0:
            print("Lemerült mozgás közben.")
            return False

    return True


def mine_current_tile():
    """
    Elindítja a bányászatot, majd megvárja a végét.
    """
    rover.mine()

    max_steps = 20000
    steps = 0

    while rover.status == STATUS.MINE:
        server_step()
        steps += 1

        if steps >= max_steps:
            print("Bányászás timeout.")
            return False

        if rover.battery <= 0:
            print("Lemerült bányászás közben.")
            return False

    return True


def remove_mined_ore(ores, pos_xy):
    for i, ore in enumerate(ores):
        if ore["pos"] == pos_xy:
            ores.pop(i)
            return True
    return False


# -------------------------
# Főprogram
# -------------------------
def main():
    ores = get_all_ores()

    print("Talált ércek száma:", len(ores))
    print("Kezdő pozíció:", rover.pos.x, rover.pos.y)

    mined_count = 0

    while rover.battery > 0 and ores:
        current_pos = (rover.pos.x, rover.pos.y)

        best = choose_next_ore(current_pos, ores)
        if best is None:
            print("Nincs több elérhető érc.")
            break

        target_ore = best["ore"]
        target_xy = target_ore["pos"]

        print(
            f"Következő cél: {target_xy}, "
            f"típus: {target_ore['type']}, "
            f"dist: {best['dist']}, "
            f"cluster_bonus: {best['bonus']}, "
            f"score: {best['score']}"
        )

        # 1) odamegyünk
        ok_move = move_rover_to(target_xy)
        if not ok_move:
            break

        # 2) bányászás
        ok_mine = mine_current_tile()
        if not ok_mine:
            break

        # 3) töröljük a kibányászott ércet a listából
        removed = remove_mined_ore(ores, target_xy)
        if removed:
            mined_count += 1
            print(f"Kibányászva: {target_xy} | Összesen kibányászva: {mined_count}")
        else:
            print("Figyelem: a kibányászott érc nem volt benne a listában:", target_xy)

    print("Vége.")
    print("Maradék battery:", rover.battery)
    print("Kibányászott ércek:", mined_count)
    print("Megmaradt ércek:", len(ores))


if __name__ == "__main__":
    main()