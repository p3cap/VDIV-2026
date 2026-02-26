# TODO example code, review, rewrite latR


"""
RoverEnv: Gym environment for Mars Rover with ML training.
Based on ML_config.md specifications.
"""

import gymnasium as gym
from gymnasium import spaces
import numpy as np
from typing import List
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from MapClass import Map, matrix_from_csv
from RoverClass import Rover, STATUS, GEARS
from Simulation import Simulation
from Global import Vector2


class RoverEnv(gym.Env):
	"""
	Custom gym environment for Mars Rover ML training.
	
	Inputs (normalized 0-1):
	- Rover state: pos_x, pos_y, battery, gear, run_hrs, time_of_day
	- Closest N minerals: each has (pos_x, pos_y, distance)
	
	Outputs (discrete):
	- Action 0-2: set_gear (0, 1, 2 = SLOW, NORMAL, FAST)
	- Action 3-32: goto mineral (indices 0-29)
	- Action 33-34: mine start/stop
	"""
	
	N_MINERALS = 30  # Number of closest minerals to track
	
	def __init__(
		self,
		map_path: str,
		run_hrs: float = 24.0,
		max_steps: int = 1000,
		sim_multiplier: float = 1.0,
	):
		"""
		Initialize the RoverEnv.
		
		Args:
			map_path: Path to the CSV map file
			run_hrs: Maximum simulation hours
			max_steps: Maximum environment steps per episode
			sim_multiplier: Simulation time multiplier
		"""
		super().__init__()
		
		# Load map
		map_data = matrix_from_csv(map_path)
		self.map_obj = Map(map_data)
		
		# Create simulation
		self.sim = Simulation(
			map_obj=self.map_obj,
			run_hrs=run_hrs,
			sim_time_multiplier=sim_multiplier,
		)
		
		# Create rover
		self.rover = Rover(id="ML_Rover", sim=self.sim)
		
		self.max_steps = max_steps
		self.step_count = 0
		self.delta_hrs = run_hrs / max_steps  # Time delta per step
		
		# Discrete action space:
		# 0-2: set gear (3 gears)
		# 3-32: go to mineral (30 minerals)
		# 33: mine
		self.action_space = spaces.Discrete(34)
		
		# Observation space (normalized):
		# rover_state (6) + minerals (30 * 3) = 96 dimensions
		obs_size = 6 + (self.N_MINERALS * 3)
		self.observation_space = spaces.Box(low=0.0, high=1.0, shape=(obs_size,), dtype=np.float32)
		
		self.initial_storage = None
		
	def _get_closest_minerals(self, limit: int = N_MINERALS) -> List[tuple]:
		"""Get closest N minerals to rover position."""
		minerals = []
		
		for mineral_marker in self.map_obj.mineral_markers:
			poses = self.map_obj.get_poses_of_tile(mineral_marker)
			for pos in poses:
				dist = abs(pos.x - self.rover.pos.x) + abs(pos.y - self.rover.pos.y)
				minerals.append((pos.x, pos.y, dist))
		
		# Sort by distance and take closest N
		minerals.sort(key=lambda m: m[2])
		return minerals[:limit]
	
	def _normalize_value(self, value: float, min_val: float, max_val: float) -> float:
		"""Normalize a value to [0, 1] range."""
		if max_val == min_val:
			return 0.5
		return np.clip((value - min_val) / (max_val - min_val), 0.0, 1.0)
	
	def _get_observation(self) -> np.ndarray:
		"""Get normalized observation from rover state."""
		obs = []
		
		# Rover state (6 values)
		obs.append(self._normalize_value(self.rover.pos.x, 0, self.map_obj.width))
		obs.append(self._normalize_value(self.rover.pos.y, 0, self.map_obj.height))
		obs.append(self._normalize_value(self.rover.battery, 0, self.rover.MAX_BATTERY_CHARGE))
		
		# Gear (0, 0.5, 1 for SLOW, NORMAL, FAST)
		gear_map = {GEARS.SLOW: 0.0, GEARS.NORMAL: 0.5, GEARS.FAST: 1.0}
		obs.append(gear_map.get(self.rover.gear, 0.5))
		
		# Run hours progress
		obs.append(self._normalize_value(self.sim.elapsed_hrs, 0, self.sim.run_hrs))
		
		# Time of day (24 hour cycle)
		cycle = self.sim.day_hrs + self.sim.night_hrs
		time_of_day = self.sim.elapsed_hrs % cycle
		obs.append(self._normalize_value(time_of_day, 0, cycle))
		
		# Closest minerals (30 entries, each with x, y, distance)
		closest_minerals = self._get_closest_minerals(self.N_MINERALS)
		
		for i in range(self.N_MINERALS):
			if i < len(closest_minerals):
				x, y, dist = closest_minerals[i]
				obs.append(self._normalize_value(x, 0, self.map_obj.width))
				obs.append(self._normalize_value(y, 0, self.map_obj.height))
				# Normalize distance (max possible = width + height)
				max_dist = self.map_obj.width + self.map_obj.height
				obs.append(self._normalize_value(dist, 0, max_dist))
			else:
				# Pad with zeros if not enough minerals
				obs.extend([0.0, 0.0, 0.0])
		
		return np.array(obs, dtype=np.float32)
	
	def _calculate_reward(self) -> float:
		"""Calculate reward based on mined minerals and survival."""
		reward = 0.0
		
		# Reward for mined minerals
		current_storage = sum(self.rover.storage.values())
		mined_this_step = current_storage - sum(self.initial_storage.values())
		reward += mined_this_step * 10.0
		
		# Small penalty for each step (encourages efficiency)
		reward -= 0.01
		
		# Penalty for dying
		if self.rover.status == STATUS.DEAD:
			reward -= 50.0
		
		# Bonus for surviving with good battery
		if self.rover.battery > 50:
			reward += 0.1
		
		return reward
	
	def _execute_action(self, action: int):
		"""Execute the given action."""
		if action < 3:
			# Set gear
			gears = [GEARS.SLOW, GEARS.NORMAL, GEARS.FAST]
			self.rover.gear = gears[action]
		
		elif action < 33:
			# Go to mineral
			mineral_idx = action - 3
			closest_minerals = self._get_closest_minerals(self.N_MINERALS)
			
			if mineral_idx < len(closest_minerals):
				x, y, _ = closest_minerals[mineral_idx]
				goal = Vector2(x, y)
				self.rover.path_find_to(goal)
		
		elif action == 33:
			# Mine
			self.rover.mine()
	
	def reset(self, seed=None, options=None):
		"""Reset environment to initial state."""
		super().reset(seed=seed)
		
		# Create new simulation and rover
		map_data = matrix_from_csv(
			str(Path(__file__).parent.parent / "data" / "mars_map_50x50.csv")
		)
		self.map_obj = Map(map_data)
		self.sim = Simulation(
			map_obj=self.map_obj,
			run_hrs=self.sim.run_hrs,
			sim_time_multiplier=self.sim.sim_time_multiplier,
		)
		
		self.rover = Rover(id="ML_Rover", sim=self.sim)
		self.initial_storage = self.rover.storage.copy()
		self.step_count = 0
		
		obs = self._get_observation()
		info = {}
		
		return obs, info
	
	def step(self, action: int):
		"""Execute one step of the environment."""
		# Store initial storage for reward calculation
		if self.initial_storage is None:
			self.initial_storage = self.rover.storage.copy()
		
		# Execute action
		self._execute_action(action)
		
		# Update simulation
		self.sim.update(self.delta_hrs)
		self.rover.update(self.delta_hrs)
		
		# Get observation and reward
		obs = self._get_observation()
		reward = self._calculate_reward()
		
		# Check termination conditions
		self.step_count += 1
		terminated = self.rover.status == STATUS.DEAD or not self.sim.is_running
		truncated = self.step_count >= self.max_steps
		done = terminated or truncated
		
		info = {
			"minerals_collected": sum(self.rover.storage.values()),
			"battery": self.rover.battery,
			"distance_travelled": self.rover.distance_travelled,
			"elapsed_hrs": self.sim.elapsed_hrs,
		}
		
		return obs, reward, terminated, truncated, info
	
	def render(self, mode="human"):
		"""Render the environment (for debugging)."""
		pass
	
	def close(self):
		"""Close the environment."""
		pass
