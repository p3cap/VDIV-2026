from math import ceil
import requests

from Simulation_env import RoverSimulationWorld
from RoverClass import STATUS, GEARS
from Global import Vector2
import cpp_path as cpp_mod

# base url
BASE_URL = "http://127.0.0.1:8000"

# A térkép beolv
CSV_PATH = r"MarsRover/data/mars_map_50x50.csv"

# Szimuláció paraméterei
delta_mode = "set_time"
delta_hrs = 0.5          # 1 tick = fél óra
tick_seconds = 1         
env_speed = 1.0
send_every = 1
run_hrs = 240.0

# adat küldés engedett a beckendnek
USE_SERVER = True

# Az ércek értékei
ORE_VALUES = {
    "Y": 1,
    "G": 1,
    "B": 1,
}

# ENERGIA / IDŐ SZABÁLYOK

# Nappal félóránként ennyit töltődik
DAY_CHARGE_PER_HALF_HOUR = 10

# Ha áll és nem bányászik
STANDBY_CONSUMPTION = 1

# Ha áll és bányászik
MINING_CONSUMPTION = 2

# Max akkukapacitás
BATTERY_CAP = 100

# Vész tartalék minimum
MIN_EMERGENCY_BATTERY = 6

# Éjjel nagyobb tartalékot hagyunk, mert nincs töltés
NIGHT_RESERVE = 18

# KLASZTER / HELYI KITERMELÉS PARAMÉTEREK


# Mekkora sugárban tekintsük ugyanazon klaszter részének az érceket
# Ha túl kicsi, túl korán elmegy.
# Ha túl nagy, túl sokáig ragad egy rossz zónában.
CLUSTER_RADIUS = 10

# Mekkora bónuszt kapjon a sűrű klaszter
DENSE_CLUSTER_BONUS = 18

# Ha már egy klaszterben vagyunk, ez extra pont a helyben maradásra
CLUSTER_STICKINESS = 40

# WORLD / SIM INICIALIZÁLÁS

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

# referenciák
rover = Sim.rover
sim = Sim.sim
map_obj = Sim.sim.map_obj

# Kezdő pozíció
rover.pos = Vector2(0, 0)


# ENUM / GEAR SEGÉD
def _enum_members(enum_cls):
    #Biztonságos enum olvasás.Ha a GEARS enum __members__-t támogat, abból lekérjük a neveket.
    
    if hasattr(enum_cls, "__members__"):
        return {k.upper(): v for k, v in enum_cls.__members__.items()}
    return {}


# Beolvassuk a gear enum tagjait
GEAR_MEMBERS = _enum_members(GEARS)

# Sebesség -> gear megfeleltetés
GEAR_BY_SPEED = {
    1: GEAR_MEMBERS.get("SLOW"),
    2: GEAR_MEMBERS.get("NORMAL"),
    3: GEAR_MEMBERS.get("FAST")
}


def set_gear_by_speed(speed: int):
    #A kívánt sebességhez beállítja a rover gear-jét.
    
    gear = GEAR_BY_SPEED.get(speed)

    if gear is None:
        raise ValueError(
            f"Nincs GEARS enum hozzárendelve ehhez a speed-hez: {speed}. "
            f"Ellenőrizd a GEARS enum neveit."
        )

    rover.gear = gear


def get_current_speed_value():
    #A rover aktuális gear-jéből visszaadja a sebesség értékét (1,2,3).
    
    for speed, gear in GEAR_BY_SPEED.items():
        if gear == rover.gear:
            return speed
    return 2


# BACKEND UPDATE

def send_setup():
    
    #Egyszer elküldjük a map állapotát a backendnek.
    
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
    #Élő adatküldés a backend felé.Itt mennek a rover állapotok, akku, útvonal stb.
    
    if not USE_SERVER:
        return

    try:
        payload = {
            "time_of_day": get_time_of_day(),
            "elapsed_hrs": get_elapsed_hours(),
            "rover_position": {"x": rover.pos.x, "y": rover.pos.y},
            "rover_battery": rover.battery,
            "rover_speed": get_current_speed_value(),
            "rover_status": str(rover.status),
            "rover_distance_travelled": getattr(rover, "distance_travelled", 0),
            "rover_path_plan": (
                [{"x": x, "y": y} for x, y in planned_path]
                if planned_path is not None else []
            ),
            "current_target": (
                {"x": current_target[0], "y": current_target[1]}
                if current_target else None
            ),
        }

        requests.post(
            f"{BASE_URL}/send_data",
            json=payload,
            timeout=2,
        )
    except Exception as e:
        print("send_data hiba:", e)


