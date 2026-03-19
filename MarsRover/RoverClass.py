from Simulation import Simulation
from Global import Vector2, MARS_ROVER_PATH

import heapq
import numpy as np
from typing import List, Optional
from enum import Enum
from pathlib import Path as FilePath

# Optional C++ backend for A* (pybind11 module). Imported once at module level.
try:
	import cpp_path as _cpp_mod
	_CPP_AVAILABLE = True
except:
	_cpp_mod = None
	_CPP_AVAILABLE = False

class STATUS(Enum):
	MINE = "mine"
	IDLE = "idle"
	MOVE = "move"
	DEAD = "dead"

class GEARS(Enum): # blocks/hr
	SLOW   = 2
	NORMAL = 4
	FAST   = 6

Path = List[Vector2]

class Rover:
	MAX_BATTERY_CHARGE         = 100
	MINING_CONSUMPTION_PER_HR  = 4
	STANDBY_CONSUMPTION_PER_HR = 2
	DAY_CHARGE_PER_HR          = 20
	MINING_TIME_HRS            = 0.5
	K_MOVEMENT                 = 2
	DEFAULT_MAP_CSV            = MARS_ROVER_PATH / "data" / "mars_map_50x50.csv"

	def __init__(self, id: str, sim: Simulation, map_csv_path: Optional[str] = None):
		self.id  = id
		self.sim = sim

		self.battery  = 100.0
		self.status   = STATUS.IDLE
		self.pos       = self.sim.map_obj.get_poses_of_tiles([self.sim.map_obj.rover_marker], limit=1)
		self.start_pos = self.pos
		self.path: Path = []
		self.gear       = GEARS.SLOW

		self.move_progress    = 0.0
		self.mine_process_hrs = 0.0

		self.storage           = {key: 0 for key in sim.map_obj.mineral_markers}
		self.distance_travelled = 0

		self.logger_url  = "http://127.0.0.1:8000"
		self.logs_per_hr = 0.5
		self.mined       = []

		# Resolve map CSV path for C++ backend
		candidate = FilePath(map_csv_path) if map_csv_path else self.DEFAULT_MAP_CSV
		self._map_csv = str(candidate) if candidate.exists() else None
		self._use_cpp = _CPP_AVAILABLE and self._map_csv is not None

# ---------------- ENERGY ----------------

	def movement_cost(self, delta_hrs: float) -> float:
		speed_per_half_hr = self.gear.value / 2
		half_hours        = delta_hrs * 2
		return 2 * (speed_per_half_hr ** 2) * half_hours

	def energy_consumed(self, delta_hrs: float) -> float:
		match self.status:
			case STATUS.MOVE:  return self.movement_cost(delta_hrs)
			case STATUS.MINE:  return self.MINING_CONSUMPTION_PER_HR  * delta_hrs
			case STATUS.IDLE:  return self.STANDBY_CONSUMPTION_PER_HR * delta_hrs
			case _:            return 0.0

	def energy_produced(self, delta_hrs: float) -> float:
		daytime = self.sim.get_daytime_in_interval(self.sim.elapsed_hrs, self.sim.elapsed_hrs + delta_hrs)
		return daytime * self.DAY_CHARGE_PER_HR

# ---------------- A* PATHFINDING ----------------

	def heuristic(self, a: Vector2, b: Vector2) -> int:
		return abs(a.x - b.x) + abs(a.y - b.y)

	def get_neighbors(self, node: Vector2) -> list[Vector2]:
		result = []
		for dx, dy in ((-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)):
			n = Vector2(node.x + dx, node.y + dy)
			if self.sim.map_obj.is_valid_pos(n):
				result.append(n)
		return result

	def astar(self, start: Vector2, goal: Vector2) -> tuple[list[Vector2], int]:
		open_set = []
		heapq.heappush(open_set, (0, start))
		came_from: dict = {}
		g_score   = {start: 0}

		while open_set:
			_, current = heapq.heappop(open_set)
			if current == goal:
				break
			for nb in self.get_neighbors(current):
				t = g_score[current] + 16
				if nb not in g_score or t < g_score[nb]:
					came_from[nb] = current
					g_score[nb]   = t
					heapq.heappush(open_set, (t + self.heuristic(nb, goal), nb))

		path, cur = [], goal
		while cur in came_from:
			path.append(cur)
			cur = came_from[cur]
		path.reverse()
		return path, len(path)

	def _astar_cpp(self, start: Vector2, goal: Vector2) -> list[Vector2]:
		"""Run C++ A*. Returns path (excluding start) or [] on any failure."""
		try:
			raw = _cpp_mod.astar_from_csv(self._map_csv, (start.x, start.y), (goal.x, goal.y))
		except Exception:
			self._use_cpp = False  # permanent fallback for this instance
			return []
		if not raw:
			return []
		path = [Vector2(x, y) for x, y in raw]
		if path and path[0] == start:
			path = path[1:]
		return path

	def _plan_path(self, start: Vector2, goal: Vector2) -> list[Vector2]:
		"""Return absolute path from start to goal using best available backend."""
		if self._use_cpp:
			path = self._astar_cpp(start, goal)
			if path:
				return path
			# cpp returned empty (unreachable) — fall through to Python
		path, _ = self.astar(start, goal)
		return path

	def path_find_to(self, goal: Vector2) -> list[Vector2]:
		if self.status != STATUS.IDLE:
			return []
		if isinstance(goal, (tuple, list)):
			goal = Vector2(goal[0], goal[1])

		absolute_path = self._plan_path(self.pos, goal)
		dirs, prev    = [], self.pos

		for node in absolute_path:
			dx = int(np.clip(node.x - prev.x, -1, 1))
			dy = int(np.clip(node.y - prev.y, -1, 1))
			dirs.append(Vector2(dx, dy))
			prev = node

		self.path   = dirs
		self.status = STATUS.MOVE
		return dirs

