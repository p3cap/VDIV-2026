"""
PPO based ML traning for a mars rover envirement
More info: doc/PPO_machine_learning_doc.md
"""
import os
import sys
import time
from pathlib import Path

import gymnasium as gym
import numpy as np
import torch
from gymnasium import spaces
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv

MARS_ROVER_ROOT = Path(__file__).parent.parent
sys.path.append(str(MARS_ROVER_ROOT))

from Global import Vector2
from RoverClass import GEARS, STATUS
from Simulation_env import RoverSimulationWorld

GEAR_TO_FLOAT = {GEARS.SLOW: 0.0, GEARS.NORMAL: 0.5, GEARS.FAST: 1.0}  # for rl input/output

class MinuteProgressCallback(BaseCallback):
    def __init__(self, total_timesteps: int, log_every_seconds: int = 60, step_check_interval: int = 1024):
        super().__init__(verbose=0)
        self.total_timesteps = max(1, int(total_timesteps))
        self.log_every_seconds = max(1, int(log_every_seconds))
        self.step_check_interval = max(1, int(step_check_interval))
        self._start_wall = 0.0
        self._last_log_wall = 0.0
        self._start_steps = 0
        self._next_step_check = 0

    def _on_training_start(self) -> None:
        now = time.perf_counter()
        self._start_wall = now
        self._last_log_wall = now
        self._start_steps = int(self.model.num_timesteps)
        self._next_step_check = self._start_steps + self.step_check_interval
        print(f"Progress: 0/{self.total_timesteps} (0.0%)")

    def _print_progress(self):
        elapsed = max(1e-9, time.perf_counter() - self._start_wall)
        run_steps = max(0, int(self.num_timesteps) - self._start_steps)
        pct = min(100.0, (run_steps / self.total_timesteps) * 100.0)
        fps = run_steps / elapsed
        print(f"Progress: {run_steps}/{self.total_timesteps} ({pct:.1f}%), elapsed={elapsed:.1f}s, fps={fps:.1f}")

    def _on_step(self) -> bool:
        # Avoid wall-clock checks on every callback hit.
        if int(self.num_timesteps) < self._next_step_check:
            return True

        self._next_step_check = int(self.num_timesteps) + self.step_check_interval
        now = time.perf_counter()
        if now - self._last_log_wall >= self.log_every_seconds:
            self._print_progress()
            self._last_log_wall = now
        return True

    def _on_training_end(self) -> None:
        self._print_progress()


