import argparse
import math
import sys
from pathlib import Path

import gymnasium as gym
import numpy as np
from gymnasium import spaces
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv

MARS_ROVER_ROOT = Path(__file__).resolve().parent.parent
if str(MARS_ROVER_ROOT) not in sys.path:
    sys.path.append(str(MARS_ROVER_ROOT))

from MapClass import Map, matrix_from_csv
from RoverClass import GEARS, STATUS, Rover
from Simulation import Simulation


class RoverSimpleEnv(gym.Env):
    """Simple Gymnasium environment for training PPO on the rover simulation."""

    metadata = {"render_modes": []}

    def __init__(self, run_hrs: float = 24.0, delta_hrs: float = 0.5, num_minerals: int = 30):
        super().__init__()
        self.run_hrs = run_hrs
        self.delta_hrs = delta_hrs
        self.num_minerals = num_minerals

        # Actions: 0-2 set gear, 3-(3+num_minerals-1) goto mineral, last action mine
        self.action_space = spaces.Discrete(3 + num_minerals + 1)
        # [x, y, battery, run_hrs, gear, time_of_day] + [min_x, min_y, min_dist] * num_minerals
        obs_size = 6 + (num_minerals * 3)
        self.observation_space = spaces.Box(low=0.0, high=1.0, shape=(obs_size,), dtype=np.float32)

        self.map_path = MARS_ROVER_ROOT / "data" / "mars_map_50x50.csv"
        self.max_dist = 1.0
        self._build_world()

    def _build_world(self):
        map_obj = Map(matrix_from_csv(str(self.map_path)))
        self.sim = Simulation(
            map_obj=map_obj,
            run_hrs=self.run_hrs,
            day_hrs=16.0,
            night_hrs=8.0,
            sim_time_multiplier=1.0,
        )
        self.rover = Rover(id="ppo_rover", sim=self.sim)
        self.max_dist = max(1.0, math.hypot(map_obj.width - 1, map_obj.height - 1))
        self.prev_mined = 0

    def _all_minerals(self):
        minerals = []
        for marker in self.sim.map_obj.mineral_markers:
            minerals.extend(self.sim.map_obj.get_poses_of_tile(marker))
        return minerals

    def _nearest_mineral(self):
        minerals = self._all_minerals()
        if not minerals:
            return None, 0.0
        nearest = min(
            minerals,
            key=lambda p: math.hypot(p.x - self.rover.pos.x, p.y - self.rover.pos.y),
        )
        dist = math.hypot(nearest.x - self.rover.pos.x, nearest.y - self.rover.pos.y)
        return nearest, dist

    def _obs(self):
        m = self.sim.map_obj
        cycle = self.sim.day_hrs + self.sim.night_hrs

        if self.rover.gear == GEARS.SLOW:
            gear_norm = 0.0
        elif self.rover.gear == GEARS.NORMAL:
            gear_norm = 0.5
        else:
            gear_norm = 1.0

        # Base state: [x, y, battery, run_hrs, gear, time_of_day]
        obs = np.array(
            [
                self.rover.pos.x / max(1, m.width - 1),
                self.rover.pos.y / max(1, m.height - 1),
                self.rover.battery / self.rover.MAX_BATTERY_CHARGE,
                self.sim.elapsed_hrs / self.run_hrs,
                gear_norm,
                (self.sim.elapsed_hrs % cycle) / cycle,
            ],
            dtype=np.float32,
        )

        # Get all minerals and sort by distance
        minerals = self._all_minerals()
        mineral_distances = [
            (m, math.hypot(m.x - self.rover.pos.x, m.y - self.rover.pos.y))
            for m in minerals
        ]
        mineral_distances.sort(key=lambda x: x[1])

        # Add closest num_minerals minerals (padded with zeros if fewer available)
        mineral_obs = []
        for i in range(self.num_minerals):
            if i < len(mineral_distances):
                mineral_pos, dist = mineral_distances[i]
                mineral_obs.extend([
                    mineral_pos.x / max(1, m.width - 1),
                    mineral_pos.y / max(1, m.height - 1),
                    dist / self.max_dist,
                ])
            else:
                # Pad with zeros if not enough minerals
                mineral_obs.extend([0.0, 0.0, 0.0])

        return np.concatenate([obs, np.array(mineral_obs, dtype=np.float32)])

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self._build_world()
        return self._obs(), {}

    def step(self, action):
        prev_battery = self.rover.battery
        prev_distance = self.rover.distance_travelled
        prev_mined = self.prev_mined

        if action == 0:
            self.rover.gear = GEARS.SLOW
        elif action == 1:
            self.rover.gear = GEARS.NORMAL
        elif action == 2:
            self.rover.gear = GEARS.FAST
        elif 3 <= action < 3 + self.num_minerals and self.rover.status == STATUS.IDLE:
            # Actions 3 to 3+num_minerals-1: go to mineral at index (action - 3)
            mineral_idx = action - 3
            minerals = self._all_minerals()
            mineral_distances = [
                (m, math.hypot(m.x - self.rover.pos.x, m.y - self.rover.pos.y))
                for m in minerals
            ]
            mineral_distances.sort(key=lambda x: x[1])
            if mineral_idx < len(mineral_distances):
                target_mineral, _ = mineral_distances[mineral_idx]
                self.rover.path_find_to(target_mineral)
        elif action == 3 + self.num_minerals and self.rover.status == STATUS.IDLE:
            # Last action: mine
            self.rover.mine()

        self.sim.update(self.delta_hrs)
        self.rover.update(self.delta_hrs)

        mined = sum(self.rover.storage.values())
        mined_now = mined - prev_mined
        self.prev_mined = mined

        battery_cost = max(0.0, prev_battery - self.rover.battery)
        dist_gain = self.rover.distance_travelled - prev_distance
        minerals_left = len(self._all_minerals())

        reward = 0.0
        reward += mined_now * 20.0
        reward += dist_gain * 0.1
        reward -= battery_cost * 0.02
        reward -= 0.05

        terminated = (self.rover.status == STATUS.DEAD) or (minerals_left == 0) or (not self.sim.is_running)
        truncated = False

        if self.rover.status == STATUS.DEAD:
            reward -= 20.0
        if minerals_left == 0:
            reward += 50.0

        return self._obs(), float(reward), terminated, truncated, {}


def train_model(timesteps: int, out_path: str):
    vec_env = DummyVecEnv([lambda: RoverSimpleEnv()])
    model = PPO("MlpPolicy", vec_env, verbose=1)
    model.learn(total_timesteps=timesteps)
    model.save(out_path)
    vec_env.close()
    print(f"Saved model: {out_path}.zip")


def main():
    parser = argparse.ArgumentParser(description="Simple PPO training for rover env.")
    parser.add_argument("--timesteps", type=int, default=100_000)
    parser.add_argument(
        "--out",
        type=str,
        default=str(MARS_ROVER_ROOT / "MachineLearning" / "trained" / "rover_ppo_simple"),
    )
    args = parser.parse_args()
    train_model(args.timesteps, args.out)


if __name__ == "__main__":
    main()
