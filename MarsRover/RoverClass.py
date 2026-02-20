from typing import List
from enum import Enum
from Simulation import Vector2
from Simulation import Map

"""
"A rover feladata, hogy adott idő alatt a lehető legtöbb ásványt gyűjtse össze."

"""

class STATUS(Enum):
	MINE = "mine",
	PROCESS = "process",
	IDLE = "idle",
	MOVE = "move"

Path = List[Vector2]

class Rover:
	MAX_SPEED = 3
	MAX_BATTERY_CHARGE = 100
	def __init__(self, id:str, map_obj:Map, log_freq_hrs:float=0.5, battery_charge:float=100.0):
		self.id = id
		self.map_data = map_obj
		self.log_freq_hrs = log_freq_hrs
		self.battery_charge = battery_charge if battery_charge <= self.MAX_BATTERY_CHARGE else self.MAX_BATTERY_CHARGE
		self.status = STATUS.IDLE
		self.pos = Map.get_poses_of_tile(Map.rover_marker, limit=1)
		self.start_pos = self.pos
		self.path = Path
		self.speed = 0

	def get_consumption(self):
		return 2 * pow(self.speed,2)

	def next_frame(self):
		# drain battery, update pos, validate next pos
		pass

	def find_path_to(self, position:Vector2):
		self.status = STATUS.PROCESS
		print("Searching for best path towards", Vector2._dict())
	
	def find_next_goal_position(self):
		# heat map based optimisation
		# find best path towards big goal
		# involve simulation time
		# get back to start point before simulation ends?
		pass


	def mine(self):
		# if not mineral: return
		if not self.map_obj.get_tile(self.pos) in self.map_obj.mineral_marks: print(f"Nothing to mine at rovers position ({self.pos})"); return
		self.status = STATUS.MINE
		# standby for 30 mins

	def set_speed(self, speed:int):
		if speed > self.MAX_SPEED: print(f"Uanble to set speed({speed}): over limit ({self.MAX_SPEED})"); return
		if speed < 0: print(f"Uanble to set speed({speed}): cannot be under 0"); return
		self.speed = speed