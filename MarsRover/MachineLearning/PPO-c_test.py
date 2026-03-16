"""
PPO-based ML training for a Mars Rover environment.
Observation (17 inputs):
  battery, gear, run_hrs, time_of_day, rover_x, rover_y,
  prev_mined_x, prev_mined_y,
  [dist, x, y] × MINERAL_COUNT closest minerals (default: 3)
Action (continuous Box, 3 outputs):
  [0] gear   → snapped to {SLOW=0, NORMAL=0.5, FAST=1}
  [1] goto_x → normalised 0-1
  [2] goto_y → normalised 0-1
More info: doc/PPO_machine_learning_doc.md
"""
import os
import sys
import time
from pathlib import Path

MARS_ROVER_ROOT = Path(__file__).parent.parent
sys.path.append(str(MARS_ROVER_ROOT))

import gymnasium as gym
import numpy as np
import torch
from gymnasium import spaces
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv
from Global import Vector2
from RoverClass import STATUS
from Simulation_env import RoverSimulationWorld
from ppo_shared import (
    DEFAULT_MINERAL_COUNT,
    PER_MINERAL_FIELDS,
    USE_MINERAL_DISTANCE,
    build_obs,
    compute_reward,
    obs_size,
    rank_minerals,
    snap_gear,
)


# ─────────────────────────── Callback ────────────────────────────

class MinuteProgressCallback(BaseCallback):
    """Prints a progress line at most once per minute, using a lightweight
    step-count gate to avoid calling perf_counter() on every env step."""

    def __init__(self, total_timesteps: int, log_every_seconds: float = 60.0,
                 check_every_steps: int = 512):
        super().__init__(verbose=0)
        self.total_timesteps   = max(1, int(total_timesteps))
        self.log_every_seconds = float(log_every_seconds)
        self.check_every_steps = max(1, int(check_every_steps))
        self._t0           = 0.0
        self._last_log     = 0.0
        self._steps_start  = 0
        self._next_check   = 0

    def _on_training_start(self) -> None:
        now = time.perf_counter()
        self._t0          = now
        self._last_log    = now
        self._steps_start = int(self.model.num_timesteps)
        self._next_check  = self._steps_start + self.check_every_steps
        print(f"[PPO] Training started — target {self.total_timesteps:,} steps", flush=True)

    def _log(self) -> None:
        elapsed   = max(1e-9, time.perf_counter() - self._t0)
        done      = max(0, int(self.model.num_timesteps) - self._steps_start)
        pct       = min(100.0, done / self.total_timesteps * 100.0)
        fps       = done / elapsed
        remaining = (self.total_timesteps - done) / max(1.0, fps)
        print(f"[PPO] {done:>10,}/{self.total_timesteps:,}  ({pct:5.1f}%)"
              f"  elapsed={elapsed:7.1f}s  fps={fps:7.1f}  eta={remaining:7.1f}s", flush=True)

    def _on_step(self) -> bool:
        # cheap gate: only hit perf_counter every check_every_steps
        if int(self.model.num_timesteps) < self._next_check:
            return True
        self._next_check = int(self.model.num_timesteps) + self.check_every_steps
        now = time.perf_counter()
        if now - self._last_log >= self.log_every_seconds:
            self._log()
            self._last_log = now
        return True

    def _on_training_end(self) -> None:
        self._log()


# ─────────────────────────── Environment ─────────────────────────

