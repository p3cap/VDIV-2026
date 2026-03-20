"""
PPO-based ML training for a Mars Rover environment.
Observation (inputs):
  battery, gear, run_hrs, time_left, time_of_day, rover_x, rover_y,
  prev_mined_x, prev_mined_y,
  [dist, x, y] × MINERAL_COUNT closest minerals
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
from typing import Sequence

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
    return_focus_window_hrs,
    snap_gear,
    tile_step_distance,
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
        remaining = (self.total_timesteps - done) / max(1.0, fps) /3600
        print(f"[PPO] {done:>10,}/{self.total_timesteps:,}  ({pct:5.1f}%)"
              f"  elapsed={elapsed:7.1f}s  fps={fps:7.1f}  eta={remaining:7.1f}hrs", flush=True)

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
    RETURN_HOME_MIN_HRS    = 5.0
    RETURN_HOME_MIN_MINED  = 1
    MINERAL_COUNT          = DEFAULT_MINERAL_COUNT

    # obs: [battery, gear, run_hrs, time_left, tod, rx, ry, pmx, pmy] + MINERAL_COUNT×[dist,x,y]
    OBS_SIZE = obs_size(MINERAL_COUNT)

    def __init__(
        self,
        run_hrs: float = 24.0,
        delta_hrs: float = 0.5,
        run_hrs_options: Sequence[float] | None = None,
        delta_mode: str = "set_time",
        tick_seconds: float = 0.0,
        env_speed: float = 1.0,
        map_csv_path: str | None = None,
    ):
        super().__init__()
        self.mineral_count = self.MINERAL_COUNT
        self.run_hrs   = max(24.0, float(run_hrs))
        self.delta_hrs = float(delta_hrs)
        self.delta_mode = str(delta_mode)
        self.tick_seconds = float(tick_seconds)
        self.env_speed = float(env_speed)
        self.map_csv_path = map_csv_path
        if run_hrs_options:
            cleaned = [max(24.0, float(v)) for v in run_hrs_options]
            self.run_hrs_options = [v for v in cleaned if v >= 24.0]
        else:
            self.run_hrs_options = []

        self.world = RoverSimulationWorld(
            run_hrs=self.run_hrs, delta_mode=self.delta_mode,
            set_delta_hrs=self.delta_hrs, tick_seconds=self.tick_seconds,
            env_speed=self.env_speed, web_logger=False,
            map_csv_path=self.map_csv_path,
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
        self._start_pos      = Vector2(0, 0)
        self._no_move_streak = 0
        self._mining_streak  = 0
        self._no_mine_streak = 0
        self._total_mined    = 0
        self._travel_since_mine = 0.0
        self._return_focus      = False
        self._last_delta_hrs = self.delta_hrs
        self._max_home_dist  = max(1.0, float(max(self.map_w - 1, self.map_h - 1)))
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

    def _home_dist(self, rover_pos: Vector2) -> float:
        return float(tile_step_distance(rover_pos, self._start_pos))

    def _return_window_hrs(self, rover_pos: Vector2) -> float:
        return return_focus_window_hrs(
            rover_pos,
            self._start_pos,
            min_window_hrs=self.RETURN_HOME_MIN_HRS,
        )

    def _update_return_focus(self, rover_pos: Vector2, time_left_hrs: float, minerals_left: int | None = None) -> bool:
        if self._return_focus:
            return True
        if minerals_left == 0:
            self._return_focus = True
            return True
        if self._total_mined < self.RETURN_HOME_MIN_MINED:
            return False
        if time_left_hrs <= self._return_window_hrs(rover_pos):
            self._return_focus = True
        return self._return_focus

    # ── reward ────────────────────────────────────────────────────

    def _reward(
        self,
        mined_now: int,
        dist_gain: float,
        battery_cost: float,
        minerals_left: int,
        is_dead: bool,
        travel_since_last_mine: float,
        home_dist_before: float,
        home_dist_after: float,
    ) -> float:
        sim = self.world.sim
        time_left_hrs = max(0.0, float(sim.run_hrs) - float(sim.elapsed_hrs))
        return_window_hrs_value = self._return_window_hrs(self.world.rover.pos)
        is_mining = self.world.rover.status == STATUS.MINE
        reward, self._no_move_streak, self._mining_streak, self._no_mine_streak = compute_reward(
            mined_now=mined_now,
            dist_gain=dist_gain,
            battery_cost=battery_cost,
            minerals_left=minerals_left,
            is_dead=is_dead,
            is_mining=is_mining,
            no_move_streak=self._no_move_streak,
            mining_streak=self._mining_streak,
            no_mine_streak=self._no_mine_streak,
            penalty_base=self.NO_MOVE_PENALTY_BASE,
            penalty_streak=self.NO_MOVE_PENALTY_STREAK,
            penalty_cap=self.NO_MOVE_PENALTY_CAP,
            travel_since_last_mine=travel_since_last_mine,
            return_focus_active=self._return_focus,
            home_dist_before=home_dist_before,
            home_dist_after=home_dist_after,
            time_left_hrs=time_left_hrs,
            return_window_hrs_value=return_window_hrs_value,
            max_home_dist=self._max_home_dist,
        )
        return reward

    # ── gym API ───────────────────────────────────────────────────

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if self.run_hrs_options:
            self.run_hrs = float(np.random.choice(self.run_hrs_options))
            self.world.run_hrs = self.run_hrs
        self.world.reset()
        self._prev_mined     = Vector2(0, 0)
        self._start_pos      = Vector2(self.world.rover.pos.x, self.world.rover.pos.y)
        self._no_move_streak = 0
        self._mining_streak  = 0
        self._no_mine_streak = 0
        self._total_mined    = 0
        self._travel_since_mine = 0.0
        self._return_focus      = False
        self._cycle_hrs      = self.world.sim.day_hrs + self.world.sim.night_hrs
        self._minerals_dirty = True
        self._rebuild_mineral_cache()
        return self._obs(), {}

    def step(self, action: np.ndarray):
        rover = self.world.rover
        sim = self.world.sim

        # gear applies every step
        rover.gear = snap_gear(action[0])
        time_left_before = max(0.0, float(sim.run_hrs) - float(sim.elapsed_hrs))
        self._update_return_focus(rover.pos, time_left_before)
        home_dist_before = self._home_dist(rover.pos)
        travel_since_last_mine = self._travel_since_mine

        # navigation / mining only when rover is free to receive a new command
        if rover.status == STATUS.IDLE:
            tile = self.world.sim.map_obj.get_tile(rover.pos)
            if (not self._return_focus) and tile in self.world.sim.map_obj.mineral_markers:
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

        delta_hrs, _ = self.world.step(sleep=False)
        self._last_delta_hrs = delta_hrs

        self._total_mined = len(rover.mined)
        mined_now = self._total_mined - prev_mined
        dist_gain = float(rover.distance_travelled - prev_dist)
        if mined_now > 0:
            self._prev_mined     = rover.pos
            self._minerals_dirty = True
            self._travel_since_mine = 0.0
        else:
            self._travel_since_mine += dist_gain

        # rebuild mineral cache when minerals changed or rover moved
        if self._minerals_dirty or rover.distance_travelled != prev_dist:
            self._rebuild_mineral_cache()

        battery_cost  = max(0.0, prev_battery - rover.battery)
        minerals_left = len(self._mineral_cache)
        time_left_after = max(0.0, float(sim.run_hrs) - float(sim.elapsed_hrs))
        self._update_return_focus(rover.pos, time_left_after, minerals_left=minerals_left)
        home_dist_after = self._home_dist(rover.pos)
        is_dead       = rover.status == STATUS.DEAD
        terminated    = is_dead or not self.world.sim.is_running or (minerals_left == 0 and home_dist_after <= 0)

        reward = self._reward(
            mined_now,
            dist_gain,
            battery_cost,
            minerals_left,
            is_dead,
            travel_since_last_mine,
            home_dist_before,
            home_dist_after,
        )
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

def build_vec_env(
    n_envs: int,
    run_hrs_options: Sequence[float] | None = None,
    delta_mode: str = "set_time",
    set_delta_hrs: float = 0.5,
    tick_seconds: float = 0.0,
    env_speed: float = 1.0,
    map_csv_path: str | None = None,
):
    make = lambda: RoverEnv(
        run_hrs=run_hrs_options[0] if run_hrs_options else 24.0,
        delta_hrs=set_delta_hrs,
        run_hrs_options=run_hrs_options,
        delta_mode=delta_mode,
        tick_seconds=tick_seconds,
        env_speed=env_speed,
        map_csv_path=map_csv_path,
    )
    return SubprocVecEnv([make] * n_envs) if n_envs > 1 else DummyVecEnv([make])


def train_model(
    timesteps: int,
    out_path: str,
    device: str = "auto",
    cpu_limit: float = 1.0,
    n_envs: int = 0,
    torch_threads: int = 0,
    run_hrs_options: Sequence[float] | None = (24.0, 36.0, 48.0, 72.0),
    delta_mode: str = "set_time",
    set_delta_hrs: float = 0.5,
    tick_seconds: float = 0.0,
    env_speed: float = 1.0,
    map_csv_path: str | None = None,
):
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

    run_hrs_options = list(run_hrs_options or [])
    if run_hrs_options:
        run_hrs_options = [max(24.0, float(v)) for v in run_hrs_options]
    vec_env   = build_vec_env(
        n_envs,
        run_hrs_options=run_hrs_options,
        delta_mode=delta_mode,
        set_delta_hrs=set_delta_hrs,
        tick_seconds=tick_seconds,
        env_speed=env_speed,
        map_csv_path=map_csv_path,
    )
    env_info = RoverEnv(
        run_hrs=run_hrs_options[0] if run_hrs_options else 24.0,
        delta_hrs=set_delta_hrs,
        run_hrs_options=run_hrs_options,
        delta_mode=delta_mode,
        tick_seconds=tick_seconds,
        env_speed=env_speed,
        map_csv_path=map_csv_path,
    )
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
    settings_lines = [
        "# Environment",
        f"run_hrs_options={run_hrs_options}",
        f"run_hrs_min=24.0",
        f"delta_mode={delta_mode}",
        f"set_delta_hrs={set_delta_hrs}",
        f"tick_seconds={tick_seconds}",
        f"env_speed={env_speed}",
        f"map_csv_path={map_csv_path}",
        f"resolved_map_path={env_info.world.map_path}",
        f"map_width={env_info.world.map_width}",
        f"map_height={env_info.world.map_height}",
        f"day_hrs={env_info.world.sim.day_hrs}",
        f"night_hrs={env_info.world.sim.night_hrs}",
        f"mineral_count={RoverEnv.MINERAL_COUNT}",
        f"use_mineral_distance={USE_MINERAL_DISTANCE}",
        f"per_mineral_fields={PER_MINERAL_FIELDS}",
        f"obs_size={obs_size(RoverEnv.MINERAL_COUNT)}",
        f"no_move_penalty_base={RoverEnv.NO_MOVE_PENALTY_BASE}",
        f"no_move_penalty_streak={RoverEnv.NO_MOVE_PENALTY_STREAK}",
        f"no_move_penalty_cap={RoverEnv.NO_MOVE_PENALTY_CAP}",
        f"return_home_min_hours={RoverEnv.RETURN_HOME_MIN_HRS}",
        f"return_home_min_mined={RoverEnv.RETURN_HOME_MIN_MINED}",
        "",
        "# PPO",
        f"timesteps_target={timesteps}",
        f"device={dev}",
        f"n_envs={n_envs}",
        f"torch_threads={torch_threads}",
        f"n_steps={n_steps}",
        f"batch_size={batch_size}",
        f"n_epochs={model.n_epochs}",
        f"gamma={model.gamma}",
        f"gae_lambda={model.gae_lambda}",
        f"clip_range={model.clip_range}",
        f"ent_coef={model.ent_coef}",
        f"vf_coef={model.vf_coef}",
        f"learning_rate={model.learning_rate}",
        f"policy={model.policy.__class__.__name__}",
    ]
    settings_path.write_text("\n".join(settings_lines), encoding="utf-8")
    try:
        env_info.world.close()
    except Exception:
        pass
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
