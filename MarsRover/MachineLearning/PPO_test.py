import argparse
import os
import sys
import time
from pathlib import Path
from datetime import datetime

import gymnasium as gym
import numpy as np
import torch
from gymnasium import spaces
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv

MARS_ROVER_ROOT = Path(__file__).parent.parent
sys.path.append(str(MARS_ROVER_ROOT))

from MapClass import Map, matrix_from_csv
from RoverClass import GEARS, STATUS, Rover
from Simulation import Simulation
from Global import Vector2


def ts_print(message: str): # time stapmed print
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {message}")


class RoverSimpleEnv(gym.Env):
    """Gymnasium env for rover trainer"""

    metadata = {"render_modes": []}

    def __init__(self, run_hrs: float = 24.0, delta_hrs: float = 0.5, mineral_count: int = 30):
        super().__init__()
        self.run_hrs = run_hrs
        self.delta_hrs = delta_hrs
        self.mineral_count = mineral_count
        self.prev_mined = Vector2(0,0)

        # Actions: 0-2 set gear, 3-(3+mineral_count-1) goto mineral, last action mine
        self.action_space = spaces.Discrete(3 + mineral_count + 1)
        # [x, y, battery, run_hrs, gear, time_of_day, prev_x, prev_y] + [min_dist, min_x, min_y] * mineral_count
        obs_size = 9 + (mineral_count * 3)
        self.observation_space = spaces.Box(low=0.0, high=1.0, shape=(obs_size,), dtype=np.float32)

        self.map_path = MARS_ROVER_ROOT / "data" / "mars_map_50x50.csv"
        self.max_dist = 0.0
        self._rank_cache_key = None
        self._rank_cache = []
        self._build_world()

    # setup simulation 
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
        # Upper bound for normalized A* distance on grid.
        self.max_dist = max(1.0, float(map_obj.width * map_obj.height))
        self._rank_cache_key = None
        self._rank_cache = []

    def _get_ranked_minerals(self):
        minerals = self.sim.map_obj.get_poses_of_tiles(self.sim.map_obj.mineral_markers)
        mineral_key = tuple(sorted((m.x, m.y) for m in minerals))
        state_key = (self.rover.pos.x, self.rover.pos.y, mineral_key)

        if self._rank_cache_key == state_key:
            return self._rank_cache

        ranked = []
        for mineral in minerals:
            print("astar")
            abs_path, dist = self.rover.astar(self.rover.pos, mineral)
            rel_steps = []
            # Stable fallback for unreachable/invalid results.
            if mineral != self.rover.pos and (not np.isfinite(dist) or dist <= 0):
                dist = float("inf")

            if np.isfinite(dist) and len(abs_path) > 0:
                prev = self.rover.pos
                for node in abs_path:
                    rel_steps.append(Vector2(node.x - prev.x, node.y - prev.y))
                    prev = node

            ranked.append((mineral, float(dist), rel_steps))

        ranked.sort(key=lambda item: (item[1], item[0].x, item[0].y))
        self._rank_cache_key = state_key
        self._rank_cache = ranked
        return ranked

    def _obs(self): # inputs to the neural network
        m = self.sim.map_obj
        cycle = self.sim.day_hrs + self.sim.night_hrs

        #  [x, y, battery, run_hrs, gear, time_of_day, prev_mined_x, prev_mined_y, mined_count]
        obs = np.array(
            [
                self.rover.pos.x / max(1, m.width - 1),
                self.rover.pos.y / max(1, m.height - 1),
                self.rover.battery / self.rover.MAX_BATTERY_CHARGE,
                min(1, self.run_hrs / 240),  # 10+ days -> lot of time to discover
                list(GEARS).index(self.rover.gear) / (len(GEARS) - 1),
                (self.sim.elapsed_hrs % cycle) / cycle,
                self.prev_mined.x / max(1, m.width - 1),
                self.prev_mined.y / max(1, m.height - 1),
                min(1.0, sum(self.rover.storage.values()) / (self.mineral_count * 100)),  # normalized mined count
            ],
            dtype=np.float32,
        )

        # mineral distances and positions
        ranked = self._get_ranked_minerals()[:self.mineral_count]
        mineral_input = [
            (dist, pos.x, pos.y) for pos, dist, _ in ranked
        ]
        
        # Pad with zeros if fewer minerals than expected
        while len(mineral_input) < self.mineral_count:
            mineral_input.append((0.0, 0.0, 0.0))
        
        # Normalize mineral data: [distance, x, y]
        mineral_data = []
        for dist, x, y in mineral_input:
            if not np.isfinite(dist):
                mineral_data.append(1.0)
            else:
                mineral_data.append(min(1.0, dist / self.max_dist))  # normalize distance
            mineral_data.append(x / max(1, m.width - 1))  # normalize x
            mineral_data.append(y / max(1, m.height - 1))  # normalize y

        return np.concatenate([obs, np.array(mineral_data, dtype=np.float32)])

    # reset....
    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self._build_world()
        return self._obs(), {}

    # one step in the simulation
    def step(self, action):
        prev_battery = self.rover.battery
        prev_distance = self.rover.distance_travelled
        prev_mined_amount = sum(self.rover.storage.values())
        ranked = self._get_ranked_minerals()

        if action == 0:
            self.rover.gear = GEARS.SLOW
        elif action == 1:
            self.rover.gear = GEARS.NORMAL
        elif action == 2:
            self.rover.gear = GEARS.FAST
        elif 3 <= action < 3 + self.mineral_count and self.rover.status == STATUS.IDLE:
            # Actions 3 to 3+mineral_count-1: go to mineral at index (action - 3)
            mineral_idx = action - 3
            if mineral_idx < len(ranked):
                target_mineral, dist, rel_steps = ranked[mineral_idx]
                if np.isfinite(dist) and len(rel_steps) > 0:
                    self.rover.move_progress = 0.0
                    self.rover.path = rel_steps
                    self.rover.status = STATUS.MOVE
                    # Track last successfully planned target.
                    self.prev_mined = target_mineral
        elif action == 3 + self.mineral_count and self.rover.status == STATUS.IDLE:
            # Last action: mine
            self.rover.mine()

        self.sim.update(self.delta_hrs)
        self.rover.update(self.delta_hrs)

        mined_now = sum(self.rover.storage.values()) - prev_mined_amount

        battery_cost = max(0.0, prev_battery - self.rover.battery)
        dist_gain = self.rover.distance_travelled - prev_distance
        minerals_left = len(self.sim.map_obj.get_poses_of_tiles(self.sim.map_obj.mineral_markers))

        # REWARD
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