#SEGÉDFÜGGVÉNYEK

def refresh_refs():
    #A sim tickek után frissítjük a rover / sim / map objektum referenciákat.
    
    global rover, sim, map_obj
    rover = Sim.rover
    sim = Sim.sim
    map_obj = Sim.sim.map_obj


def get_time_of_day():
    #Több helyről is megpróbáljuk kiolvasni az aktuális napszak időértékét.
    
    for obj, attr in [
        (Sim, "time_of_day"),
        (sim, "time_of_day"),
        (map_obj, "time_of_day"),
    ]:
        if hasattr(obj, attr):
            return float(getattr(obj, attr))
    return 0.0


def get_elapsed_hours():
    
    #Eddig eltelt órák lekérése, ha van ilyen attribútum.
    
    for obj, attr in [
        (Sim, "elapsed_hrs"),
        (sim, "elapsed_hrs"),
        (Sim, "elapsed_hours"),
        (sim, "elapsed_hours"),
    ]:
        if hasattr(obj, attr):
            return float(getattr(obj, attr))
    return 0.0


def is_daytime():
    """
    A kiírás:
        - nappal = 16 óra
        - éjszaka = 8 óra

    Tehát 24 órás cikluson belül:
        0-16 -- nappal
        16-24 -- éjszaka
    """
    tod = get_time_of_day() % 24.0
    return tod < 16.0


def same_pos_vec_and_tuple(vec, xy):
    #Vector2 és (x,y) tuple összehasonlítása.
    return vec.x == xy[0] and vec.y == xy[1]

# ENERGIA SZÁMÍTÁSOK

def movement_consumption_per_half_hour(speed: int):
    #Mozgási fogyasztás félórára: E = k * v^2, ahol k=2
    
    return 2 * (speed ** 2)


def net_move_energy_per_half_hour(speed: int, daytime: bool):
    """

    Félóránkénti nettó energiamérleg mozgás közben.
    Nappal: fogyasztás - töltés
    Éjjel: fogyasztás - 0
    Pozitív: merül
    Negatív: töltődik összességében

    """
    use = movement_consumption_per_half_hour(speed)
    charge = DAY_CHARGE_PER_HALF_HOUR if daytime else 0
    return use - charge


def net_mine_energy_per_half_hour(daytime: bool):
    """

    Bányászás közbeni nettó energiamérleg félórára.
    Bányászás közben a rover áll, de 2 egységet fogyaszt.
    Nappal mozgás közben is tölthet.
    
    """
    charge = DAY_CHARGE_PER_HALF_HOUR if daytime else 0
    return MINING_CONSUMPTION - charge


def estimate_move_half_hours(dist_blocks: int, speed: int):
    """

    Megadja, hogy hány félórás tick kell dist blokk megtételéhez.

    """
    return ceil(dist_blocks / speed)


def estimate_trip_after_battery(current_battery: float, dist_blocks: int, speed: int, daytime: bool):
    """

    Megbecsüli, mennyi akku maradna:
    - odamenetel után
    - majd 1 bányászás tick után

    Visszaad:
    - várható akku
    - mozgáshoz szükséges félórás tickek száma

    """
    move_ticks = estimate_move_half_hours(dist_blocks, speed)
    move_delta = net_move_energy_per_half_hour(speed, daytime) * move_ticks
    mine_delta = net_mine_energy_per_half_hour(daytime) * 1  # 1 tick = 0.5 óra bányászás

    after = current_battery - move_delta - mine_delta

    # Nappal ha töltődik, ne mehessen 100 fölé
    if daytime:
        after = min(BATTERY_CAP, after)

    return after, move_ticks


# MAP / ÉRC SEGÉDEK

def get_all_ores():
    #Végigmegy a mapon, és összeszedi az összes elérhető ércet.
    
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


