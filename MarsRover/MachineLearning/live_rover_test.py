import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np
import torch

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
from RoverLogger import RoverLogger
from Simulation import Simulation


LEGACY_FEATURES_14 = [
    "rover_x_norm",
    "rover_y_norm",
    "battery_norm",
    "time_in_cycle_norm",
    "is_day",
    "status_idle",
    "status_move",
    "status_mine",
    "nearest_B_dist_norm",
    "has_B",
    "nearest_Y_dist_norm",
    "has_Y",
    "nearest_G_dist_norm",
    "has_G",
]

MODERN_FEATURES_35 = [
    "rover_x_norm",
    "rover_y_norm",
    "battery_norm",
    "elapsed_hrs_norm_240",
    "run_hrs_norm_240",
    "elapsed_ratio",
    "remaining_ratio",
    "time_in_cycle_norm",
    "is_day",
    "gear_index_norm",
    "gear_value_norm",
    "status_idle",
    "status_move",
    "status_mine",
    "status_dead",
    "path_len_norm",
    "move_progress",
    "mine_process_norm",
    "can_mine_now",
    "nearest_B_dist_norm",
    "nearest_Y_dist_norm",
    "nearest_G_dist_norm",
    "remaining_B_norm",
    "remaining_Y_norm",
    "remaining_G_norm",
    "remaining_total_norm",
    "move_cost_now_norm",
    "move_cost_slow_norm",
    "move_cost_normal_norm",
    "move_cost_fast_norm",
    "energy_if_idle_norm",
    "energy_if_move_norm",
    "energy_if_mine_norm",
    "energy_produced_norm",
    "distance_norm",
]

LEGACY_ACTIONS_3 = [
    "target_nearest_B",
    "target_nearest_Y",
    "target_nearest_G",
]

MODERN_ACTIONS_9 = [
    "set_gear_slow",
    "set_gear_normal",
    "set_gear_fast",
    "target_nearest_B",
    "target_nearest_Y",
    "target_nearest_G",
    "target_nearest_any",
    "mine_current_tile",
    "wait",
]


def _load_model_blob(model_path: Path):
    blob = torch.load(str(model_path), map_location="cpu")
    if isinstance(blob, dict) and "q_net" in blob:
        return blob["q_net"], blob
    return blob, {}


def _infer_network_shape(state_dict: dict):
    linear_layers = []
    for key, tensor in state_dict.items():
        m = re.match(r"net\.(\d+)\.weight$", key)
        if m and getattr(tensor, "ndim", 0) == 2:
            linear_layers.append((int(m.group(1)), tensor))

    if not linear_layers:
        raise RuntimeError("Could not infer network shape from state_dict.")

    linear_layers.sort(key=lambda x: x[0])
    first_w = linear_layers[0][1]
    last_w = linear_layers[-1][1]

    input_dim = int(first_w.shape[1])
    hidden_sizes = tuple(int(w.shape[0]) for _, w in linear_layers[:-1])
    output_dim = int(last_w.shape[0])
    return input_dim, output_dim, hidden_sizes


def _select_feature_names(input_dim: int, metadata: dict):
    names = metadata.get("feature_names")
    if isinstance(names, list) and len(names) == input_dim:
        return names
    if input_dim == 14:
        return LEGACY_FEATURES_14
    if input_dim == 35:
        return MODERN_FEATURES_35
    raise ValueError(
        f"Unsupported model input_dim={input_dim}. "
        "Use a checkpoint with feature_names metadata or a known architecture (14 or 35)."
    )


def _select_action_names(output_dim: int, metadata: dict):
    names = metadata.get("action_names")
    if isinstance(names, list) and len(names) == output_dim:
        return names
    if output_dim == 3:
        return LEGACY_ACTIONS_3
    if output_dim == 9:
        return MODERN_ACTIONS_9
    raise ValueError(
        f"Unsupported model output_dim={output_dim}. "
        "Use a checkpoint with action_names metadata or a known architecture (3 or 9)."
    )


