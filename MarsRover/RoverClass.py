from MapClass import Map
from Simulation import Simulation
from Global import Vector2
from RoverLogger import RoverLogger

import heapq
import numpy as np
from typing import List, Optional
from enum import Enum

"""
Reminder:

A feladat 30 percesével számol mindent.
Szerintem én mindetn konsatnst (pl. töltést) 1 órával fogok számolni
és a szimuláció "deltájával" (milyen gyakran frisssül) megszorzom
"""

class STATUS(Enum): # "state machine"
	MINE = "mine"
	IDLE = "idle"
	MOVE = "move"
	DEAD = "dead"

class GEARS(Enum): # calculated in block/hrs
	SLOW = 2
	NORMAL = 4
	FAST = 6

Path = List[Vector2] # naviagtion path type

class Rover:
	MAX_BATTERY_CHARGE = 100

	MINING_CONSUMPTION_PER_HR = 4 # 	2 /30 mins
	STANDBY_CONSUMPTION_PER_HR = 2 # 1 /30 mins
	DAY_CHARGE_PER_HR = 20 # 	10/30 mins

	MINING_TIME_HRS = 0.5

	K_MOVEMENT = 2  # k in E = k * v^2

	def __init__(self, id:str, sim:Simulation, log_server_url:str="http://127.0.0.1:8000"):
		self.id = id
		self.sim = sim
		
		#defaluts
		self.battery = 100.0
		self.status = STATUS.IDLE

		self.pos = self.sim.map_obj.get_poses_of_tile(self.sim.map_obj.rover_marker, limit=1) # get pos on map
		self.start_pos = self.pos
		
		self.path:Path = [] # the desired path the robot is going to follow
		self.gear = GEARS.SLOW

		# fractional movement progress (tiles). Allows next_frame to be called
		# with uneven delta_hrs and accumulate partial tile movement.
		self.move_progress = 0.0
		self.mine_process_hrs = 0.0
		
		self.storage = {key: 0 for key in sim.map_obj.mineral_markers} # dict of minerals {"Mineral":amount}
		self.distance_travelled = 0

		#logging
		self.log_server_url = log_server_url # deafult localhost for development
		self.log_freq_per_hr = 0.5
		self.hrs_until_next_log = 0
		self.logger_obj = RoverLogger(log_server_url)

		#mined = [] # a lit for stroring mines metrials coords, for frontend packet optimisation

# ---------------- CONTROL HELPERS ----------------

	def _normalize_gear(self, gear=None) -> GEARS:
		if gear is None:
			return self.gear
		if isinstance(gear, GEARS):
			return gear
		if isinstance(gear, str):
			return GEARS[gear.upper()]
		if isinstance(gear, (int, float)):
			for g in GEARS:
				if g.value == int(gear):
					return g
		raise ValueError(f"Unsupported gear: {gear}")

	def set_gear(self, gear) -> GEARS:
		self.gear = self._normalize_gear(gear)
		return self.gear

	def gear_index(self) -> int:
		ordered = list(GEARS)
		return ordered.index(self.gear)

# ---------------- ENERGY ----------------
	def movement_cost_for_gear(self, delta_hrs: float, gear=None) -> float:
		"""Estimated movement energy for a chosen gear and duration."""
		g = self._normalize_gear(gear)
		speed_per_half_hr = g.value / 2
		half_hours = delta_hrs * 2
		return 2 * (speed_per_half_hr ** 2) * half_hours

	def movement_cost(self, delta_hrs: float) -> float:
		return self.movement_cost_for_gear(delta_hrs, self.gear)

	def energy_consumed(self, delta_hrs: float, status: STATUS = None, gear=None) -> float:
		"""Estimated energy consumption for a status/gear combination."""
		status = self.status if not status else status
		gear = self.gear if not gear else gear

		match status:
			case STATUS.MOVE:
				return self.movement_cost_for_gear(delta_hrs, gear)
			case STATUS.MINE:
				return self.MINING_CONSUMPTION_PER_HR * delta_hrs
			case STATUS.IDLE | STATUS.DEAD:
				return self.STANDBY_CONSUMPTION_PER_HR * delta_hrs
		return 0.0


	def energy_produced(self, delta_hrs: float) -> float:
		start_hrs = self.sim.elapsed_hrs
		end_hrs = start_hrs + delta_hrs
		daytime = self.sim.get_daytime_in_interval(start_hrs, end_hrs)
		return daytime * self.DAY_CHARGE_PER_HR