def train_model(timesteps: int, out_path: str, device: str = "auto", n_envs: int = 1, torch_threads: int | None = None, cpu_limit: float = 0.9):

    start_time = time.perf_counter()
    cpu_limit = max(0.01, min(1.0, cpu_limit))
    cpu_budget = max(1, int(round((os.cpu_count() or 1) * cpu_limit)))
    resolved_device = "cuda" if device == "auto" and torch.cuda.is_available() else device

    if torch_threads is None:
        torch_threads = cpu_budget
    else:
        torch_threads = min(max(1, torch_threads), cpu_budget)

    if n_envs <= 0:
        n_envs = max(1, cpu_budget // 2)
    n_envs = min(max(1, n_envs), cpu_budget)

    if torch_threads > 0:
        torch.set_num_threads(torch_threads)

    ts_print(
        "Training setup:"
        f" device={resolved_device}, timesteps={timesteps}, cpu_limit={cpu_limit:.2f},"
        f" cpu_budget={cpu_budget}, n_envs={n_envs}, torch_threads={torch_threads}"
    )

    def make_env():
        return RoverSimpleEnv(mineral_count=1)

    if n_envs > 1:
        vec_env = SubprocVecEnv([make_env for _ in range(n_envs)])
    else:
        vec_env = DummyVecEnv([make_env])

    ts_print("Starting PPO learn()")
    model = PPO("MlpPolicy", vec_env, verbose=1, device=device)
    model.learn(total_timesteps=timesteps)
    elapsed = time.perf_counter() - start_time
    ts_print(f"Training finished in {elapsed:.1f}s")
    model.save(out_path)
    vec_env.close()
    ts_print(f"Saved model: {out_path}.zip")


def main():

    # computer rescources limit
    parser = argparse.ArgumentParser(description="Simple PPO training for rover env.")
    parser.add_argument("--timesteps", type=int, default=100_000)
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        choices=["auto", "cpu", "cuda"],
        help="Torch device: auto (default), cpu, or cuda.",
    )
    parser.add_argument( 
        "--cpu-limit",
        type=float,
        default=0.9,
        help="CPU cap from 0.01 to 1.0 (1.0 = 100%%, 0.5 = 50%%).",
    )
    parser.add_argument(
        "--n-envs",
        type=int,
        default=0,
        help="Parallel environments (0 = auto from --cpu-limit).",
    )
    parser.add_argument(
        "--torch-threads",
        type=int,
        default=0,
        help="Torch CPU threads (0 = auto from --cpu-limit).",
    )
    parser.add_argument( # Trainder model path
        "--out",
        type=str,
        default=str(MARS_ROVER_ROOT / "MachineLearning" / "trained" / "rover_ppo_simple"),
    )

    # start training process
    args = parser.parse_args()
    train_model(
        timesteps=args.timesteps,
        out_path=args.out,
        device=args.device,
        n_envs=args.n_envs,
        torch_threads=None if args.torch_threads <= 0 else args.torch_threads,
        cpu_limit=args.cpu_limit,
    )


if __name__ == "__main__":
    main()