def remove_mined_ore(ores, pos_xy):
    #Kiveszi a kibányászott ércet az aktív ore listából.
    for i, ore in enumerate(ores):
        if ore["pos"] == pos_xy:
            ores.pop(i)
            return True
    return False

# C++ A* KAPCSOLAT

def get_cpp_path(start_xy, goal_xy):
    #Meghívja a C++ A* útkeresőt.
    
    try:
        return cpp_mod.astar_from_csv(CSV_PATH, start_xy, goal_xy)
    except Exception as e:
        print("C++ A* hiba:", e)
        return []


def get_path_and_length(start_xy, goal_xy):
    """
    Visszaadja:
    - teljes path-et
    - távolság blokkban

    Ha nincs útvonal, dist=None
    """
    path = get_cpp_path(start_xy, goal_xy)

    if not path:
        return [], None

    return path, len(path) - 1

# KLASZTER LOGIKA

def cluster_bonus(target_ore, ores, radius=CLUSTER_RADIUS):
    """
    Megnézi, hogy a target körül hány másik érc van a megadott sugáron belül.

    Mivel diagonális mozgás is engedett,
    itt Chebyshev-távolságot használunk:
    max(dx, dy)
    """
    tx, ty = target_ore["pos"]
    bonus = 0

    for ore in ores:
        if ore["pos"] == target_ore["pos"]:
            continue

        ox, oy = ore["pos"]
        chebyshev = max(abs(tx - ox), abs(ty - oy))

        if chebyshev <= radius:
            bonus += 1

    return bonus


def ores_near_anchor(ores, anchor_xy, radius=CLUSTER_RADIUS):
    #Visszaadja az anchor körüli érceket.
    
    if anchor_xy is None:
        return []

    ax, ay = anchor_xy
    result = []

    for ore in ores:
        ox, oy = ore["pos"]
        chebyshev = max(abs(ax - ox), abs(ay - oy))

        if chebyshev <= radius:
            result.append(ore)

    return result


def should_keep_local_harvest(ores, cluster_center):
    #Addig maradunk a klaszterben, amíg a cluster_center körül van még legalább 1 érc.
    
    if cluster_center is None:
        return False

    local_ores = ores_near_anchor(ores, cluster_center, radius=CLUSTER_RADIUS)
    return len(local_ores) > 0

# SEBESSÉGVÁLASZTÁS

def choose_speed_for_target(dist, battery, daytime):
    """
    Kiválasztja a legjobb sebességet az adott célponthoz.

    Alapelv:
    - nappal inkább normál
    - ha nagyon tele az akku és hosszú az út, gyors is lehet
    - éjjel inkább lassú, mert jobb az energia/blokk arány
    """
    candidates = [1, 2, 3]
    best = None

    for speed in candidates:
        after_battery, move_ticks = estimate_trip_after_battery(
            battery,
            dist,
            speed,
            daytime
        )

        # Mennyi minimális tartalék maradjon
        reserve = MIN_EMERGENCY_BATTERY if daytime else NIGHT_RESERVE

        # Ha ez a sebesség túl veszélyes, eldobjuk
        if after_battery < reserve:
            continue

        # Heurisztikus pontozás
        utility = 0

        # Maradjon sok akku
        utility += after_battery * 0.8

        # Minél kevesebb idő kelljen
        utility -= move_ticks * 3.0

        # Nappali preferencia
        if daytime:
            if speed == 2:
                utility += 8
            elif speed == 3 and battery >= 85 and dist >= 10:
                utility += 5
        else:
            # Éjszakai preferencia
            if speed == 1:
                utility += 10
            elif speed == 2 and battery >= 70 and dist <= 5:
                utility += 2

        if best is None or utility > best["utility"]:
            best = {
                "speed": speed,
                "after_battery": after_battery,
                "move_ticks": move_ticks,
                "utility": utility
            }

    return best



# CÉLVÁLASZTÁS - GLOBÁLIS