# ---------------- A* PATHFINDING ----------------

	def get_neighbors(self, node:Vector2) -> list[Vector2]:
		dirs = [
			(-1,0),(1,0),(0,-1),(0,1),
			(-1,-1),(-1,1),(1,-1),(1,1)
		]
		
		result = []
		for dx,dy in dirs:
			n = Vector2(node.x+dx,node.y+dy)
			if self.sim.map_obj.is_valid_pos(n):
				result.append(n)
		return result

	def astar(self, start: Vector2, goal: Vector2):
		open_set = []
		heapq.heappush(open_set, (0, start))

		came_from = {}
		g_score = {start: 0}
		closed_set = set()

		while open_set:
				_, current = heapq.heappop(open_set)

				if current in closed_set: continue
				if current == goal: break

				closed_set.add(current)

				for neighbor in self.get_neighbors(current):
						tentative = g_score[current] + 1  # cost = 1 per move

						if neighbor not in g_score or tentative < g_score[neighbor]:
								came_from[neighbor] = current
								g_score[neighbor] = tentative
								f = tentative + neighbor.distance_to(goal)
								heapq.heappush(open_set, (f, neighbor))

		# reconstruct path
		path = []
		cur = goal

		if cur not in came_from and cur != start:
				return [], 0

		while cur != start:
				path.append(cur)
				cur = came_from[cur]

		path.reverse()
		return path, len(path)

	def path_find_to(self, goal: Vector2, force: bool = False) -> list[Vector2]:
		if self.status != STATUS.IDLE and not force:
				return []

		start = self.pos
		dirs, _ = self.astar(start, goal)

		self.path = dirs
		self.status = STATUS.MOVE if dirs else STATUS.IDLE

		return dirs

# ---------------- MINING ----------------


	def mine(self) -> bool:
		tile = self.sim.map_obj.get_tile(self.pos)
		if not tile or not tile not in self.sim.map_obj.mineral_markers: return False

		self.mine_process_hrs = self.MINING_TIME_HRS
		self.status = STATUS.MINE
		self.storage[tile] += 1
		return True

# ---------------- FRAME UPDATE ----------------

	def update(self, delta_hrs:float):
		if not self.sim.is_running: print("Rover stopped: Simulation not running"); return
		if delta_hrs <= 0: return # don't calcaute for no reason

		if self.status == STATUS.MOVE and self.path:
			self.move_progress += self.gear.value * delta_hrs

			# consume whole-tile progress and advance along the path
			while self.move_progress >= 1.0 and self.path:
				dir = self.path.pop(0)
				self.pos = Vector2(self.pos.x + dir.x, self.pos.y + dir.y)
				self.distance_travelled += 1
				self.move_progress -= 1.0

			# arrived at goal
			if not self.path:
				self.status = STATUS.IDLE

		elif self.status == STATUS.MINE:
			self.mine_process_hrs -= delta_hrs
			if self.mine_process_hrs <= 0:
				self.status = STATUS.IDLE
				self.sim.map_obj.set_tile(self.pos, self.sim.map_obj.path_marker) # mark map pos as cleared
		
		elif self.status == STATUS.DEAD:
			return
		
		else:
			self.status = STATUS.IDLE

		# Energy
		consumed = self.energy_consumed(delta_hrs)
		produced = self.energy_produced(delta_hrs)
		self.battery += produced - consumed

		# Clamp battery to valid range
		self.battery = float(np.clip(self.battery, 0, self.MAX_BATTERY_CHARGE))

		# out of energy -> stop
		if self.battery <= 0:
			self.status = STATUS.DEAD
		
		self.hrs_until_next_log -= delta_hrs
		if self.hrs_until_next_log <= 0:
			self.hrs_until_next_log = self.log_freq_per_hr
			self.logger_obj.send_live(self.get_live_data())
			self.logger_obj.send_setup(self.get_setup_data()) # TODO exlude constant setups

