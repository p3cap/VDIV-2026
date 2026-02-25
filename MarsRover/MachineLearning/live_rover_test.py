import os
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np

# Resolve imports when launched from project root or MachineLearning folder.
ML_DIR = Path(__file__).resolve().parent
ROOT_DIR = ML_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(ML_DIR) not in sys.path:
    sys.path.insert(0, str(ML_DIR))

from dqn_lib import DQNAgent
from Global import Vector2
from MapClass import Map, matrix_from_csv
from RoverClass import Rover, STATUS, GEARS
from Simulation import Simulation


class RoverDQNController:
    """Uses the trained DQN to pick which mineral type to target next."""

    def __init__(self, rover: Rover, sim: Simulation, model_path: Path):
        self.rover = rover
        self.sim = sim
        self.map_obj = sim.map_obj
        self.minerals = ["B", "Y", "G"]

        # Must match training setup in dqn_rover_test.py
        self.state_dim = 14
        self.action_dim = 3
        self.agent = DQNAgent(
            state_dim=self.state_dim,
            action_dim=self.action_dim,
            lr=5e-4,
            gamma=0.99,
            hidden_sizes=(128, 128),
        )
        self.agent.load(str(model_path))
        self.agent.q_net.eval()

    def nearest_tile(self, marker: str) -> Optional[Vector2]:
        candidates = self.map_obj.get_poses_of_tile(marker)
        if not candidates:
            return None
        return min(candidates, key=lambda p: abs(p.x - self.rover.pos.x) + abs(p.y - self.rover.pos.y))

    def remaining_minerals(self) -> int:
        return sum(len(self.map_obj.get_poses_of_tile(m)) for m in self.minerals)

    def build_state(self) -> np.ndarray:
        width = max(1, self.map_obj.width - 1)
        height = max(1, self.map_obj.height - 1)
        cycle = self.sim.day_hrs + self.sim.night_hrs

        features = [
            self.rover.pos.x / width,
            self.rover.pos.y / height,
            self.rover.battery / self.rover.MAX_BATTERY_CHARGE,
            (self.sim.elapsed_hrs % cycle) / cycle,
            float(self.sim.is_day),
            float(self.rover.status == STATUS.IDLE),
            float(self.rover.status == STATUS.MOVE),
            float(self.rover.status == STATUS.MINE),
        ]

        max_dist = max(1.0, float(self.map_obj.width + self.map_obj.height))
        for marker in self.minerals:
            tile = self.nearest_tile(marker)
            if tile is None:
                features.append(1.0)
                features.append(0.0)
            else:
                dist = abs(tile.x - self.rover.pos.x) + abs(tile.y - self.rover.pos.y)
                features.append(dist / max_dist)
                features.append(1.0)

        return np.array(features, dtype=np.float32)

    def choose_target(self) -> Optional[Vector2]:
        # 1) greedy DQN action
        action = self.agent.act(self.build_state(), epsilon=0.0)

        # 2) preferred mineral
        preferred = self.nearest_tile(self.minerals[action])
        if preferred is not None:
            return preferred

        # 3) fallback if preferred type is exhausted
        for marker in self.minerals:
            fallback = self.nearest_tile(marker)
            if fallback is not None:
                return fallback
        return None


def post_json(url: str, endpoint: str, payload: dict):
    rover.send_log(url)


def advance_world(sim: Simulation, rover: Rover, delta_hrs: float):
    sim.update(delta_hrs)
    # Normalize run-state semantics for live loop.
    sim.is_running = sim.elapsed_hrs < sim.run_hrs
    rover.update(delta_hrs)


if __name__ == "__main__":
    url = "http://127.0.0.1:8000"

    map_obj = Map(map_data=matrix_from_csv(str(ROOT_DIR / "data" / "mars_map_50x50.csv")))

    sim = Simulation(
        map_obj=map_obj,
        sim_time_multiplier=15000,
        run_hrs=240.0,
        day_hrs=16.0,
        night_hrs=8.0,
    )

    rover = Rover(id="dqn_live_rover", sim=sim)
    rover.gear = GEARS.SLOW

    model_path = ROOT_DIR / "MachineLearning" / "trained" / "rover_dqn.pth"
    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")

    controller = RoverDQNController(rover=rover, sim=sim, model_path=model_path)

    setup_data = {
        "day_hrs": sim.day_hrs,
        "night_hrs": sim.night_hrs,
        "run_hrs": sim.run_hrs,
        "sim_time_multiplier": sim.sim_time_multiplier,
        "markers": {
            "S": "Rover Start",
            ".": "Field",
            "#": "Barrier",
            "Y": "Gold",
            "B": "Ice",
            "G": "Green",
        },
        "rover_name": rover.id,
        "rover_max_battery": rover.MAX_BATTERY_CHARGE,
        "rover_mining_consumption_per_hr": rover.MINING_CONSUMPTION_PER_HR,
        "rover_standby_consumption_per_hr": rover.STANDBY_CONSUMPTION_PER_HR,
        "rover_charge_per_hr": rover.DAY_CHARGE_PER_HR,
        "rover_mine_hrs": rover.MINING_TIME_HRS,
        "rover_mode": "machine_learning_dqn_live",
        "map_matrix": map_obj.map_data,
    }
    post_json(url, "/send_setup", setup_data)

    # Set first target immediately.
    first_target = controller.choose_target()
    if first_target is not None:
        rover.path_find_to(first_target)

    last_time = time.perf_counter()
    while True:
        now = time.perf_counter()
        _delta_real = now - last_time
        last_time = now

        delta_hrs = 0.5
        advance_world(sim, rover, delta_hrs)

        if rover.status == STATUS.IDLE:
            rover.mine()
            next_target = controller.choose_target()
            if next_target is not None:
                rover.path_find_to(next_target)

        if os.name == "nt":
            os.system("cls")
        else:
            os.system("clear")

        print(f"frame started with delta_hrs: {delta_hrs}")
        print(rover)

        live_data = {
            "time_of_day": sim.elapsed_hrs % (sim.day_hrs + sim.night_hrs),
            "rover_position": rover.pos._dict(),
            "rover_battery": rover.battery,
            "rover_storage": rover.storage,
            "speed": rover.gear.value,
            "status": rover.status.name,
            "distance_travelled": rover.distance_travelled,
            "mine_process_hrs": rover.mine_process_hrs,
            "path_plan": [v._dict() for v in rover.path],
        }
        post_json(url, "/send_data", live_data)

        if rover.status == STATUS.DEAD:
            print("Rover stopped: battery depleted")
            break
        if not sim.is_running:
            print("Rover stopped: simulation run time reached")
            break
        if controller.remaining_minerals() == 0:
            print("Rover stopped: all minerals mined")
            break

        time.sleep(1)