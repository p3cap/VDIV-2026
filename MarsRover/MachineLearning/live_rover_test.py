import argparse
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import requests
from stable_baselines3 import PPO

MARS_ROVER_ROOT = Path(__file__).parent.parent
sys.path.append(str(MARS_ROVER_ROOT))

from RoverClass import GEARS, STATUS
from Simulation_env import RoverSimulationWorld

ML_ROOT = Path(__file__).parent
GEAR_TO_FLOAT = {GEARS.SLOW: 0.0, GEARS.NORMAL: 0.5, GEARS.FAST: 1.0}


def ts_print(message: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


class LivePolicyEnv:
    """Minimal policy inference wrapper over RoverSimulationWorld."""

    def __init__(
        self,
        run_hrs: float,
        mineral_count: int,
        delta_mode: str,
        set_delta_hrs: float,
        tick_seconds: float,
        env_speed: float,
        base_url: str,
        send_every: int,
    ):
        self.mineral_count = mineral_count
        self.prev_mined = None
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
        self.obs_size = 9 + (self.mineral_count * 3)

    def _ranked_minerals(self):
        rover = self.world.rover
        ranked = []
        for mineral in self.world.minerals():
            _, dist = rover.astar(rover.pos, mineral)
            if dist == 0 and mineral != rover.pos:
                dist = float("inf")
            ranked.append((mineral, float(dist)))
        ranked.sort(key=lambda item: (item[1], item[0].x, item[0].y))
        return ranked[: self.mineral_count]

    def obs(self):
        rover = self.world.rover
        sim = self.world.sim
        obs = np.zeros(self.obs_size, dtype=np.float32)
        cycle = sim.day_hrs + sim.night_hrs
        inv_w = self.world.inv_w
        inv_h = self.world.inv_h

        obs[0] = rover.pos.x * inv_w
        obs[1] = rover.pos.y * inv_h
        obs[2] = rover.battery / rover.MAX_BATTERY_CHARGE
        obs[3] = min(1.0, self.world.run_hrs / 240.0)
        obs[4] = GEAR_TO_FLOAT[rover.gear]
        obs[5] = (sim.elapsed_hrs % cycle) / cycle
        px = self.prev_mined.x if self.prev_mined is not None else 0
        py = self.prev_mined.y if self.prev_mined is not None else 0
        obs[6] = px * inv_w
        obs[7] = py * inv_h
        obs[8] = min(1.0, sum(rover.storage.values()) / (self.mineral_count * 100))

        ranked = self._ranked_minerals()
        for i in range(self.mineral_count):
            base = 9 + (i * 3)
            if i >= len(ranked):
                break
            pos, dist = ranked[i]
            obs[base] = 1.0 if not np.isfinite(dist) else min(1.0, dist / self.world.max_dist)
            obs[base + 1] = pos.x * inv_w
            obs[base + 2] = pos.y * inv_h
        return obs

    def step(self, action: int) -> tuple[bool, float, float]:
        rover = self.world.rover

        if action == 0:
            rover.gear = GEARS.SLOW
        elif action == 1:
            rover.gear = GEARS.NORMAL
        elif action == 2:
            rover.gear = GEARS.FAST
        elif 3 <= action < 3 + self.mineral_count and rover.status == STATUS.IDLE:
            idx = action - 3
            ranked = self._ranked_minerals()
            if idx < len(ranked):
                target, _ = ranked[idx]
                planned = rover.path_find_to(target)
                if planned:
                    self.prev_mined = target
        elif action == 3 + self.mineral_count and rover.status == STATUS.IDLE:
            rover.mine()

        delta_hrs, real_dt_seconds = self.world.step(sleep=True)
        sim = self.world.sim
        done = (rover.status == STATUS.DEAD) or (len(self.world.minerals()) == 0) or (not sim.is_running)
        return done, delta_hrs, real_dt_seconds


def parse_args():
    parser = argparse.ArgumentParser(description="Run trained PPO model as live rover logger.")
    parser.add_argument("--base-url", type=str, default="http://127.0.0.1:8000")
    parser.add_argument("--steps", type=int, default=0)
    parser.add_argument("--delta-mode", type=str, choices=["set_time", "real_time"], default="set_time")
    parser.add_argument("--delta-hrs", type=float, default=0.5, help="Used in set_time mode.")
    parser.add_argument("--tick-seconds", type=float, default=1.0, help="Loop interval in seconds.")
    parser.add_argument("--env-speed", type=float, default=1.0, help="Used in real_time mode.")
    parser.add_argument("--send-every", type=int, default=1)
    parser.add_argument("--run-hrs", type=float, default=24.0)
    parser.add_argument("--deterministic", action="store_true")
    return parser.parse_args()


def choose_model_base() -> str:
    trained_dir = ML_ROOT / "trained"
    models = sorted(trained_dir.glob("*.zip"))
    print("\nAvailable models:")
    for idx, model_file in enumerate(models, start=1):
        print(f"  {idx}. {model_file.stem}")
    print()
    name = input("Model name: ").strip()
    if name.lower().endswith(".zip"):
        name = name[:-4]
    return str(trained_dir / name)


def main():
    args = parse_args()
    model_base = choose_model_base()
    model = PPO.load(model_base)

    obs_size = int(model.observation_space.shape[0])
    mineral_count = max(1, (obs_size - 9) // 3)
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

            action, _ = model.predict(obs, deterministic=args.deterministic)
            done, delta_hrs, real_dt = env.step(int(action))
            obs = env.obs()

            sent_ok = env.world.last_send_ok

            ts_print(
                f"step={step} real_dt={real_dt:.3f}s sim_dt={delta_hrs:.5f}h "
                f"pos=({env.world.rover.pos.x},{env.world.rover.pos.y}) status={env.world.rover.status.name} "
                f"action={int(action)} sent={'ok' if sent_ok else 'failed'}"
            )

            if done or (args.steps > 0 and step >= args.steps):
                break
    finally:
        env.world.close()
        ts_print("logger closed.")


if __name__ == "__main__":
    main()
