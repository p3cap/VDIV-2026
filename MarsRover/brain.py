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
            if erc in ('Y', 'G', 'B'):
                # map is indexed as map[y][x] so x=j, y=i
                ercek_helye.append((i,j))

            j += 1

        i += 1



def tavolsagok():
    tavolsag_lista.clear()

    for ore_x,ore_y in ercek_helye:
        path, length = rover.astar(rover.pos, Vector2(ore_x,ore_y))  # astar -> (path, len(path))
        tavolsag_lista.append([[ore_x,ore_y], length])    



def legkozelebbi_erc():
    elerheto = [t for t in tavolsag_lista if t[1] is not None]
    return min(elerheto, key=lambda t: t[1])  # (ore_vector, length)

print(map_obj.map_data)

ercek_a_mapon()




def serverpost():
    sim.update(0.5)
    rover.update(0.5)
    time.sleep(1)


rover.pos = Vector2(0,0)

while(rover.battery != 0):  
    tavolsagok()
    leg = legkozelebbi_erc()
    print(leg)

    # leg is stored as (x, y, distance)
    rover.path_find_to(Vector2(leg[0][0], leg[0][1]))

    if rover.path == []:
        rover.mine()
        if rover.status != STATUS.MINE:
            tavolsag_lista.pop(0)

    serverpost()
    

