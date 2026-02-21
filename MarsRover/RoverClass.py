import Simulation
import Map
from Simulation import Vector2

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

Path = List[Vector2] # naviagtion path type

class Rover:
	MAX_SPEED = 3
	MAX_BATTERY_CHARGE = 100

	MINING_CONSUMPTION_HRS = 4 # 	2 /30mins
	STANDBY_CONSUMPTION_HRS = 2 # 1 /30mins
	DAY_CHARGE_SPEED_HRS = 20 # 	10/30mins

	K_MOVEMENT = 2  # k in E = k * v^2

	def __init__(self, id:str, map_obj:Map, simulation:Simulation):
		self.id = id
		self.map = map_obj
		self.sim = simulation
		
		#defaluts
		self.battery = 100.0
		self.status = STATUS.IDLE

		self.pos = self.map.get_poses_of_tile(self.map.rover_marker, limit=1) # get pos on map
		self.start_pos = self.pos
		
		self.path:Path = [] # the desired path the robot is going to follow
		self.speed = 1
		
		self.storage = {key: 0 for key in map_obj.mineral_markers} # dict of minerals {"Mineral":amount}
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
				return self.MINING_CONSUMPTION
			case STATUS.IDLE:
				return self.STANDBY_CONSUMPTION
	
	# RRVISE!!
	def energy_produced(self, delta_hrs: float):
		day = self.sim.day_hrs
		night = self.sim.night_hrs
		cycle = day + night # 24

		start = self.sim.elapsed_hrs % cycle
		end = (start + delta_hrs)

		# Case 1: interval does NOT wrap cycle
		if end <= cycle:
			daytime = max(0, min(end, day) - min(start, day))
		
		# Case 2: interval wraps cycle boundary
		else:
			first_part = max(0, day - min(start, day))
			second_part = min(end - cycle, day)
			daytime = first_part + max(0, second_part)

		return daytime * self.DAY_CHARGE_SPEED_HRS

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
			if self.map.is_walkable(n):
				result.append(n)
		return result

	def find_path_to(self, goal:Vector2):
		open_set = []
		heapq.heappush(open_set,(0,self.pos)) # (f_score, node)
		came_from = {}
		g_score = {self.pos:0} # cost from start
		
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
		while cur in came_from:
			path.append(cur)
			cur = came_from[cur]
		
		path.reverse()
		self.path = path
		self.status = STATUS.MOVE

# ---------------- GOAL SELECTION ----------------

	def find_next_goal_position(self):
		minerals = []
		for m in self.map.mineral_marks:
			minerals.extend(self.map.get_poses_of_tile(m))
		
		if not minerals:
			return self.start_pos
		
		best = None
		best_dist = 9999
		
		for m in minerals:
			d = self.heuristic(self.pos,m)
			if d < best_dist:
				best = m
				best_dist = d
		
		return best

# ---------------- MINING ----------------

	def mine(self):
		tile_mark = self.map.get_tile(self.pos)

		if tile_mark not in self.map.mineral_marks: return
		
		self.status = STATUS.MINE
		self.storage[tile_mark] += 1
		self.map.set_tile(self.pos,self.map.path_marker) # mark map pos as cleared

# ---------------- FRAME UPDATE ----------------

	def next_frame(self):
		self.battery = np.clip(self.battery, 0, self.MAX_BATTERY_CHARGE) # ensures battery can't be invalid
		

		if self.status == STATUS.MOVE and self.path:
			steps = min(self.speed,len(self.path))
			for _ in range(steps):
				self.pos = self.path.pop(0)
				self.distance_travelled += 1
			
			if not self.path:
				if self.map.get_tile(self.pos) in self.map.mineral_marks:
					self.mine()
				else:
					self.status = STATUS.IDLE
		
		elif self.status == STATUS.IDLE:
			target = self.find_next_goal_position()
			self.find_path_to(target)
		
		self.apply_energy()