class RoverDQNController:
    """Live DQN controller that supports both legacy and modern model schemas."""

    def __init__(self, rover: Rover, sim: Simulation, model_path: Path, delta_hrs: float = 0.5):
        self.rover = rover
        self.sim = sim
        self.map_obj = sim.map_obj
        self.delta_hrs = delta_hrs
        self.minerals = ["B", "Y", "G"]
        self.initial_mineral_count = max(1, self.map_obj.count_minerals(self.minerals))
        self.pending_mine_after_arrival = False
        self.last_action_name = "none"

        state_dict, metadata = _load_model_blob(model_path)
        state_dim, action_dim, hidden_sizes = _infer_network_shape(state_dict)

        self.feature_names = _select_feature_names(state_dim, metadata)
        self.action_names = _select_action_names(action_dim, metadata)

        self.agent = DQNAgent(
            state_dim=state_dim,
            action_dim=action_dim,
            lr=5e-4,
            gamma=0.99,
            hidden_sizes=hidden_sizes,
        )
        self.agent.q_net.load_state_dict(state_dict)
        self.agent.target_q_net.load_state_dict(self.agent.q_net.state_dict())
        self.agent.q_net.eval()

        print(
            f"Loaded model '{model_path.name}' | state_dim={state_dim}, "
            f"action_dim={action_dim}, hidden={hidden_sizes}"
        )

    def nearest_tile(self, marker: str) -> Optional[Vector2]:
        return self.map_obj.nearest_tile(self.rover.pos, marker)

    def remaining_minerals(self) -> int:
        return self.map_obj.count_minerals(self.minerals)

    def _max_map_distance(self) -> float:
        return max(1.0, float(self.map_obj.width + self.map_obj.height))

    def _nearest_marker_distance(self, marker: str) -> float:
        tile = self.nearest_tile(marker)
        if tile is None:
            return self._max_map_distance()
        return float(self.map_obj.manhattan_distance(self.rover.pos, tile))

    def _mineral_count_norm(self, marker: str) -> float:
        return self.map_obj.count_tiles(marker) / self.initial_mineral_count

    def _feature_value_map(self) -> dict:
        cycle = self.sim.get_cycle_hrs()
        max_dist = self._max_map_distance()

        return {
            "rover_x_norm": self.rover.pos.x / max(1, self.map_obj.width - 1),
            "rover_y_norm": self.rover.pos.y / max(1, self.map_obj.height - 1),
            "battery_norm": self.rover.battery / self.rover.MAX_BATTERY_CHARGE,
            "elapsed_hrs_norm_240": self.sim.elapsed_hrs / 240.0,
            "run_hrs_norm_240": self.sim.run_hrs / 240.0,
            "elapsed_ratio": self.sim.elapsed_hrs / max(1.0, self.sim.run_hrs),
            "remaining_ratio": self.sim.remaining_hrs() / max(1.0, self.sim.run_hrs),
            "time_in_cycle_norm": self.sim.get_time_in_cycle() / max(1.0, cycle),
            "is_day": float(self.sim.is_day),
            "gear_index_norm": self.rover.gear_index() / max(1, len(list(GEARS)) - 1),
            "gear_value_norm": self.rover.gear.value / GEARS.FAST.value,
            "status_idle": float(self.rover.status == STATUS.IDLE),
            "status_move": float(self.rover.status == STATUS.MOVE),
            "status_mine": float(self.rover.status == STATUS.MINE),
            "status_dead": float(self.rover.status == STATUS.DEAD),
            "path_len_norm": len(self.rover.path) / max_dist,
            "move_progress": self.rover.move_progress,
            "mine_process_norm": self.rover.mine_process_hrs / max(0.1, self.rover.MINING_TIME_HRS),
            "can_mine_now": float(self.rover.can_mine()),
            "nearest_B_dist_norm": self._nearest_marker_distance("B") / max_dist,
            "nearest_Y_dist_norm": self._nearest_marker_distance("Y") / max_dist,
            "nearest_G_dist_norm": self._nearest_marker_distance("G") / max_dist,
            "has_B": float(self.map_obj.count_tiles("B") > 0),
            "has_Y": float(self.map_obj.count_tiles("Y") > 0),
            "has_G": float(self.map_obj.count_tiles("G") > 0),
            "remaining_B_norm": self._mineral_count_norm("B"),
            "remaining_Y_norm": self._mineral_count_norm("Y"),
            "remaining_G_norm": self._mineral_count_norm("G"),
            "remaining_total_norm": self.remaining_minerals() / self.initial_mineral_count,
            "move_cost_now_norm": self.rover.movement_cost_for_gear(self.delta_hrs) / self.rover.MAX_BATTERY_CHARGE,
            "move_cost_slow_norm": self.rover.movement_cost_for_gear(self.delta_hrs, GEARS.SLOW) / self.rover.MAX_BATTERY_CHARGE,
            "move_cost_normal_norm": self.rover.movement_cost_for_gear(self.delta_hrs, GEARS.NORMAL) / self.rover.MAX_BATTERY_CHARGE,
            "move_cost_fast_norm": self.rover.movement_cost_for_gear(self.delta_hrs, GEARS.FAST) / self.rover.MAX_BATTERY_CHARGE,
            "energy_if_idle_norm": self.rover.energy_consumed_for(self.delta_hrs, STATUS.IDLE) / self.rover.MAX_BATTERY_CHARGE,
            "energy_if_move_norm": self.rover.energy_consumed_for(self.delta_hrs, STATUS.MOVE, self.rover.gear) / self.rover.MAX_BATTERY_CHARGE,
            "energy_if_mine_norm": self.rover.energy_consumed_for(self.delta_hrs, STATUS.MINE) / self.rover.MAX_BATTERY_CHARGE,
            "energy_produced_norm": self.rover.energy_produced(self.delta_hrs) / self.rover.MAX_BATTERY_CHARGE,
            "distance_norm": self.rover.distance_travelled / max_dist,
        }

    def build_state(self) -> np.ndarray:
        values = self._feature_value_map()
        try:
            features = [values[name] for name in self.feature_names]
        except KeyError as e:
            raise KeyError(f"Unknown feature in model schema: {e}") from e
        return np.array(features, dtype=np.float32)

    def _plan_to_marker(self, marker: str) -> bool:
        target = self.nearest_tile(marker)
        if target is None:
            return False

        if self.rover.pos == target:
            mined = self.rover.mine()
            self.pending_mine_after_arrival = not mined
            return mined

        path = self.rover.path_find_to(target)
        if path:
            self.pending_mine_after_arrival = True
            return True
        return False

    def _plan_to_nearest_any(self) -> bool:
        nearest = self.map_obj.nearest_mineral(self.rover.pos, self.minerals)
        if nearest is None:
            return False
        marker, _, _ = nearest
        return self._plan_to_marker(marker)

    def _execute_action(self, action_idx: int):
        if action_idx < 0 or action_idx >= len(self.action_names):
            self.last_action_name = "invalid_action"
            return

        action_name = self.action_names[action_idx]
        self.last_action_name = action_name

        if action_name == "set_gear_slow":
            self.rover.set_gear(GEARS.SLOW)
            return
        if action_name == "set_gear_normal":
            self.rover.set_gear(GEARS.NORMAL)
            return
        if action_name == "set_gear_fast":
            self.rover.set_gear(GEARS.FAST)
            return

        if action_name == "target_nearest_B":
            self._plan_to_marker("B")
            return
        if action_name == "target_nearest_Y":
            self._plan_to_marker("Y")
            return
        if action_name == "target_nearest_G":
            self._plan_to_marker("G")
            return
        if action_name == "target_nearest_any":
            self._plan_to_nearest_any()
            return
        if action_name == "mine_current_tile":
            self.rover.mine()
            return
        if action_name == "wait":
            return

        # Fallback for unknown custom action names:
        # if first 3 actions behave like legacy target selectors, preserve behavior.
        if len(self.action_names) >= 3 and action_idx in (0, 1, 2):
            self._plan_to_marker(self.minerals[action_idx])
            return

    def on_idle(self):
        # When we arrive after a target action, mine automatically.
        if self.pending_mine_after_arrival and self.rover.can_mine():
            self.rover.mine()
            self.pending_mine_after_arrival = False
            self.last_action_name = "auto_mine_after_arrival"
            return

        if self.pending_mine_after_arrival and not self.rover.can_mine():
            self.pending_mine_after_arrival = False

        action = self.agent.act(self.build_state(), epsilon=0.0)
        self._execute_action(action)