def choose_next_ore(current_pos_xy, ores, current_battery, cluster_anchor=None):
    """
    Globális célválasztás:
    az összes érc közül kiválasztja a legjobb következő célt.

    Figyelembe veszi:
    - távolság
    - klaszter sűrűség
    - várható maradék akku
    - menetidő
    - helyben maradás bónusza (ha lenne cluster_anchor)
    """
    daytime = is_daytime()
    candidates = []

    local_ores = ores_near_anchor(ores, cluster_anchor, radius=CLUSTER_RADIUS) if cluster_anchor else []

    for ore in ores:
        path, dist = get_path_and_length(current_pos_xy, ore["pos"])

        # Ha nincs elérhető út, ezt kihagyjuk
        if dist is None:
            continue

        speed_plan = choose_speed_for_target(dist, current_battery, daytime)

        # Ha egyik sebességgel sem biztonságos, kihagyjuk
        if speed_plan is None:
            continue

        local_bonus = cluster_bonus(ore, ores, radius=CLUSTER_RADIUS)

        staying_bonus = 0
        if cluster_anchor is not None and ore in local_ores:
            staying_bonus = CLUSTER_STICKINESS

        # Összpontszám
        score = 0
        score += ore["value"] * 100
        score += local_bonus * DENSE_CLUSTER_BONUS
        score += staying_bonus
        score += speed_plan["after_battery"] * 0.6
        score -= dist * 3.5
        score -= speed_plan["move_ticks"] * 4.0

        candidates.append({
            "ore": ore,
            "path": path,
            "dist": dist,
            "score": score,
            "cluster_bonus": local_bonus,
            "speed": speed_plan["speed"],
            "after_battery": speed_plan["after_battery"],
            "move_ticks": speed_plan["move_ticks"],
        })

    if not candidates:
        return None

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates[0]

# CÉLVÁLASZTÁS - HELYI KLASZTEREN BELÜL

def choose_best_local_ore(current_pos_xy, local_ores, current_battery):
    """
    Ha már egy klaszterben vagyunk, akkor csak a helyi ércek közül választ.

    Ez a kulcs ahhoz, hogy ne menjen el 3-4 kő után máshova.
    """
    daytime = is_daytime()
    candidates = []

    for ore in local_ores:
        path, dist = get_path_and_length(current_pos_xy, ore["pos"])

        if dist is None:
            continue

        speed_plan = choose_speed_for_target(dist, current_battery, daytime)

        if speed_plan is None:
            continue

        local_bonus = cluster_bonus(ore, local_ores, radius=CLUSTER_RADIUS)

        score = 0
        score += ore["value"] * 100
        score += local_bonus * DENSE_CLUSTER_BONUS
        score += speed_plan["after_battery"] * 0.6
        score -= dist * 3.0
        score -= speed_plan["move_ticks"] * 3.0

        candidates.append({
            "ore": ore,
            "path": path,
            "dist": dist,
            "score": score,
            "cluster_bonus": local_bonus,
            "speed": speed_plan["speed"],
            "after_battery": speed_plan["after_battery"],
            "move_ticks": speed_plan["move_ticks"],
        })

    if not candidates:
        return None

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates[0]


# WORLD STEP

def world_step(current_target=None, planned_path=None):
    """
    Egy szimulációs lépés:
    - ref frissítés
    - sim step
    - ref frissítés
    - live adatküldés
    """
    refresh_refs()
    Sim.step(sleep=True)
    refresh_refs()
    send_live_data(current_target=current_target, planned_path=planned_path)



# MOZGÁS A CÉLHOZ

def move_rover_to(target_xy, planned_path, speed):
    #A rovert elmozgatja a megadott célpozícióig.
    
    set_gear_by_speed(speed)

    target_vec = Vector2(target_xy[0], target_xy[1])

    # A beépített pathfindingnak megadjuk a célpontot
    rover.path_find_to(target_vec)

    max_steps = 5000
    stuck_steps = 0
    last_pos = (rover.pos.x, rover.pos.y)

    while not same_pos_vec_and_tuple(rover.pos, target_xy):
        # Tick előtt újra beállítjuk a geart
        set_gear_by_speed(speed)

        world_step(current_target=target_xy, planned_path=planned_path)

        current_pos = (rover.pos.x, rover.pos.y)

        # Akku vész eset
        if rover.battery <= 0:
            print("Lemerült mozgás közben.")
            return False

        # Beragadás figyelés
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

# BÁNYÁSZÁS

