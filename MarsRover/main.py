import time, os, requests, random
from Simulation import Simulation
from RoverClass import Rover, STATUS, GEARS
from MapClass import Map, matrix_from_csv
from Global import Vector2

url = "http://127.0.0.1:8000/send_data" # TODO make universal

map_obj = Map(
	map_data = matrix_from_csv(r"MarsRover/data/mars_map_50x50.csv") # TODO make universal
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

#response = requests.post(url, json=live_data) # setup data, should go under

# -- test run --]
rover.Astar_pathfind_to(Vector2(random.randint(0,50),random.randint(0,50)))
#rover.Astar_pathfind_to(Vector2(0,32))
rover.gear = GEARS.SLOW

last_time = time.perf_counter()
while True:
	delta = time.perf_counter() - last_time
	last_time = time.perf_counter()
	print(f"frame started with delta: {delta}")
	delta_hrs = 0.5 # TODO remove divison laterrr, TEST ONLY
	sim.update(delta_hrs)
	rover.update(delta_hrs)

	if rover.status == STATUS.IDLE:
		rover.mine()
		rover.Astar_pathfind_to(Vector2(random.randint(0,50),random.randint(0,50)))
		#rover.Astar_pathfind_to(Vector2(0,35))

	os.system("cls")
	print(delta_hrs)
	print(rover)
	#print(rover)
	# print(sim)

	# TEST ONLY json server packet

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

	response = requests.post(url, json=live_data)
	#print("Server response:", response.json())

	time.sleep(1) # TODO 1/sim.sim_time_multiplie