def advance_world(sim: Simulation, rover: Rover, delta_hrs: float):
    sim.update(delta_hrs)
    sim.is_running = sim.elapsed_hrs < sim.run_hrs
    if sim.is_running:
        rover.update(delta_hrs)


def resolve_model_path(trained_dir: Path, model_name: str) -> Path:
    ckpt = trained_dir / f"{model_name}.ckpt.pt"
    pth = trained_dir / f"{model_name}.pth"
    if ckpt.exists():
        return ckpt
    if pth.exists():
        return pth
    raise FileNotFoundError(f"Model not found. Checked: {ckpt} and {pth}")


if __name__ == "__main__":
    url = "http://127.0.0.1:8000"
    delta_hrs = 0.5

    map_obj = Map(map_data=matrix_from_csv(str(ROOT_DIR / "data" / "mars_map_50x50.csv")))

    sim = Simulation(
        map_obj=map_obj,
        sim_time_multiplier=15000,
        run_hrs=240.0,
        day_hrs=16.0,
        night_hrs=8.0,
    )

    rover = Rover(id="dqn_live_rover", sim=sim)
    rover.set_gear(GEARS.SLOW)
    logger = RoverLogger(url)

    model_name = (input("Model name [rover_dqn]: ").strip() or "rover_dqn")
    model_path = resolve_model_path(ROOT_DIR / "MachineLearning" / "trained", model_name)
    controller = RoverDQNController(rover=rover, sim=sim, model_path=model_path, delta_hrs=delta_hrs)

    setup_data = {
        "day_hrs": sim.day_hrs,
        "night_hrs": sim.night_hrs,
        "run_hrs": sim.run_hrs,
        "sim_time_multiplier": sim.sim_time_multiplier,
        "markers": map_obj.marker_descriptions,
        "rover_name": rover.id,
        "rover_max_battery": rover.MAX_BATTERY_CHARGE,
        "rover_mining_consumption_per_hr": rover.MINING_CONSUMPTION_PER_HR,
        "rover_standby_consumption_per_hr": rover.STANDBY_CONSUMPTION_PER_HR,
        "rover_charge_per_hr": rover.DAY_CHARGE_PER_HR,
        "rover_mine_hrs": rover.MINING_TIME_HRS,
        "rover_mode": "machine_learning_dqn_live",
        "map_matrix": map_obj.map_data,
    }

    # First decision.
    if rover.status == STATUS.IDLE:
        controller.on_idle()

    last_time = time.perf_counter()
    while True:
        now = time.perf_counter()
        _delta_real = now - last_time
        last_time = now

        advance_world(sim, rover, delta_hrs)

        if rover.status == STATUS.IDLE:
            controller.on_idle()

        if os.name == "nt":
            os.system("cls")
        else:
            os.system("clear")

        print(f"frame started with delta_hrs: {delta_hrs}")
        print(f"model: {model_path.name} | action: {controller.last_action_name}")
        print(rover)
        print(sim)

        live_data = {
            "time_of_day": sim.elapsed_hrs % (sim.day_hrs + sim.night_hrs),
            "elapsed_hrs": sim.elapsed_hrs,
            "rover_position": rover.pos._dict(),
            "rover_battery": rover.battery,
            "rover_storage": rover.storage,
            "speed": rover.gear.value,
            "status": rover.status.name,
            "distance_travelled": rover.distance_travelled,
            "mine_process_hrs": rover.mine_process_hrs,
            "path_plan": [v._dict() for v in rover.path],
            "remaining_minerals": controller.remaining_minerals(),
            "action_name": controller.last_action_name,
        }
        logger.send_live(live_data)
        logger.send_setup(setup_data)

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
