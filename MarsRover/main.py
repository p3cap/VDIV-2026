import time, os, requests, random
from Simulation import Simulation
from RoverClass import Rover, STATUS, GEARS
from MapClass import Map, matrix_from_csv
from Global import Vector2, MARS_ROVER_PATH
from RoverLogger import RoverLogger

url = "http://127.0.0.1:8000" # TODO make universal


map_obj = Map(
	map_data = matrix_from_csv(MARS_ROVER_PATH+r"/data/mars_map_50x50.csv") # TODO make universal
)

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
logger = RoverLogger(url)
logger.send_setup(rover.get_setup_data())




# -- test run --

#rover.Astar_pathfind_to(Vector2(random.randint(0,50),random.randint(0,50)))
blue = map_obj.get_poses_of_tile("B") # find all blue gems
rover.path_find_to(blue[random.randint(0,len(blue)-1)])
#rover.Astar_pathfind_to(Vector2(0,32))
rover.gear = GEARS.SLOW

last_time = time.perf_counter()
while True:
	delta = time.perf_counter() - last_time
	last_time = time.perf_counter()
	delta_hrs = 0.5 # TODO remove divison laterrr, TEST ONLY
	sim.update(delta_hrs)
	rover.update(delta_hrs)

	if rover.status == STATUS.IDLE:
		rover.mine()
		blue = map_obj.get_poses_of_tile("B")
		rover.path_find_to(blue[random.randint(0,len(blue)-1)])
		#rover.Astar_pathfind_to(Vector2(0,35)) #fixed mineral

	os.system("cls")
	print(f"frame started with delta_hrs: {delta_hrs}")
	print(rover)
	#print(rover)
	# print(sim)

	#send live data 
	logger.send_live(rover.get_live_data(delta_hrs))
	# TEST ONLY json server packet

	rover.send_log(url)
	#print("Server response:", response.json())

	time.sleep(1) # TODO 1/sim.sim_time_multiplie