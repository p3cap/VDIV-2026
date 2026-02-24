from Simulation import Simulation 
from RoverClass import Rover, STATUS, GEARS 
from MapClass import Map, matrix_from_csv
from Global import Vector2
from collections import deque
import requests
import time

#szerver start
#cd dashboard 
#npm run dev

ercek_helye = []
tavolsag_lista = []

map_obj = Map(
    map_data = matrix_from_csv(r"MarsRover/data/mars_map_50x50.csv") # TODO make universal
)


#map_obj.is_day = True => +10 / 30 min

#map_obj.get_poses_of_tile(self, tile_name:str, limit:int=-1) #returnol lista[Vector2] ahol a mpon szerepel az adott dolog

sim = Simulation(
    map_obj = map_obj,
    sim_time_multiplier=15000,
    run_hrs = 24.0,
    day_hrs = 16.0,
    night_hrs = 8.0,
)

rover = Rover(
    id = "test_rover",
    sim = sim
)

#rover.battery

#rover.path_find_to(Vector2(15,15)) #rover meny erre a poziciora (x,y)

#rover.gear = GEARS.SLOW 1-be valt
#GEARS.NORMAL 2-be valt
#GEARS.FAST 3-ba valt

map = map_obj.map_data

def ercek_a_mapon():


    i = 0
    while i < len(map):
        j = 0
        while j < len(map[i]):
            
            erc = map[i][j]
            if erc == 'Y' or erc == 'G' or erc == 'B':
                ercek_helye.append((i, j))

            j += 1

        i += 1



def bfs(map, tx, ty):
    #tx = target x 
    #ty = target y

    sor = len(map)
    oszlop = len(map[0])

    iranyok = [(1,0), (-1,0), (0,1), (0,-1)]
    visited = [[False for _ in range(oszlop)] for _ in range(sor)]

    sx = rover.pos.x
    sy = rover.pos.y


    queue = deque()
    queue.append((sx, sy, 0))   # x, y, distance
    visited[sx][sy] = True

    while queue:
        x, y, d = queue.popleft() # d = distance 

        if (x, y) == (tx, ty): # if the destination is reached , return the distance 
            return d

        for dx, dy in iranyok:
            nx = x + dx
            ny = y + dy

            if 0 <= nx < sor and 0 <= ny < oszlop:
                if not visited[nx][ny] and map[nx][ny] != '#':
                    visited[nx][ny] = True
                    queue.append((nx, ny, d + 1))

    return None


def tavolsagok(map):
    
    rover_x = rover.pos.    x
    rover_y = rover.pos.y

    for ore_x, ore_y in ercek_helye:
        d = bfs(map,ore_x, ore_y)
        tavolsag_lista.append((ore_x, ore_y, d))

    return tavolsag_lista



def legkozelebbi_erc():
    elerheto = [t for t in tavolsag_lista if t[2] is not None]
    return  min(elerheto, key=lambda t: t[2])

print(map_obj.map_data)

ercek_a_mapon()
tavolsagok(map)
print()


def serverpost():

    sim.update(0.5)
    rover.update(0.5)

    url = "http://127.0.0.1:8000/send_data"
    live_data = {
        "time_of_day": sim.elapsed_hrs % (sim.day_hrs+sim.night_hrs),
        "rover_position": rover.pos._dict(),
        "rover_battery": rover.battery,
        "rover_storage": rover.storage,
        "speed": rover.gear.value,
        "status": rover.status.name,
        "distance_travelled": rover.distance_travelled,
        "mine_process_hrs": rover.mine_process_hrs,
        "path_plan": [v._dict() for v in rover.path]
    }

    time.sleep(1)
    response = requests.post(url, json=live_data)


rover.pos = Vector2(0,0)

while(rover.battery != 0):  
    leg = legkozelebbi_erc()
    rover.path_find_to(Vector2(leg[1],leg[0]))
    serverpost()
    rover.mine()

