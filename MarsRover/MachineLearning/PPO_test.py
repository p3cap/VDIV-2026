import os
import sys
import time
from datetime import datetime
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
from MapClass import Map, matrix_from_csv
from RoverClass import GEARS, STATUS, Rover
from Simulation import Simulation

GEAR_TO_FLOAT = {GEARS.SLOW: 0.0, GEARS.NORMAL: 0.5, GEARS.FAST: 1.0}


def ts_print(message: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {message}", flush=True)


class ProgressCallback(BaseCallback):
    def __init__(self, total_timesteps: int, log_interval_steps: int):
        super().__init__()
        self.total_timesteps = max(1, int(total_timesteps))
        self.log_interval_steps = max(1, int(log_interval_steps))
        self._start_time = 0.0
        self._start_timesteps = 0
        self._target_timesteps = self.total_timesteps
        self._next_log = self.log_interval_steps
        self._final_logged = False

    def _on_training_start(self) -> None:
        self._start_time = time.perf_counter()
        self._start_timesteps = int(self.model.num_timesteps)
        self._target_timesteps = self._start_timesteps + self.total_timesteps
        self._next_log = self._start_timesteps + self.log_interval_steps
        ts_print(
            f"Progress: 0/{self.total_timesteps} (0.0%)"
        )

    def _log_progress(self):
        elapsed = max(1e-9, time.perf_counter() - self._start_time)
        run_steps = max(0, int(self.num_timesteps) - self._start_timesteps)
        pct = min(100.0, (run_steps / self.total_timesteps) * 100.0)
        fps = run_steps / elapsed

        ep_reward = None
        if len(self.model.ep_info_buffer) > 0:
            ep_reward = float(np.mean([ep["r"] for ep in self.model.ep_info_buffer]))

        if ep_reward is None:
            ts_print(
                f"Progress: {run_steps}/{self.total_timesteps} ({pct:.1f}%), "
                f"elapsed={elapsed:.1f}s, fps={fps:.1f}"
            )
        else:
            ts_print(
                f"Progress: {run_steps}/{self.total_timesteps} ({pct:.1f}%), "
                f"elapsed={elapsed:.1f}s, fps={fps:.1f}, mean_ep_reward={ep_reward:.2f}"
            )

    def _on_step(self) -> bool:
        if self.num_timesteps >= self._target_timesteps:
            if not self._final_logged:
                self._log_progress()
                self._final_logged = True
            return True

        if self.num_timesteps < self._next_log:
            return True

        self._log_progress()
        self._next_log += self.log_interval_steps
        return True


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

        self.map_path = MARS_ROVER_ROOT / "data" / "mars_map_50x50.csv"
        self.map_template = matrix_from_csv(str(self.map_path))
        self.map_width = len(self.map_template[0])
        self.map_height = len(self.map_template)
        self.inv_w = 1.0 / max(1, self.map_width - 1)
        self.inv_h = 1.0 / max(1, self.map_height - 1)
        self.max_dist = max(1.0, float(self.map_width * self.map_height))
        self.obs_size = 9 + (self.mineral_count * 3)

        self.action_space = spaces.Discrete(3 + self.mineral_count + 1)
        self.observation_space = spaces.Box(low=0.0, high=1.0, shape=(self.obs_size,), dtype=np.float32)

        self._minerals = []
        self._rank_cache_key = None
        self._rank_cache = []
        # Keep A* caches across resets to avoid recomputing same paths/distances.
        self._dist_cache = {}
        self._path_cache = {}
        self._build_world()

    def _build_world(self):
        map_obj = Map([row[:] for row in self.map_template])
        self.sim = Simulation(map_obj=map_obj, run_hrs=self.run_hrs, day_hrs=16.0, night_hrs=8.0, sim_time_multiplier=1.0)
        self.rover = Rover(id="ppo_rover", sim=self.sim)
        self.prev_mined = Vector2(0, 0)
        self.no_move_streak = 0
        self._minerals = list(self.sim.map_obj.get_poses_of_tiles(self.sim.map_obj.mineral_markers))
        self._rank_cache_key = None
        self._rank_cache = []

    def _all_minerals(self):
        return self._minerals

    def _invalidate_cache(self):
        self._rank_cache_key = None
        self._rank_cache = []

    def _astar_distance(self, start: Vector2, goal: Vector2) -> float:
        key = (start.x, start.y, goal.x, goal.y)
        cached = self._dist_cache.get(key)
        if cached is not None:
            return cached

        _, dist = self.rover.astar(start, goal)
        if dist == 0 and goal != start:
            dist = float("inf")
        dist = float(dist)

        self._dist_cache[key] = dist
        if len(self._dist_cache) > 250000:
            self._dist_cache.clear()
        return dist

    def _astar_path(self, start: Vector2, goal: Vector2):
        key = (start.x, start.y, goal.x, goal.y)
        cached_path = self._path_cache.get(key)
        if cached_path is not None:
            return cached_path

        abs_path, dist = self.rover.astar(start, goal)
        if dist == 0 and goal != start:
            dist = float("inf")
        self._dist_cache[key] = float(dist)
        self._path_cache[key] = abs_path
        if len(self._path_cache) > 50000:
            self._path_cache.clear()
        return abs_path

    def _get_ranked_minerals(self):
        mineral_key = tuple((m.x, m.y) for m in self._minerals)
        state_key = (self.rover.pos.x, self.rover.pos.y, mineral_key)
        if self._rank_cache_key == state_key:
            return self._rank_cache

        if self.mineral_count == 1:
            nearest_goal, nearest_path, nearest_dist = self.rover.astar_to_any(self.rover.pos, self._minerals)
            if nearest_goal is None:
                ranked = []
            else:
                ranked = [(nearest_goal, float(nearest_dist), nearest_path)]
        else:
            ranked = []
            for mineral in self._minerals:
                dist = self._astar_distance(self.rover.pos, mineral)
                ranked.append((mineral, dist, None))
            ranked.sort(key=lambda item: (item[1], item[0].x, item[0].y))

        self._rank_cache_key = state_key
        self._rank_cache = ranked
        return ranked

    def _set_rover_path(self, absolute_path):
        prev = self.rover.pos
        rel_steps = []
        for node in absolute_path:
            rel_steps.append(Vector2(node.x - prev.x, node.y - prev.y))
            prev = node
        if rel_steps:
            self.rover.move_progress = 0.0
            self.rover.path = rel_steps
            self.rover.status = STATUS.MOVE

    def _obs(self):
        obs = np.zeros(self.obs_size, dtype=np.float32)
        cycle = self.sim.day_hrs + self.sim.night_hrs

        obs[0] = self.rover.pos.x * self.inv_w
        obs[1] = self.rover.pos.y * self.inv_h
        obs[2] = self.rover.battery / self.rover.MAX_BATTERY_CHARGE
        obs[3] = min(1.0, self.run_hrs / 240.0)
        obs[4] = GEAR_TO_FLOAT[self.rover.gear]
        obs[5] = (self.sim.elapsed_hrs % cycle) / cycle
        obs[6] = self.prev_mined.x * self.inv_w
        obs[7] = self.prev_mined.y * self.inv_h
        obs[8] = min(1.0, sum(self.rover.storage.values()) / (self.mineral_count * 100))

        ranked = self._get_ranked_minerals()
        for i in range(self.mineral_count):
            base = 9 + i * 3
            if i >= len(ranked):
                break
            pos, dist, _ = ranked[i]
            obs[base] = 1.0 if not np.isfinite(dist) else min(1.0, dist / self.max_dist)
            obs[base + 1] = pos.x * self.inv_w
            obs[base + 2] = pos.y * self.inv_h

        return obs

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self._build_world()
        return self._obs(), {}

    def step(self, action):
        prev_battery = self.rover.battery
        prev_distance = self.rover.distance_travelled
        prev_mined_amount = sum(self.rover.storage.values())

        if action == 0:
            self.rover.gear = GEARS.SLOW
        elif action == 1:
            self.rover.gear = GEARS.NORMAL
        elif action == 2:
            self.rover.gear = GEARS.FAST
        elif 3 <= action < 3 + self.mineral_count and self.rover.status == STATUS.IDLE:
            mineral_idx = action - 3
            ranked = self._get_ranked_minerals()
            if mineral_idx < len(ranked):
                target_mineral, _, abs_path = ranked[mineral_idx]
                if abs_path is None:
                    abs_path = self._astar_path(self.rover.pos, target_mineral)
                self._set_rover_path(abs_path)
                if abs_path:
                    self.prev_mined = target_mineral
        elif action == 3 + self.mineral_count and self.rover.status == STATUS.IDLE:
            self.rover.mine()

        self.sim.update(self.delta_hrs)
        self.rover.update(self.delta_hrs)

        mined_now = sum(self.rover.storage.values()) - prev_mined_amount
        if mined_now > 0:
            self._minerals = [m for m in self._minerals if m != self.rover.pos]
            self._invalidate_cache()

        battery_cost = max(0.0, prev_battery - self.rover.battery)
        dist_gain = self.rover.distance_travelled - prev_distance
        minerals_left = len(self._minerals)

        reward = mined_now * 20.0 + (dist_gain * 0.1) - (battery_cost * 0.02) - 0.05

        # Strongly punish idle/no-progress behavior.
        if dist_gain <= 0 and mined_now <= 0:
            self.no_move_streak += 1
            no_move_penalty = min(
                self.NO_MOVE_PENALTY_CAP,
                self.NO_MOVE_PENALTY_BASE + (self.NO_MOVE_PENALTY_STREAK * self.no_move_streak),
            )
            reward -= no_move_penalty
        else:
            self.no_move_streak = 0

        terminated = (self.rover.status == STATUS.DEAD) or (minerals_left == 0) or (not self.sim.is_running)
        if self.rover.status == STATUS.DEAD:
            reward -= 20.0
        if minerals_left == 0:
            reward += 50.0

        return self._obs(), float(reward), terminated, False, {}


def train_model(timesteps: int, out_path: str, cpu_limit: float = 0.9, device: str = "auto"):
    start_time = time.perf_counter()
    model_base = Path(out_path)
    if model_base.suffix == ".zip":
        model_base = model_base.with_suffix("")
    model_zip = model_base.with_suffix(".zip")
    model_pt = model_base.with_suffix(".pt")

    cpu_limit = min(1.0, max(0.01, float(cpu_limit)))
    cpu_budget = max(1, int(round((os.cpu_count() or 1) * cpu_limit)))
    resolved_device = "cuda" if device == "auto" and torch.cuda.is_available() else ("cpu" if device == "auto" else device)
    n_envs = max(1, cpu_budget // 2)
    torch_threads = max(1, cpu_budget // n_envs)
    torch.set_num_threads(torch_threads)

    ts_print(
        "Training setup:"
        f" device={resolved_device}, timesteps={timesteps}, cpu_limit={cpu_limit:.2f},"
        f" cpu_budget={cpu_budget}, n_envs={n_envs}, torch_threads={torch_threads}"
    )

    def make_env():
        return RoverSimpleEnv(mineral_count=1)

    if n_envs > 1 and os.name == "nt":
        ts_print("SubprocVecEnv disabled on Windows for stability; using single env")
        n_envs = 1
        vec_env = DummyVecEnv([make_env])
    elif n_envs > 1:
        try:
            vec_env = SubprocVecEnv([make_env for _ in range(n_envs)])
        except Exception as exc:
            ts_print(f"SubprocVecEnv init failed ({type(exc).__name__}), falling back to single env")
            n_envs = 1
            vec_env = DummyVecEnv([make_env])
    else:
        vec_env = DummyVecEnv([make_env])

    resume = False
    model = None

    if model_zip.exists():
        if model_zip.stat().st_size <= 0:
            ts_print(f"Existing model file is empty ({model_zip}), removing it")
            try:
                model_zip.unlink()
            except OSError:
                pass
        else:
            try:
                ts_print(f"Resuming existing model: {model_zip}")
                model = PPO.load(str(model_zip), env=vec_env, device=resolved_device)
                resume = True
            except Exception as exc:
                ts_print(f"Could not load existing model ({type(exc).__name__}), starting new model")

    if model is None and model_pt.exists() and model_pt.stat().st_size > 0:
        try:
            ts_print(f"Resuming fallback checkpoint: {model_pt}")
            model = PPO("MlpPolicy", vec_env, verbose=0, device=resolved_device)
            checkpoint = torch.load(model_pt, map_location="cpu")
            model.policy.load_state_dict(checkpoint["policy_state_dict"])
            optimizer_state = checkpoint.get("optimizer_state_dict")
            if optimizer_state is not None:
                model.policy.optimizer.load_state_dict(optimizer_state)
            model.num_timesteps = int(checkpoint.get("num_timesteps", 0))
            resume = True
        except Exception as exc:
            ts_print(f"Could not load fallback checkpoint ({type(exc).__name__}), starting new model")

    if model is None:
        ts_print("Starting new PPO model")
        model = PPO("MlpPolicy", vec_env, verbose=0, device=resolved_device)

    log_interval_steps = max(1000, timesteps // 20)
    ts_print(f"Starting PPO learn() with progress interval={log_interval_steps} steps")
    model.learn(
        total_timesteps=timesteps,
        reset_num_timesteps=not resume,
        callback=ProgressCallback(total_timesteps=timesteps, log_interval_steps=log_interval_steps),
    )
    elapsed = time.perf_counter() - start_time
    ts_print(f"Training finished in {elapsed:.1f}s")

    zip_saved = False
    try:
        model.save(str(model_base))
        zip_saved = True
    except RecursionError:
        ts_print("model.save() recursion issue on this Python build, retrying with reduced metadata")
        zip_path = model_base.with_suffix(".zip")
        if zip_path.exists():
            try:
                zip_path.unlink()
            except OSError:
                pass
        try:
            model.save(
                str(model_base),
                exclude=[
                    "policy_class",
                    "observation_space",
                    "action_space",
                    "rollout_buffer_class",
                    "clip_range",
                    "clip_range_vf",
                    "lr_schedule",
                ],
            )
            zip_saved = True
        except Exception as exc:
            ts_print(f"Reduced-metadata zip save failed ({type(exc).__name__}), using .pt fallback")

    checkpoint = {
        "policy_state_dict": model.policy.state_dict(),
        "optimizer_state_dict": model.policy.optimizer.state_dict(),
        "num_timesteps": int(model.num_timesteps),
    }
    torch.save(checkpoint, model_pt)

    vec_env.close()
    if zip_saved:
        ts_print(f"Saved model: {model_base}.zip")
    else:
        ts_print(f"Saved model checkpoint: {model_pt}")

def ask_int(label: str, default: int, min_value: int | None = None, max_value: int | None = None) -> int:
    while True:
        raw = input(f"{label} [{default}]: ").strip()
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError:
            continue
        if min_value is not None and value < min_value:
            continue
        if max_value is not None and value > max_value:
            continue
        return value


def main():
    trained_dir = MARS_ROVER_ROOT / "MachineLearning" / "trained"
    trained_dir.mkdir(parents=True, exist_ok=True)

    timesteps = ask_int("Timesteps limit", 100000, min_value=1)
    model_name = input("Model name [rover_ppo_simple]: ").strip() or "rover_ppo_simple"
    cpu_percent = ask_int("CPU limit (0-100%)", 90, min_value=0, max_value=100)

    model_path = Path(model_name).expanduser()
    if not model_path.is_absolute():
        model_path = trained_dir / model_path

    train_model(
        timesteps=timesteps,
        out_path=str(model_path),
        cpu_limit=max(0.01, cpu_percent / 100.0),
    )

if __name__ == "__main__":
    main()