def mine_current_tile(target_xy, planned_path):
    """
    Elindítja a bányászás folyamatát és kivárja a végét.
    """
    rover.mine()

    max_steps = 5000
    stuck_steps = 0
    last_status = rover.status

    while rover.status == STATUS.MINE:
        world_step(current_target=target_xy, planned_path=planned_path)

        if rover.battery <= 0:
            print("Lemerült bányászás közben.")
            return False

        # Beragadás figyelés status alapján
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

# EGY TELJES CÉL KIBÁNYÁSZÁSA

def mine_one_target(ores, target_pack):
    """
    Egy kiválasztott célra:
    - odamegy
    - kibányássza
    - törli az ore listából
    - kitörli a mapból
    """
    target_ore = target_pack["ore"]
    target_xy = target_ore["pos"]
    planned_path = target_pack["path"]
    speed = target_pack["speed"]

    print(
        f"Cél: {target_xy}, "
        f"típus: {target_ore['type']}, "
        f"dist: {target_pack['dist']}, "
        f"speed: {speed}, "
        f"cluster_bonus: {target_pack['cluster_bonus']}, "
        f"várható_akku_utána: {target_pack['after_battery']:.1f}, "
        f"day={is_daytime()}"
    )

    send_live_data(current_target=target_xy, planned_path=planned_path)

    # mozgas
    ok_move = move_rover_to(target_xy, planned_path, speed)
    if not ok_move:
        return False, None

    # bányászás
    ok_mine = mine_current_tile(target_xy, planned_path)
    if not ok_mine:
        return False, None

    # kiveszük a kibányászot ércet
    removed = remove_mined_ore(ores, target_xy)
    if removed:
        print(f"Kibányászva: {target_xy}")
    else:
        print("Nem sikerült törölni a kibányászott ércet:", target_xy)

    # a mapból is
    x, y = target_xy
    map_obj.map_data[y][x] = "."

    # Frissített map
    send_setup()
    send_live_data(current_target=None, planned_path=[])

    return True, target_xy


def main():
    """
    Fő vezérlő ciklus.
    """
    refresh_refs()

    # Összes érc összegyűjtése induláskor
    ores = get_all_ores()

    print("Talált ércek száma:", len(ores))
    print("Kezdő pozíció:", rover.pos.x, rover.pos.y)

    send_setup()
    send_live_data(current_target=None, planned_path=[])

    mined_count = 0

    # Ez a fix klaszterközép. Ha egyszer kiválasztunk egy jó területet,addig ott maradunk, amíg a környékén van még érc.
    cluster_center = None

    while rover.battery > 0 and ores:
        current_pos = (rover.pos.x, rover.pos.y)

        #  Ha van aktív klaszter, és abban még van érc, akkor CSAK abból válasszunk

        if should_keep_local_harvest(ores, cluster_center):
            local_ores = ores_near_anchor(
                ores,
                cluster_center,
                radius=CLUSTER_RADIUS
            )

            best = choose_best_local_ore(
                current_pos_xy=current_pos,
                local_ores=local_ores,
                current_battery=rover.battery
            )


        # Ha nincs aktív klaszter, válasszunk globálisan

        else:
            cluster_center = None

            best = choose_next_ore(
                current_pos_xy=current_pos,
                ores=ores,
                current_battery=rover.battery,
                cluster_anchor=None
            )

        # Ha nincs több biztonságos cél
        if best is None:
            print("Nincs több elérhető vagy energiaszinten biztonságosan elérhető érc.")
            break

        #  Ha most globálból választottunk új célt,ezt tekintjük az új klaszter közepének

        if cluster_center is None:
            cluster_center = best["ore"]["pos"]

        #Kibányásszuk a kiválasztott célt
        ok, mined_xy = mine_one_target(ores, best)
        if not ok:
            break

        mined_count += 1


        #Ha kiürült a klaszter, elengedjük
        if not should_keep_local_harvest(ores, cluster_center):
            cluster_center = None

        print(
            f"Összesen kibányászva: {mined_count} | "
            f"Maradék akku: {rover.battery:.1f} | "
            f"Megmaradt ércek: {len(ores)} | "
            f"Nappal: {is_daytime()}"
        )

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