# ---------------- MINING ----------------

	def mine(self):
		tile_mark = self.sim.map_obj.get_tile(self.pos)
		if tile_mark not in self.sim.map_obj.mineral_markers or self.status == STATUS.MINE:
			return
		self.mine_process_hrs = self.MINING_TIME_HRS
		self.status = STATUS.MINE

	def mine_finished(self):
		tile_mark = self.sim.map_obj.get_tile(self.pos)
		self.status = STATUS.IDLE
		self.mine_process_hrs = 0.0
		self.mined.append(self.pos._dict())
		self.storage[tile_mark] += 1
		self.sim.map_obj.set_tile(self.pos, self.sim.map_obj.path_marker)

# ---------------- FRAME UPDATE ----------------

	def update(self, delta_hrs: float):
		if not self.sim.is_running or delta_hrs <= 0:
			return

		if self.status == STATUS.MOVE and self.path:
			self.move_progress += self.gear.value * delta_hrs
			while self.move_progress >= 1.0 and self.path:
				d = self.path.pop(0)
				self.pos = Vector2(self.pos.x + d.x, self.pos.y + d.y)
				self.distance_travelled += 1
				self.move_progress -= 1.0
			if not self.path:
				self.status = STATUS.IDLE

		elif self.status == STATUS.MINE:
			self.mine_process_hrs -= delta_hrs
			if self.mine_process_hrs <= 0:
				self.mine_finished()
		else:
			self.status = STATUS.IDLE

		self.battery = float(np.clip(
			self.battery + self.energy_produced(delta_hrs) - self.energy_consumed(delta_hrs),
			0, self.MAX_BATTERY_CHARGE,
		))
		if self.battery <= 0:
			self.status = STATUS.DEAD

# ---------------- SERVER LOGGING ----------------

	def get_live_data(self, delta_hrs: float) -> dict:
		return {
			"time_of_day":              self.sim.elapsed_hrs % (self.sim.day_hrs + self.sim.night_hrs),
			"elapsed_hrs":              self.sim.elapsed_hrs,
			"rover_position":           self.pos._dict(),
			"rover_battery":            self.battery,
			"rover_storage":            self.storage,
			"rover_speed":              self.gear.value,
			"rover_status":             self.status.name,
			"rover_distance_travelled": self.distance_travelled,
			"rover_path_plan":          [v._dict() for v in self.path],
			"rover_energy_consumption": self.energy_consumed(delta_hrs),
			"rover_energy_production":  self.energy_produced(delta_hrs),
			"rover_mined":              self.mined,
		}

	def get_setup_data(self) -> dict:
		return {
			"map_matrix":                        self.sim.map_obj.map_data,
			"day_hrs":                           self.sim.day_hrs,
			"night_hrs":                         self.sim.night_hrs,
			"run_hrs":                           self.sim.run_hrs,
			"sim_time_multiplier":               self.sim.sim_time_multiplier,
			"markers":                           self.sim.map_obj.marker_descriptions,
			"rover_name":                        self.id,
			"rover_max_battery":                 self.MAX_BATTERY_CHARGE,
			"rover_mining_consumption_per_hr":   self.MINING_CONSUMPTION_PER_HR,
			"rover_standby_consumption_per_hr":  self.STANDBY_CONSUMPTION_PER_HR,
			"rover_charge_per_hr":               self.DAY_CHARGE_PER_HR,
			"rover_mine_hrs":                    self.MINING_TIME_HRS,
			"rover_mode":                        "machine_learning",
		}

	def __repr__(self):
		line        = "=" * 40
		storage_str = ", ".join(f"{k}:{v}" for k, v in self.storage.items() if v > 0) or "empty"
		return (
			f"\n{line}\n"
			f"ROVER [{self.id}]\n"
			f"{line}\n"
			f"Status    : {self.status.value}\n"
			f"Position  : ({self.pos.x}, {self.pos.y})\n"
			f"Speed     : {self.gear.value}\n"
			f"Battery   : {self.battery:.2f} / {self.MAX_BATTERY_CHARGE}\n"
			f"Distance  : {self.distance_travelled} tiles\n"
			f"move_prcs : {self.move_progress}\n"
			f"Path left : {len(self.path)} nodes\n"
			f"Storage   : {storage_str}\n"
			f"Path      : {self.path}\n"
			f"{line}"
		)