class RoverSimpleEnv(gym.Env):
    metadata = {"render_modes": []}
    NO_MOVE_PENALTY_BASE = 2.0
    NO_MOVE_PENALTY_STREAK = 0.5
    NO_MOVE_PENALTY_CAP = 8.0

    def __init__(self, run_hrs: float = 24.0, delta_hrs: float = 0.5, mineral_count: int = 30):
        super().__init__()
        self.run_hrs = run_hrs
        self.delta_hrs = delta_hrs
        self.mineral_count = mineral_count
        self.prev_mined = Vector2(0, 0)
        self.no_move_streak = 0

        self.world = RoverSimulationWorld(
            run_hrs=run_hrs,
            delta_mode="set_time",
            set_delta_hrs=delta_hrs,
            tick_seconds=0.0,
            env_speed=1.0,
            web_logger=False,
        )

        self.obs_size = 9 + (self.mineral_count * 3)
        self.action_space = spaces.Discrete(3 + self.mineral_count + 1)
        self.observation_space = spaces.Box(low=0.0, high=1.0, shape=(self.obs_size,), dtype=np.float32)

        self._obs_buffer = np.zeros(self.obs_size, dtype=np.float32)
        self._cycle_hours = self.world.sim.day_hrs + self.world.sim.night_hrs
        self._storage_norm = max(1.0, float(self.mineral_count * 100))

        self._rank_cache_key = None
        self._rank_cache = []
        self._cached_minerals = []
        self._minerals_version = 0
        self._total_mined = 0
        self._refresh_minerals()

    def _refresh_minerals(self):
        self._cached_minerals = list(self.world.minerals())
        self._minerals_version += 1
        self._rank_cache_key = None
        self._rank_cache = []

    def _apply_absolute_path(self, absolute_path: list[Vector2]) -> bool:
        rover = self.world.rover
        if not absolute_path:
            return False

        dirs = []
        prev = rover.pos
        for node in absolute_path:
            dx = node.x - prev.x
            dy = node.y - prev.y

            if dx < -1:
                dx = -1
            elif dx > 1:
                dx = 1

            if dy < -1:
                dy = -1
            elif dy > 1:
                dy = 1

            dirs.append(Vector2(dx, dy))
            prev = node

        if not dirs:
            return False

        rover.path = dirs
        rover.status = STATUS.MOVE
        return True

    def _get_ranked_minerals(self):
        minerals = self._cached_minerals
        if not minerals:
            self._rank_cache_key = None
            self._rank_cache = []
            return self._rank_cache

        rover = self.world.rover
        state_key = (rover.pos.x, rover.pos.y, self._minerals_version, self.mineral_count)
        if self._rank_cache_key == state_key:
            return self._rank_cache

        # Fast path for current training profile (mineral_count=1).
        if self.mineral_count == 1:
            found_goal, abs_path, dist = rover.astar_to_any(rover.pos, minerals)
            if found_goal is None:
                ranked = []
            else:
                dist = float(dist)
                if dist == 0 and found_goal != rover.pos:
                    dist = float("inf")
                ranked = [(found_goal, dist, abs_path)]

            self._rank_cache_key = state_key
            self._rank_cache = ranked
            return ranked

        ranked = []
        for mineral in minerals:
            abs_path, dist = rover.astar(rover.pos, mineral)
            if dist == 0 and mineral != rover.pos:
                dist = float("inf")
            ranked.append((mineral, float(dist), abs_path))

        ranked.sort(key=lambda item: (item[1], item[0].x, item[0].y))
        ranked = ranked[: self.mineral_count]
        self._rank_cache_key = state_key
        self._rank_cache = ranked
        return ranked

    def _obs(self):
        rover = self.world.rover
        sim = self.world.sim
        obs = self._obs_buffer
        obs.fill(0.0)

        obs[0] = rover.pos.x * self.world.inv_w
        obs[1] = rover.pos.y * self.world.inv_h
        obs[2] = rover.battery / rover.MAX_BATTERY_CHARGE
        obs[3] = min(1.0, self.run_hrs / 240.0)
        obs[4] = GEAR_TO_FLOAT[rover.gear]
        obs[5] = (sim.elapsed_hrs % self._cycle_hours) / self._cycle_hours
        obs[6] = self.prev_mined.x * self.world.inv_w
        obs[7] = self.prev_mined.y * self.world.inv_h
        obs[8] = min(1.0, self._total_mined / self._storage_norm)

        ranked = self._get_ranked_minerals()
        for i in range(self.mineral_count):
            base = 9 + (i * 3)
            if i >= len(ranked):
                break
            pos, dist, _ = ranked[i]
            obs[base] = 1.0 if not np.isfinite(dist) else min(1.0, dist / self.world.max_dist)
            obs[base + 1] = pos.x * self.world.inv_w
            obs[base + 2] = pos.y * self.world.inv_h

        return obs

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self.world.reset()
        self.prev_mined = Vector2(0, 0)
        self.no_move_streak = 0
        self._cycle_hours = self.world.sim.day_hrs + self.world.sim.night_hrs
        self._refresh_minerals()
        self._total_mined = len(self.world.rover.mined)
        return self._obs(), {}

    def _compute_reward(self, mined_now: float, dist_gain: float, battery_cost: float, minerals_left: int, is_dead: bool) -> float:
        reward = mined_now * 20.0 + (dist_gain * 0.1) - (battery_cost * 0.02) - 0.05
        if dist_gain <= 0 and mined_now <= 0:
            self.no_move_streak += 1
            reward -= min(
                self.NO_MOVE_PENALTY_CAP,
                self.NO_MOVE_PENALTY_BASE + (self.NO_MOVE_PENALTY_STREAK * self.no_move_streak),
            )
        else:
            self.no_move_streak = 0

        if is_dead:
            reward -= 200.0
        if minerals_left == 0:
            reward += 50.0
        return reward

    def step(self, action):
        rover = self.world.rover
        sim = self.world.sim
        prev_battery = rover.battery
        prev_distance = rover.distance_travelled
        prev_mined_amount = self._total_mined

        if action == 0:
            rover.gear = GEARS.SLOW
        elif action == 1:
            rover.gear = GEARS.NORMAL
        elif action == 2:
            rover.gear = GEARS.FAST
        elif 3 <= action < 3 + self.mineral_count and rover.status == STATUS.IDLE:
            mineral_idx = action - 3
            ranked = self._get_ranked_minerals()
            if mineral_idx < len(ranked):
                target_mineral, _, abs_path = ranked[mineral_idx]
                planned = self._apply_absolute_path(abs_path) or bool(rover.path_find_to(target_mineral))
                if planned:
                    self.prev_mined = target_mineral
        elif action == 3 + self.mineral_count and rover.status == STATUS.IDLE:
            rover.mine()

        _, _ = self.world.step(sleep=False)
        self._rank_cache_key = None

        self._total_mined = len(rover.mined)
        mined_now = self._total_mined - prev_mined_amount
        if mined_now > 0:
            self._refresh_minerals()

        battery_cost = max(0.0, prev_battery - rover.battery)
        dist_gain = rover.distance_travelled - prev_distance
        minerals_left = len(self._cached_minerals)
        is_dead = rover.status == STATUS.DEAD
        terminated = is_dead or (minerals_left == 0) or (not sim.is_running)
        reward = self._compute_reward(mined_now, dist_gain, battery_cost, minerals_left, is_dead)

        return self._obs(), float(reward), terminated, False, {}

