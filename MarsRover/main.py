import time, os, requests, random
from Simulation import Simulation
from RoverClass import Rover, STATUS, GEARS
from MapClass import Map, matrix_from_csv
from Global import Vector2

url = "http://127.0.0.1:8000" # TODO make universal

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

# -- test run --

setup_data = {
  "day_hrs": sim.day_hrs,
  "night_hrs": sim.night_hrs,
  "run_hrs": sim.run_hrs,
  "sim_time_multiplier": sim.sim_time_multiplier,
  "markers": { # TODO idk what about this, but not good yet, cuz no reference to other stuffz
    "S": "Rover Start",
    ".": "Field",
    "#": "Barrier",
    "Y": "Gold",
    "B": "Ice",
    "G": "Green"
  },
  "rover_name": rover.id,
  "rover_max_battery": rover.MAX_BATTERY_CHARGE,
  "rover_mining_consumption_per_hr": rover.MINING_CONSUMPTION_PER_HR,
  "rover_standby_consumption_per_hr": rover.STANDBY_CONSUMPTION_PER_HR,
  "rover_charge_per_hr": rover.DAY_CHARGE_PER_HR,
  "rover_mine_hrs": rover.MINING_TIME_HRS,
  "rover_mode": "machine_learning", # Will be the type of algorythm used
	"map_matrix": map_obj.map_data
}

response = requests.post(url+"/send_setup", json=setup_data) # setup data, should go under /send_setup

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

	response = requests.post(url+"/send_data", json=live_data)
	#print("Server response:", response.json())

	time.sleep(1) # TODO 1/sim.sim_time_multiplie