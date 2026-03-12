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
from RoverClass import GEARS, STATUS
from Simulation_env import RoverSimulationWorld

ML_ROOT = Path(__file__).parent
GEAR_TO_FLOAT = {GEARS.SLOW: 0.0, GEARS.NORMAL: 0.5, GEARS.FAST: 1.0}
FLOAT_TO_GEAR = {0.0: GEARS.SLOW, 0.5: GEARS.NORMAL, 1.0: GEARS.FAST}


def snap_gear(value: float) -> GEARS:
    snapped = min([0.0, 0.5, 1.0], key=lambda g: abs(g - float(value)))
    return FLOAT_TO_GEAR[snapped]


def ts_print(message: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


class LivePolicyEnv:
    """Minimal policy inference wrapper over RoverSimulationWorld."""

    def __init__(self, run_hrs: float, mineral_count: int, delta_mode: str, set_delta_hrs: float, tick_seconds: float, env_speed: float, base_url: str, send_every: int):
        self.mineral_count = mineral_count
        self.prev_mined = None
        self.total_mined = 0
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
        self.obs_size = 8 + (self.mineral_count * 3) # input size

    def _ranked_minerals(self): # get mineral distances
        rover = self.world.rover
        minerals = list(self.world.minerals())
        if not minerals:
            return []
        rx, ry = rover.pos.x, rover.pos.y
        ranked = sorted(minerals, key=lambda m: abs(m.x - rx) + abs(m.y - ry))
        return [(m, float(abs(m.x - rx) + abs(m.y - ry))) for m in ranked[:self.mineral_count]]

    def obs(self): # NN Inputs
        rover = self.world.rover
        sim = self.world.sim
        obs = np.zeros(self.obs_size, dtype=np.float32)
        cycle = sim.day_hrs + sim.night_hrs
        inv_w = self.world.inv_w
        inv_h = self.world.inv_h

        obs[0] = rover.battery / rover.MAX_BATTERY_CHARGE
        obs[1] = GEAR_TO_FLOAT[rover.gear]
        obs[2] = min(1.0, self.world.run_hrs / 240.0)
        obs[3] = (sim.elapsed_hrs % cycle) / cycle
        obs[4] = rover.pos.x * inv_w
        obs[5] = rover.pos.y * inv_h
        px = self.prev_mined.x if self.prev_mined is not None else 0
        py = self.prev_mined.y if self.prev_mined is not None else 0
        obs[6] = px * inv_w
        obs[7] = py * inv_h

        ranked = self._ranked_minerals()
        max_d = float(self.world.map_width + self.world.map_height)
        for i in range(self.mineral_count):
            base = 8 + i * 3
            if i >= len(ranked):
                break
            pos, dist = ranked[i]
            obs[base] = min(1.0, dist / max_d)
            obs[base + 1] = pos.x * inv_w
            obs[base + 2] = pos.y * inv_h
        return obs

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
    if (obs_size - 8) % 3 != 0:
        raise ValueError(f"Observation size {obs_size} is not 8 + 3*k; cannot infer mineral count.")
    mineral_count = max(1, (obs_size - 8) // 3)

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
    parser.add_argument("--debug-nn", action="store_true", help="Print NN inputs, outputs, and reward per step.")
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

    no_move_streak = 0

    try:
        while True:
            step += 1
            before_battery = env.world.rover.battery
            before_dist = env.world.rover.distance_travelled
            before_mined = len(env.world.rover.mined)
            before_minerals = len(env.world.minerals())

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

            reward = mined_now * 20.0 + dist_gain * 0.1 - battery_cost * 0.02 - 0.05
            if dist_gain <= 0 and mined_now <= 0:
                no_move_streak += 1
                penalty = min(8.0, 2.0 + 0.5 * no_move_streak)
                reward -= penalty
            else:
                no_move_streak = 0
            if is_dead:
                reward -= 200.0
            if minerals_left == 0:
                reward += 50.0

            ts_print(
                f"step={step} real_dt={real_dt:.3f}s sim_dt={delta_hrs:.5f}h "
                f"pos=({env.world.rover.pos.x},{env.world.rover.pos.y}) status={env.world.rover.status.name} "
                f"action={action} sent={'ok' if sent_ok else 'failed'}"
            )

            if args.debug_nn:
                ts_print(
                    "  nn_input="
                    + np.array2string(obs, precision=3, separator=", ")
                    + f" | reward={reward:.3f} (mined={mined_now}, dist_gain={dist_gain:.1f}, battery_cost={battery_cost:.2f}, minerals_left={minerals_left}, dead={is_dead})"
                )

            if done or (args.steps > 0 and step >= args.steps):
                break
    finally:
        env.world.close()
        ts_print("logger closed.")


if __name__ == "__main__":
    main()