def resolve_device(device: str) -> str:  # device optimisation when training
    return "cuda" if device == "auto" and torch.cuda.is_available() else ("cpu" if device == "auto" else device)

def tune_torch_runtime(device: str):
    if device != "cuda":
        return

    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
    torch.backends.cudnn.benchmark = True
    torch.set_float32_matmul_precision("high")

def choose_ppo_batch_params(n_envs: int) -> tuple[int, int]:
    # Throughput-oriented defaults: fewer optimizer phases per env step.
    n_steps = 1024
    rollout_batch = max(1, n_steps * n_envs)
    batch_size = min(rollout_batch, 2048)

    # Keep batch_size as a clean divisor to avoid partial mini-batches.
    while batch_size > 32 and (rollout_batch % batch_size) != 0:
        batch_size //= 2

    return n_steps, max(32, batch_size)

def compute_parallelism(device: str, cpu_limit: float, n_envs: int, torch_threads: int):
    cpu_limit = min(1.0, max(0.01, float(cpu_limit)))
    cpu_budget = max(1, int(round((os.cpu_count() or 1) * cpu_limit)))

    if n_envs <= 0:
        n_envs = max(1, cpu_budget - 1) if device == "cuda" else max(1, int(round(cpu_budget * 0.8)))
    n_envs = min(max(1, int(n_envs)), cpu_budget)

    if torch_threads <= 0:
        torch_threads = 1 if device == "cuda" else max(1, cpu_budget - n_envs)
    torch_threads = min(max(1, int(torch_threads)), cpu_budget)
    return cpu_budget, n_envs, torch_threads

def build_vec_env(n_envs: int):
    def make_env():
        return RoverSimpleEnv(mineral_count=1)

    return SubprocVecEnv([make_env for _ in range(n_envs)]) if n_envs > 1 else DummyVecEnv([make_env])

def train_model(timesteps: int, out_path: str, device: str = "auto", cpu_limit: float = 1.0, n_envs: int = 0, torch_threads: int = 0):
    start_time = time.perf_counter()
    resolved_device = resolve_device(device)
    cpu_budget, n_envs, torch_threads = compute_parallelism(resolved_device, cpu_limit, n_envs, torch_threads)
    tune_torch_runtime(resolved_device)
    ppo_n_steps, ppo_batch_size = choose_ppo_batch_params(n_envs)

    torch.set_num_threads(torch_threads)
    try:
        torch.set_num_interop_threads(max(1, min(4, torch_threads)))
    except RuntimeError:
        pass

    print(
        "Training setup:"
        f" device={resolved_device}, timesteps={timesteps}, cpu_budget={cpu_budget},"
        f" n_envs={n_envs}, torch_threads={torch_threads},"
        f" n_steps={ppo_n_steps}, batch_size={ppo_batch_size}, n_epochs=4"
    )

    vec_env = build_vec_env(n_envs)
    model_base = Path(out_path).with_suffix("") if Path(out_path).suffix == ".zip" else Path(out_path)
    model_zip = model_base.with_suffix(".zip")

    if model_zip.exists() and model_zip.stat().st_size > 0:
        print(f"Resuming model: {model_zip}")
        model = PPO.load(str(model_zip), env=vec_env, device=resolved_device)
        reset_num_timesteps = False
    else:
        print("Starting new PPO model")
        model = PPO(
            "MlpPolicy",
            vec_env,
            verbose=0,
            device=resolved_device,
            n_steps=ppo_n_steps,
            batch_size=ppo_batch_size,
            n_epochs=4,
        )
        reset_num_timesteps = True

    model.learn(
        total_timesteps=timesteps,
        reset_num_timesteps=reset_num_timesteps,
        callback=MinuteProgressCallback(
            total_timesteps=timesteps,
            log_every_seconds=60,
            step_check_interval=max(1024, n_envs * 256),
        ),
    )

    model.save(str(model_base))
    latest_file = model_base.parent / "latest_ppo_model.txt"
    latest_file.write_text(model_base.name, encoding="utf-8")

    vec_env.close()
    elapsed = time.perf_counter() - start_time
    print(f"Training finished in {elapsed:.1f}s")
    print(f"Saved model: {model_base}.zip")


def main():
    timesteps = 10000000
    cpu_limit = 1.0
    n_envs = 0
    torch_threads = 0
    device = "auto"

    trained_dir = MARS_ROVER_ROOT / "MachineLearning" / "trained"

    models = sorted(trained_dir.glob("*.zip"))  # list avaliable models
    print("\nAvailable models:")
    for idx, model_file in enumerate(models, start=1):
        print(f"  {idx}. {model_file.stem}")
    print()

    model_name = input("Model name [rover_ppo_simple]: ").strip() or "rover_ppo_simple"
    out_path = str(trained_dir / model_name)

    train_model(
        timesteps=timesteps,
        out_path=out_path,
        device=device,
        cpu_limit=cpu_limit,
        n_envs=n_envs,
        torch_threads=torch_threads,
    )


if __name__ == "__main__":
    main()