# ----- ML helper -----

	def get_control_snapshot(self, delta_hrs: float = 0.5) -> dict:
		"""State/control snapshot intended for ML feature builders."""
		return {
			"position": {"x": self.pos.x, "y": self.pos.y},
			"status": self.status.name,
			"gear": self.gear.name,
			"gear_value": self.gear.value,
			"gear_index": self.gear_index(),
			"battery": float(self.battery),
			"battery_norm": float(self.battery / self.MAX_BATTERY_CHARGE),
			"move_progress": float(self.move_progress),
			"mine_process_hrs": float(self.mine_process_hrs),
			"distance_travelled": int(self.distance_travelled),
			"path_len": len(self.path),
			"movement_cost_now": float(self.movement_cost(delta_hrs)),
			"movement_cost_slow": float(self.movement_cost_for_gear(delta_hrs, GEARS.SLOW)),
			"movement_cost_normal": float(self.movement_cost_for_gear(delta_hrs, GEARS.NORMAL)),
			"movement_cost_fast": float(self.movement_cost_for_gear(delta_hrs, GEARS.FAST)),
			"energy_if_idle": float(self.energy_consumed_for(delta_hrs, STATUS.IDLE)),
			"energy_if_move": float(self.energy_consumed_for(delta_hrs, STATUS.MOVE, self.gear)),
			"energy_if_mine": float(self.energy_consumed_for(delta_hrs, STATUS.MINE)),
			"energy_produced": float(self.energy_produced(delta_hrs)),
		}


# ---------- Server logging --------------

	def get_live_data(self, delta_hrs : float) -> dict:
		consumed = self.energy_consumed(delta_hrs)
		produced = self.energy_produced(delta_hrs)
		return {
			"time_of_day": self.sim.elapsed_hrs % (self.sim.day_hrs+self.sim.night_hrs),
			"elapsed_hrs": self.sim.elapsed_hrs,
			"rover_position": self.pos._dict(),
			"rover_battery": self.battery,
			"rover_storage": self.storage,
			"speed": self.gear.value,
			"status": self.status.name,
			"distance_travelled": self.distance_travelled,
			"path_plan": [v._dict() for v in self.path],
			"rover_energy_consumption" : consumed,
			"rover_energy_production" : produced,
		}

	def get_setup_data(self) -> dict:
		return {
			"map_matrix": self.sim.map_obj.map_data,
			"day_hrs": self.sim.day_hrs,
			"night_hrs": self.sim.night_hrs,
			"run_hrs": self.sim.run_hrs,
			"sim_time_multiplier": self.sim.sim_time_multiplier,
			"markers" : self.sim.map_obj.marker_descriptions,
			"rover_name": self.id,
			"rover_max_battery": self.MAX_BATTERY_CHARGE,
			"rover_mining_consumption_per_hr": self.MINING_CONSUMPTION_PER_HR,
			"rover_standby_consumption_per_hr": self.STANDBY_CONSUMPTION_PER_HR,
			"rover_charge_per_hr": self.DAY_CHARGE_PER_HR,
			"rover_mine_hrs": self.MINING_TIME_HRS,
			"rover_mode": "machine_learning", # Will be the type of algory
		}

	# ---------- Self print Formatter --------------
	def __repr__(self):
		line = "=" * 40
		
		storage_str = ", ".join(
			f"{k}:{v}" for k, v in self.storage.items() if v > 0
		)
		if not storage_str:
			storage_str = "empty"

		path_len = len(self.path)

		return (
			f"\n{line}\n"
			f"ROVER [{self.id}]\n"
			f"{line}\n"
			f"Status      : {self.status.value}\n"
			f"Position    : ({self.pos.x}, {self.pos.y})\n"
			f"Speed       : {self.gear.value}\n"
			f"Battery     : {self.battery:.2f} / {self.MAX_BATTERY_CHARGE}\n"
			f"Distance    : {self.distance_travelled} tiles\n"
			f"move_prcs   : {self.move_progress} \n"
			f"Path left   : {path_len} nodes\n"
			f"Storage     : {storage_str}\n"
			f"Path     		: {self.path}\n"
			f"{line}"
		)