class RoverEnv(gym.Env):
    metadata = {"render_modes": []}

    NO_MOVE_PENALTY_BASE   = 6.0
    NO_MOVE_PENALTY_STREAK = 2.0
    NO_MOVE_PENALTY_CAP    = 30.0
    MINERAL_COUNT          = DEFAULT_MINERAL_COUNT

    # obs: [battery, gear, run_hrs, tod, rx, ry, pmx, pmy] + MINERAL_COUNT×[dist,x,y]
    OBS_SIZE = obs_size(MINERAL_COUNT)

    def __init__(self, run_hrs: float = 24.0, delta_hrs: float = 0.5):
        super().__init__()
        self.mineral_count = self.MINERAL_COUNT
        self.run_hrs   = run_hrs
        self.delta_hrs = delta_hrs

        self.world = RoverSimulationWorld(
            run_hrs=run_hrs, delta_mode="set_time",
            set_delta_hrs=delta_hrs, tick_seconds=0.0,
            env_speed=1.0, web_logger=False,
        )
        self.map_w = self.world.map_width
        self.map_h = self.world.map_height

        self.observation_space = spaces.Box(0.0, 1.0, shape=(self.OBS_SIZE,), dtype=np.float32)
        self.action_space      = spaces.Box(
            np.zeros(3, dtype=np.float32), np.ones(3, dtype=np.float32), dtype=np.float32
        )

        self._obs_buf        = np.zeros(self.OBS_SIZE, dtype=np.float32)
        self._cycle_hrs      = self.world.sim.day_hrs + self.world.sim.night_hrs
        self._prev_mined     = Vector2(0, 0)
        self._no_move_streak = 0
        self._mining_streak  = 0
        self._total_mined    = 0
        # mineral cache: list of (Vector2, manhattan_dist)
        self._mineral_cache: list[tuple] = []
        self._minerals_dirty = True

    # ── mineral cache ─────────────────────────────────────────────

    def _rebuild_mineral_cache(self):
        """Manhattan-distance ranking — fast, no A* per step."""
        self._mineral_cache  = rank_minerals(self.world, self.mineral_count)
        self._minerals_dirty = False

    # ── observation ───────────────────────────────────────────────

    def _obs(self) -> np.ndarray:
        return build_obs(
            world=self.world,
            mineral_count=self.mineral_count,
            prev_mined=self._prev_mined,
            mineral_cache=self._mineral_cache,
            obs_buf=self._obs_buf,
        )

    # ── reward ────────────────────────────────────────────────────

    def _reward(self, mined_now: int, dist_gain: float,
                battery_cost: float, minerals_left: int, is_dead: bool) -> float:
        reward, self._no_move_streak, self._mining_streak = compute_reward(
            mined_now=mined_now,
            dist_gain=dist_gain,
            battery_cost=battery_cost,
            minerals_left=minerals_left,
            is_dead=is_dead,
            no_move_streak=self._no_move_streak,
            mining_streak=self._mining_streak,
            penalty_base=self.NO_MOVE_PENALTY_BASE,
            penalty_streak=self.NO_MOVE_PENALTY_STREAK,
            penalty_cap=self.NO_MOVE_PENALTY_CAP,
        )
        return reward

    # ── gym API ───────────────────────────────────────────────────

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self.world.reset()
        self._prev_mined     = Vector2(0, 0)
        self._no_move_streak = 0
        self._mining_streak  = 0
        self._total_mined    = 0
        self._cycle_hrs      = self.world.sim.day_hrs + self.world.sim.night_hrs
        self._minerals_dirty = True
        self._rebuild_mineral_cache()
        return self._obs(), {}

    def step(self, action: np.ndarray):
        rover = self.world.rover

        # gear applies every step
        rover.gear = snap_gear(action[0])

        # navigation / mining only when rover is free to receive a new command
        if rover.status == STATUS.IDLE:
            tile = self.world.sim.map_obj.get_tile(rover.pos)
            if tile in self.world.sim.map_obj.mineral_markers:
                rover.mine()
            else:
                gx = float(np.clip(action[1], 0.0, 1.0))
                gy = float(np.clip(action[2], 0.0, 1.0))
                tx = int(np.clip(round(gx * (self.map_w - 1)), 0, self.map_w - 1))
                ty = int(np.clip(round(gy * (self.map_h - 1)), 0, self.map_h - 1))
                target = Vector2(tx, ty)
                if target != rover.pos:
                    rover.path_find_to(target)

        prev_battery = rover.battery
        prev_dist    = rover.distance_travelled
        prev_mined   = self._total_mined

        self.world.step(sleep=False)

        self._total_mined = len(rover.mined)
        mined_now = self._total_mined - prev_mined
        if mined_now > 0:
            self._prev_mined     = rover.pos
            self._minerals_dirty = True

        # rebuild mineral cache when minerals changed or rover moved
        if self._minerals_dirty or rover.distance_travelled != prev_dist:
            self._rebuild_mineral_cache()

        battery_cost  = max(0.0, prev_battery - rover.battery)
        dist_gain     = float(rover.distance_travelled - prev_dist)
        minerals_left = len(self._mineral_cache)
        is_dead       = rover.status == STATUS.DEAD
        terminated    = is_dead or minerals_left == 0 or not self.world.sim.is_running

        reward = self._reward(mined_now, dist_gain, battery_cost, minerals_left, is_dead)
        return self._obs(), float(reward), terminated, False, {}


# ─────────────────────────── Training helpers ────────────────────

