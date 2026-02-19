import time
from Simulation import Simulation, Vector2
from RoverClass import Rover

sim = Simulation(
	run_hrs = 24.0,
	day_hrs = 16.0,
	night_hrs = 8.0,
)

rover = Rover(
	id = "test_rover"
)

while Simulation.next_frame():
	continue