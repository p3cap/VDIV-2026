import sys
from datetime import datetime
from pathlib import Path

import numpy as np
from stable_baselines3 import PPO

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
                    planned = rover.path_find_to(target)
                    if planned:
                        self.prev_mined = target

        delta_hrs, real_dt_seconds = self.world.step(sleep=True)
        sim = self.world.sim
        done = (rover.status == STATUS.DEAD) or (len(self.world.minerals()) == 0) or (not sim.is_running)
        return done, delta_hrs, real_dt_seconds


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
    base_url = "http://127.0.0.1:8000"
    steps = 0
    delta_mode = "set_time"
    delta_hrs = 0.5
    tick_seconds = 1.0
    env_speed = 1.0
    send_every = 1
    run_hrs = 240.0
    deterministic = True

    model_base = choose_model_base()
    model = PPO.load(model_base)

    obs_size = int(model.observation_space.shape[0])
    mineral_count = max(1, (obs_size - 8) // 3)
    env = LivePolicyEnv(
        run_hrs=run_hrs,
        mineral_count=mineral_count,
        delta_mode=delta_mode,
        set_delta_hrs=delta_hrs,
        tick_seconds=tick_seconds,
        env_speed=env_speed,
        base_url=base_url,
        send_every=send_every,
    )
    obs = env.obs()
    step = 0

    try:
        while True:
            step += 1

            action, _ = model.predict(obs, deterministic=deterministic)
            done, delta_hrs, real_dt = env.step(action)
            obs = env.obs()
            sent_ok = env.world.last_send_ok

            ts_print(
                f"step={step} real_dt={real_dt:.3f}s sim_dt={delta_hrs:.5f}h "
                f"pos=({env.world.rover.pos.x},{env.world.rover.pos.y}) status={env.world.rover.status.name} "
                f"action={action} sent={'ok' if sent_ok else 'failed'}"
            )

            if done or (steps > 0 and step >= steps):
                break
    finally:
        env.world.close()
        ts_print("logger closed.")


if __name__ == "__main__":
    main()
