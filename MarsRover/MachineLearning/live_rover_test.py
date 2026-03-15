import argparse
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
from stable_baselines3 import PPO
from typing import Optional

MARS_ROVER_ROOT = Path(__file__).parent.parent
sys.path.append(str(MARS_ROVER_ROOT))

from Global import Vector2
from RoverClass import STATUS
from Simulation_env import RoverSimulationWorld
from ppo_shared import (
    OBS_STATIC_FIELDS,
    PER_MINERAL_FIELDS,
    USE_MINERAL_DISTANCE,
    build_obs,
    compute_reward,
    obs_size,
    rank_minerals,
    snap_gear,
)

ML_ROOT = Path(__file__).parent

def ts_print(message: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def _decode_inputs(obs_vec: np.ndarray, env) -> dict:
    """Convert the flattened observation vector back into readable fields."""
    world = env.world
    inv_w = world.inv_w or 1.0
    inv_h = world.inv_h or 1.0
    return {
        "battery_pct": float(np.clip(obs_vec[0], 0.0, 1.0) * 100.0),
        "gear_norm": float(obs_vec[1]),
        "run_hrs": float(obs_vec[2] * 240.0),
        "tod_pct": float(obs_vec[3] * 100.0),
        "rover_x": int(round(obs_vec[4] / inv_w)),
        "rover_y": int(round(obs_vec[5] / inv_h)),
        "prev_mined_x": int(round(obs_vec[6] / inv_w)),
        "prev_mined_y": int(round(obs_vec[7] / inv_h)),
    }


def _decode_outputs(action_vec: np.ndarray, env) -> dict:
    """Human-friendly view of the policy action."""
    world = env.world
    gx_norm = float(np.clip(action_vec[1], 0.0, 1.0))
    gy_norm = float(np.clip(action_vec[2], 0.0, 1.0))
    goto_x = int(np.clip(round(gx_norm * (world.map_width - 1)), 0, world.map_width - 1))
    goto_y = int(np.clip(round(gy_norm * (world.map_height - 1)), 0, world.map_height - 1))
    snapped_gear = snap_gear(action_vec[0])
    return {
        "gear_raw": float(action_vec[0]),
        "gear": snapped_gear.name,
        "goto_x": goto_x,
        "goto_y": goto_y,
        "goto_x_norm": gx_norm,
        "goto_y_norm": gy_norm,
    }


def debug_log(
    step: int,
    input_obs: np.ndarray,
    action_vec: np.ndarray,
    env,
    reward: float,
    mined_now: int,
    dist_gain: float,
    battery_cost: float,
    minerals_left: int,
    is_dead: bool,
    delta_hrs: float,
    real_dt: float,
    sent_ok: bool,
):
    """Structured debugger: raw vectors first, then decoded fields."""
    inputs = _decode_inputs(input_obs, env)
    outputs = _decode_outputs(action_vec, env)

    ts_print(f"[DEBUG] step {step}")
    ts_print(f"  raw input : {np.array2string(input_obs, precision=3, separator=', ')}")
    ts_print(f"  raw output: {np.array2string(action_vec, precision=3, separator=', ')}")
    ts_print("  Inputs:")
    ts_print(f"    rover_x: {inputs['rover_x']}")
    ts_print(f"    rover_y: {inputs['rover_y']}")
    ts_print(f"    prev_mined: ({inputs['prev_mined_x']}, {inputs['prev_mined_y']})")
    ts_print(f"    battery: {inputs['battery_pct']:.1f}%   run_hrs: {inputs['run_hrs']:.1f}h   tod: {inputs['tod_pct']:.1f}%")
    ts_print("  Outputs:")
    ts_print(f"    gear: {outputs['gear']} (raw={outputs['gear_raw']:.3f})")
    ts_print(f"    goto_x: {outputs['goto_x']} (norm={outputs['goto_x_norm']:.3f})")
    ts_print(f"    goto_y: {outputs['goto_y']} (norm={outputs['goto_y_norm']:.3f})")
    ts_print(
        f"  Reward: {reward:.3f} (mined={mined_now}, dist_gain={dist_gain:.2f}, battery_cost={battery_cost:.2f}, minerals_left={minerals_left}, dead={is_dead})"
    )
    ts_print(
        f"  Status: pos=({env.world.rover.pos.x},{env.world.rover.pos.y}) status={env.world.rover.status.name} "
        f"sim_dt={delta_hrs:.5f}h real_dt={real_dt:.3f}s sent={'ok' if sent_ok else 'failed'}"
    )
    print("")  # spacer


class LivePolicyEnv:
    """Minimal policy inference wrapper over RoverSimulationWorld."""

    def __init__(self, run_hrs: float, mineral_count: int, delta_mode: str, set_delta_hrs: float, tick_seconds: float, env_speed: float, base_url: str, send_every: int):
        self.mineral_count = mineral_count
        self.prev_mined = None
        self.total_mined = 0
        self._no_move_streak = 0
        self.world = RoverSimulationWorld(
            run_hrs=run_hrs,
            delta_mode=delta_mode,
            set_delta_hrs=set_delta_hrs,
            tick_seconds=tick_seconds,
            env_speed=env_speed,
            web_logger=True,
            base_url=base_url,
            send_every=send_every,
        )
        self.obs_size = obs_size(self.mineral_count)  # input size
        self._obs_buf = np.zeros(self.obs_size, dtype=np.float32)

    def _ranked_minerals(self): # get mineral distances
        return rank_minerals(self.world, self.mineral_count)

    def obs(self): # NN Inputs
        ranked = self._ranked_minerals()
        return build_obs(
            world=self.world,
            mineral_count=self.mineral_count,
            prev_mined=self.prev_mined,
            mineral_cache=ranked,
            obs_buf=self._obs_buf,
        )

    def step(self, action: np.ndarray) -> tuple[bool, float, float]:
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
                tx = int(np.clip(round(gx * (self.world.map_width - 1)), 0, self.world.map_width - 1))
                ty = int(np.clip(round(gy * (self.world.map_height - 1)), 0, self.world.map_height - 1))
                target = Vector2(tx, ty)
                if target != rover.pos:
                    rover.path_find_to(target)

        before_mined = self.total_mined
        delta_hrs, real_dt_seconds = self.world.step(sleep=True)
        sim = self.world.sim
        self.total_mined = len(rover.mined)
        if self.total_mined > before_mined:
            self.prev_mined = rover.pos

        done = (rover.status == STATUS.DEAD) or (len(self.world.minerals()) == 0) or (not sim.is_running)
        return done, delta_hrs, real_dt_seconds

    def reward(self, mined_now: int, dist_gain: float, battery_cost: float, minerals_left: int, is_dead: bool) -> float:
        reward, self._no_move_streak = compute_reward(
            mined_now=mined_now,
            dist_gain=dist_gain,
            battery_cost=battery_cost,
            minerals_left=minerals_left,
            is_dead=is_dead,
            no_move_streak=self._no_move_streak,
        )
        return reward


def choose_model_base(requested: Optional[str]) -> str:
    trained_dir = ML_ROOT / "trained"
    trained_dir.mkdir(exist_ok=True, parents=True)
    models = sorted(trained_dir.glob("*.zip"))
    latest_hint = trained_dir / "latest_ppo_model.txt"

    def _normalize(name: str) -> str:
        if name.lower().endswith(".zip"):
            name = name[:-4]
        # allow absolute or relative paths outside trained/
        p = Path(name)
        if p.is_absolute() or "\\" in name or "/" in name:
            return str(p.with_suffix(""))
        return str(trained_dir / name)

    if requested:
        return _normalize(requested)

    default = None
    if latest_hint.exists():
        default = latest_hint.read_text(encoding="utf-8").strip()
    elif models:
        default = models[-1].stem
    else:
        default = "rover_ppo_simple"

    if models:
        print("\nAvailable models:")
        for model_file in models:
            print(f"  - {model_file.stem}")

    name = input(f"Model name [{default}]: ").strip() or default
    return _normalize(name)


def infer_mineral_count(model) -> int:
    obs_shape = getattr(model, "observation_space", None)
    if obs_shape is None or not getattr(obs_shape, "shape", None):
        raise ValueError("Model has no observation_space with shape.")
    if len(obs_shape.shape) != 1:
        raise ValueError(f"Unexpected obs shape {obs_shape.shape}; expected 1-D.")
    obs_size = int(obs_shape.shape[0])
    if (obs_size - OBS_STATIC_FIELDS) % PER_MINERAL_FIELDS != 0:
        raise ValueError(
            f"Observation size {obs_size} is not {OBS_STATIC_FIELDS} + "
            f"{PER_MINERAL_FIELDS}*k; cannot infer mineral count (distance flag={USE_MINERAL_DISTANCE})."
        )
    mineral_count = max(1, (obs_size - OBS_STATIC_FIELDS) // PER_MINERAL_FIELDS)

    act_shape = getattr(getattr(model, "action_space", None), "shape", None)
    if act_shape != (3,):
        raise ValueError(f"Model action space shape {act_shape} does not match expected (3,)")

    return mineral_count


def main():
    parser = argparse.ArgumentParser(description="Run a trained PPO policy live.")
    parser.add_argument("--model", type=str, default=None, help="Model base name or path (without .zip).")
    parser.add_argument("--steps", type=int, default=0, help="Max steps to run (0 = infinite).")
    parser.add_argument("--delta-mode", type=str, default="set_time", choices=["set_time", "real_time"])
    parser.add_argument("--delta-hrs", type=float, default=0.5, help="Sim delta hours per step.")
    parser.add_argument("--tick-seconds", type=float, default=1.0, help="Wall time sleep per step.")
    parser.add_argument("--env-speed", type=float, default=1.0, help="Real-time speed multiplier.")
    parser.add_argument("--send-every", type=int, default=1, help="Send websocket data every N steps.")
    parser.add_argument("--run-hrs", type=float, default=240.0, help="Sim run hours per episode.")
    parser.add_argument("--base-url", type=str, default="http://127.0.0.1:8000", help="Backend base URL.")
    parser.add_argument("--deterministic", dest="deterministic", action="store_true", default=True, help="Use deterministic policy actions (default).")
    parser.add_argument("--stochastic", dest="deterministic", action="store_false", help="Use stochastic policy actions.")
    parser.add_argument("--debug", action="store_true", help="Print raw policy inputs/outputs plus decoded fields per step.")
    parser.add_argument("--debug-nn", dest="debug", action="store_true", help=argparse.SUPPRESS)  # legacy alias
    args = parser.parse_args()

    model_base = choose_model_base(args.model)
    ts_print(f"Loading model: {model_base}.zip")
    model = PPO.load(model_base)

    mineral_count = infer_mineral_count(model)
    env = LivePolicyEnv(
        run_hrs=args.run_hrs,
        mineral_count=mineral_count,
        delta_mode=args.delta_mode,
        set_delta_hrs=args.delta_hrs,
        tick_seconds=args.tick_seconds,
        env_speed=args.env_speed,
        base_url=args.base_url,
        send_every=args.send_every,
    )
    obs = env.obs()
    step = 0

    try:
        while True:
            step += 1
            before_battery = env.world.rover.battery
            before_dist = env.world.rover.distance_travelled
            before_mined = len(env.world.rover.mined)
            before_minerals = len(env.world.minerals())

            input_obs = obs.copy()
            action, _ = model.predict(obs, deterministic=args.deterministic)
            done, delta_hrs, real_dt = env.step(action)
            obs = env.obs()
            sent_ok = env.world.last_send_ok

            after_battery = env.world.rover.battery
            after_dist = env.world.rover.distance_travelled
            after_mined = len(env.world.rover.mined)
            after_minerals = len(env.world.minerals())

            mined_now = after_mined - before_mined
            dist_gain = float(after_dist - before_dist)
            battery_cost = max(0.0, before_battery - after_battery)
            minerals_left = after_minerals
            is_dead = env.world.rover.status == STATUS.DEAD

            reward = env.reward(mined_now, dist_gain, battery_cost, minerals_left, is_dead)

            if args.debug:
                debug_log(
                    step=step,
                    input_obs=input_obs,
                    action_vec=action,
                    env=env,
                    reward=reward,
                    mined_now=mined_now,
                    dist_gain=dist_gain,
                    battery_cost=battery_cost,
                    minerals_left=minerals_left,
                    is_dead=is_dead,
                    delta_hrs=delta_hrs,
                    real_dt=real_dt,
                    sent_ok=sent_ok,
                )
            else:
                ts_print(
                    f"step={step} real_dt={real_dt:.3f}s sim_dt={delta_hrs:.5f}h "
                    f"pos=({env.world.rover.pos.x},{env.world.rover.pos.y}) status={env.world.rover.status.name} "
                    f"action={action} sent={'ok' if sent_ok else 'failed'}"
                )

            if done or (args.steps > 0 and step >= args.steps):
                break
    finally:
        env.world.close()
        ts_print("logger closed.")


if __name__ == "__main__":
    main()