def resolve_device(device: str) -> str:
    if device == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    return device

def tune_torch(device: str) -> None:
    if device != "cuda":
        return
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32       = True
    torch.backends.cudnn.benchmark        = True
    torch.set_float32_matmul_precision("high")

def ppo_batch_params(n_envs: int) -> tuple[int, int]:
    n_steps = 1024
    rollout = n_steps * n_envs
    batch   = min(rollout, 2048)
    while batch > 32 and rollout % batch:
        batch //= 2
    return n_steps, max(32, batch)

def parallelism(device: str, cpu_limit: float, n_envs: int, torch_threads: int):
    budget = max(1, int(round((os.cpu_count() or 1) * min(1.0, max(0.01, cpu_limit)))))
    if n_envs        <= 0: n_envs        = max(1, budget - 1) if device == "cuda" else max(1, int(budget * 0.8))
    if torch_threads <= 0: torch_threads = 1 if device == "cuda" else max(1, budget - n_envs)
    return budget, min(max(1, n_envs), budget), min(max(1, torch_threads), budget)

def build_vec_env(n_envs: int):
    make = lambda: RoverEnv()
    return SubprocVecEnv([make] * n_envs) if n_envs > 1 else DummyVecEnv([make])


def train_model(timesteps: int, out_path: str, device: str = "auto",
                cpu_limit: float = 1.0, n_envs: int = 0, torch_threads: int = 0):
    t0  = time.perf_counter()
    dev = resolve_device(device)
    _, n_envs, torch_threads = parallelism(dev, cpu_limit, n_envs, torch_threads)
    tune_torch(dev)
    n_steps, batch_size = ppo_batch_params(n_envs)

    torch.set_num_threads(torch_threads)
    try:    torch.set_num_interop_threads(max(1, min(4, torch_threads)))
    except RuntimeError: pass

    print(f"[PPO] device={dev}  envs={n_envs}  threads={torch_threads}"
          f"  n_steps={n_steps}  batch={batch_size}  target={timesteps:,}", flush=True)

    vec_env   = build_vec_env(n_envs)
    base_path = Path(out_path).with_suffix("")
    model_zip = base_path.with_suffix(".zip")

    if model_zip.exists() and model_zip.stat().st_size > 0:
        print(f"[PPO] Resuming from {model_zip}", flush=True)
        model = PPO.load(str(model_zip), env=vec_env, device=dev)
        reset_steps = False
    else:
        print("[PPO] Starting fresh model", flush=True)
        model = PPO("MlpPolicy", vec_env, verbose=0, device=dev,
                    n_steps=n_steps, batch_size=batch_size, n_epochs=4)
        reset_steps = True

    # check_every_steps small enough that we never miss a 60s window
    check_steps = max(256, n_envs * 64)
    model.learn(
        total_timesteps=timesteps,
        reset_num_timesteps=reset_steps,
        callback=MinuteProgressCallback(timesteps, log_every_seconds=60.0,
                                        check_every_steps=check_steps),
    )

    model.save(str(base_path))
    settings_path = base_path.with_suffix(".txt")
    settings_path.write_text(
        "\n".join([
            f"mineral_count={RoverEnv.MINERAL_COUNT}",
            f"use_mineral_distance={USE_MINERAL_DISTANCE}",
            f"per_mineral_fields={PER_MINERAL_FIELDS}",
            f"obs_size={obs_size(RoverEnv.MINERAL_COUNT)}",
        ]),
        encoding="utf-8",
    )
    (base_path.parent / "latest_ppo_model.txt").write_text(base_path.name, encoding="utf-8")
    vec_env.close()
    print(f"[PPO] Finished in {time.perf_counter()-t0:.1f}s  →  {base_path}.zip", flush=True)


# ─────────────────────────── Entry point ─────────────────────────

def main():
    trained_dir = MARS_ROVER_ROOT / "MachineLearning" / "trained"
    trained_dir.mkdir(parents=True, exist_ok=True)

    models = sorted(trained_dir.glob("*.zip"))
    if models:
        print("\nAvailable models:")
        for i, m in enumerate(models, 1):
            print(f"  {i}. {m.stem}")

    model_name = input("\nModel name [unnamed]: ").strip() or "unnamed"
    timestamps =  input("\nTimestaps [100_000]: ").strip().replace(" ","") or 100_000
    train_model(
        timesteps=int(timestamps),
        out_path=str(trained_dir / model_name),
        device="cpu"
    )


if __name__ == "__main__":
    main()
