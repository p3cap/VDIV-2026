from MapClass import Map
from Simulation import Simulation
from Global import Vector2

import heapq
import numpy as np
from typing import List
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

Path = List[Vector2] # naviagtion path type

class Rover:
	MAX_SPEED = 3
	MAX_BATTERY_CHARGE = 100

	MINING_CONSUMPTION_PER_HR = 4 # 	2 /30 mins
	STANDBY_CONSUMPTION_PER_HR = 2 # 1 /30 mins
	DAY_CHARGE_PER_HR = 20 # 	10/30 mins

	MINING_TIME_HRS = 0.5

	K_MOVEMENT = 2  # k in E = k * v^2

	def __init__(self, id:str, sim:Simulation):
		self.id = id
		self.sim = sim
		
		#defaluts
		self.battery = 100.0
		self.status = STATUS.IDLE

		self.pos = self.sim.map_obj.get_poses_of_tile(self.sim.map_obj.rover_marker, limit=1) # get pos on map
		self.start_pos = self.pos
		
		self.path:Path = [] # the desired path the robot is going to follow
		self.speed = 1

		# fractional movement progress (tiles). Allows next_frame to be called
		# with uneven delta_hrs and accumulate partial tile movement.
		self.move_progress = 0.0
		self.mine_process_hrs = 0.0
		
		self.storage = {key: 0 for key in sim.map_obj.mineral_markers} # dict of minerals {"Mineral":amount}
		self.distance_travelled = 0

# ---------------- ENERGY ----------------
	# calculates energy used for movement
	def movement_cost(self, delta_hrs: float):
		# all consatnts are in /hour calcuation for easier usage
		# formula: 
		# k * v^2 = 2 * half_hour_consumption^2 * half_hours_passed
		speed_per_half_hr = self.speed / 2
		half_hours = delta_hrs * 2 # amount of half hours passed (ex.: 1.5 * 2 = 3)
		return 2 * (speed_per_half_hr ** 2) * half_hours

	# calculates energy used (has to be called every time before changing status)
	def energy_consumed(self, delta_hrs:float):
		match self.status:
			case STATUS.MOVE:
				return self.movement_cost(delta_hrs)
			case STATUS.MINE:
				return self.MINING_CONSUMPTION_PER_HR * delta_hrs
			case STATUS.IDLE:
				return self.STANDBY_CONSUMPTION_PER_HR * delta_hrs
	
	# calculates energy produced from solar during daytime
	def energy_produced(self, delta_hrs: float):
		"""Calculate energy produced from solar panel during the interval.
		
		Uses Simulation's day/night cycle calculator to determine daytime hours.
		"""
		start = self.sim.elapsed_hrs
		end = start + delta_hrs
		daytime = self.sim.get_daytime_in_interval(start, end)
		return daytime * self.DAY_CHARGE_PER_HR

# ---------------- A* PATHFINDING ----------------

	def heuristic(self, a:Vector2, b:Vector2):
		return abs(a.x - b.x) + abs(a.y - b.y)

	def get_neighbors(self, node:Vector2):
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

	def Astar_pathfind_to(self, goal:Vector2): # TODO seperate A* into a new def
		if self.status != STATUS.IDLE: return
		open_set = []
		start = self.pos
		heapq.heappush(open_set,(0,start)) # (f_score, node)
		came_from = {}
		g_score = {start:0} # cost from start
		
		while open_set:
			_,current = heapq.heappop(open_set)
			
			if current == goal: break
			
			for neighbor in self.get_neighbors(current):
				tentative = g_score[current] + 1
				
				if neighbor not in g_score or tentative < g_score[neighbor]:
					came_from[neighbor] = current
					g_score[neighbor] = tentative
					f = tentative + self.heuristic(neighbor,goal)
					heapq.heappush(open_set,(f,neighbor))
		
		path = []
		cur = goal
		# Reconstruct path as absolute positions (excluding start)
		while cur in came_from:
			path.append(cur)
			cur = came_from[cur]
		
		path.reverse()
		# Convert absolute positions into direction vectors relative to start
		dirs: List[Vector2] = []
		prev = start
		for node in path:
			dx = node.x - prev.x
			dy = node.y - prev.y
			# clamp to -1/0/1 just in case
			dx = max(-1, min(1, dx))
			dy = max(-1, min(1, dy))
			dirs.append(Vector2(dx, dy))
			prev = node

		self.path = dirs
		self.status = STATUS.MOVE

# ---------------- MINING ----------------

	def mine(self):
		tile_mark = self.sim.map_obj.get_tile(self.pos)
		if tile_mark not in self.sim.map_obj.mineral_markers: return

		self.mine_process_hrs = self.MINING_TIME_HRS
		self.status = STATUS.MINE
		self.storage[tile_mark] += 1

# ---------------- FRAME UPDATE ----------------

	def next_frame(self, delta_hrs:float):
		if delta_hrs <= 0: return

		if self.status == STATUS.MOVE and self.path:
			self.move_progress += self.speed * delta_hrs

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
				self.state = STATUS.IDLE
				self.sim.map_obj.set_tile(self.pos,self.sim.map_obj.path_marker) # mark map pos as cleared

		# Energy
		consumed = self.energy_consumed(delta_hrs)
		produced = self.energy_produced(delta_hrs)
		self.battery += produced - consumed

		# Clamp battery to valid range
		self.battery = float(np.clip(self.battery, 0, self.MAX_BATTERY_CHARGE))

		# out of energy -> stop
		if self.battery <= 0:
			self.status = STATUS.DEAD

# ---------- Print Formatter --------------
	def __repr__(self):
		line = "-" * 40
		
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
			f"Speed       : {self.speed} tiles/hr\n"
			f"Battery     : {self.battery:.2f} / {self.MAX_BATTERY_CHARGE}\n"
			f"Distance    : {self.distance_travelled} tiles\n"
			f"Path left   : {path_len} nodes\n"
			f"Storage     : {storage_str}\n"
			f"Path     		: {self.path}\n"
			f"{line}"
		)