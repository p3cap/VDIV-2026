from __future__ import annotations

import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence

import numpy as np
import torch

# Allow running from project root or from MachineLearning directory.
ML_DIR = Path(__file__).resolve().parent
ROOT_DIR = ML_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(ML_DIR) not in sys.path:
    sys.path.insert(0, str(ML_DIR))

from dqn_lib import DQNAgent, DQNTrainer
from Global import MARS_ROVER_PATH
from MapClass import Map, matrix_from_csv
from RoverClass import GEARS, STATUS, Rover
from Simulation import Simulation


FeatureGetter = Callable[["RoverDQNEnv"], float]
ActionHandler = Callable[["RoverDQNEnv"], float]


@dataclass(frozen=True)
class FeatureSpec:
    """One neural-network input feature."""

    name: str
    getter: FeatureGetter


@dataclass(frozen=True)
class ActionSpec:
    """One discrete neural-network output action."""

    name: str
    handler: ActionHandler


@dataclass
class RoverWorldConfig:
    map_csv: str = str(MARS_ROVER_PATH / "data" / "mars_map_50x50.csv")
    rover_id: str = "dqn_rover"
    run_hrs: float = 24.0
    run_hrs_min: float = 24.0
    run_hrs_max: float = 240.0
    randomize_run_hrs: bool = True
    sim_time_multiplier: float = 15000.0
    day_hrs: float = 16.0
    night_hrs: float = 8.0
    delta_hrs: float = 0.5
    max_steps_per_episode: int = 120
    action_tick_limit: int = 5000


@dataclass
class RewardConfig:
    mined_reward: float = 2.0
    elapsed_time_penalty: float = 0.02
    distance_penalty: float = 0.003
    battery_gain_reward: float = 0.01
    invalid_action_penalty: float = 0.5
    death_penalty: float = 4.0
    completion_bonus: float = 6.0
    wait_penalty: float = 0.03


@dataclass
class DQNModelConfig:
    lr: float = 5e-4
    gamma: float = 0.99
    hidden_sizes: Sequence[int] = (128, 128)
    buffer_size: int = 20000
    batch_size: int = 128
    initial_exploration: int = 200
    train_frequency: int = 1
    target_update_freq: int = 500
    min_buffer_size_to_learn: int = 500


@dataclass
class DQNTrainConfig:
    max_episodes: int = 600
    epsilon_start: float = 1.0
    epsilon_final: float = 0.05
    epsilon_decay: float = 0.995
    eval_every: int = 0
    eval_episodes: int = 100
    verbose: bool = True


class RoverControlAPI:
    """
    Thin facade for explicit rover controls used by the environment.

    This keeps all rover control points in one place and makes action logic easy to read.
    """

    def __init__(self, env: "RoverDQNEnv"):
        self.env = env

    @property
    def rover(self) -> Rover:
        return self.env.rover

    @property
    def sim(self) -> Simulation:
        return self.env.sim

    def set_gear(self, gear) -> GEARS:
        return self.rover.set_gear(gear)

    def movement_cost(self, delta_hrs: float, gear=None) -> float:
        return self.rover.movement_cost_for_gear(delta_hrs, gear)

    def energy_consumed(self, delta_hrs: float, status: Optional[STATUS] = None, gear=None) -> float:
        return self.rover.energy_consumed_for(delta_hrs, status, gear)

    def energy_produced(self, delta_hrs: float) -> float:
        return self.rover.energy_produced(delta_hrs)

    def astar(self, start, goal):
        return self.rover.astar(start, goal)

    def path_find_to(self, goal, force: bool = False):
        return self.rover.path_find_to(goal, force=force)

    def mine(self, force: bool = False) -> bool:
        return self.rover.mine(force=force)


class RoverDQNEnv:
    """
    OOP RL environment for rover control.

    Inputs (NN state) and outputs (NN actions) are defined by `feature_specs` and
    `action_specs`; edit those lists to change the neural interface.
    """

    minerals = ("B", "Y", "G")

    def __init__(
        self,
        world_cfg: RoverWorldConfig,
        reward_cfg: Optional[RewardConfig] = None,
        feature_specs: Optional[Sequence[FeatureSpec]] = None,
        action_specs: Optional[Sequence[ActionSpec]] = None,
    ):
        self.world_cfg = world_cfg
        self.reward_cfg = reward_cfg or RewardConfig()
        self.feature_specs = list(feature_specs) if feature_specs is not None else self._default_feature_specs()
        self.action_specs = list(action_specs) if action_specs is not None else self._default_action_specs()
        self.control = RoverControlAPI(self)
        self.reset()

    @property
    def state_dim(self) -> int:
        return len(self.feature_specs)

    @property
    def action_dim(self) -> int:
        return len(self.action_specs)

    @property
    def max_steps_per_episode(self) -> int:
        return self.world_cfg.max_steps_per_episode

    def describe_io(self):
        print("State features:")
        for idx, spec in enumerate(self.feature_specs):
            print(f"  [{idx:02d}] {spec.name}")
        print("Actions:")
        for idx, spec in enumerate(self.action_specs):
            print(f"  [{idx:02d}] {spec.name}")

    def _sample_run_hrs(self) -> float:
        if not self.world_cfg.randomize_run_hrs:
            return float(self.world_cfg.run_hrs)
        lo = float(min(self.world_cfg.run_hrs_min, self.world_cfg.run_hrs_max))
        hi = float(max(self.world_cfg.run_hrs_min, self.world_cfg.run_hrs_max))
        return float(np.random.uniform(lo, hi))

    def _build_world(self):
        map_obj = Map(map_data=matrix_from_csv(self.world_cfg.map_csv))
        sim = Simulation(
            map_obj=map_obj,
            sim_time_multiplier=self.world_cfg.sim_time_multiplier,
            run_hrs=self._sample_run_hrs(),
            day_hrs=self.world_cfg.day_hrs,
            night_hrs=self.world_cfg.night_hrs,
        )
        rover = Rover(id=self.world_cfg.rover_id, sim=sim)
        rover.set_gear(GEARS.SLOW)
        return map_obj, sim, rover

    def _max_map_distance(self) -> float:
        return max(1.0, float(self.map_obj.width + self.map_obj.height))

    def _remaining_minerals(self) -> int:
        return self.map_obj.count_minerals(self.minerals)

    def _nearest_marker_distance(self, marker: str) -> float:
        nearest = self.map_obj.nearest_tile(self.rover.pos, marker)
        if nearest is None:
            return self._max_map_distance()
        return float(self.map_obj.manhattan_distance(self.rover.pos, nearest))

    def _mineral_count_norm(self, marker: str) -> float:
        if self.initial_mineral_count <= 0:
            return 0.0
        return self.map_obj.count_tiles(marker) / self.initial_mineral_count

    def _advance_once(self):
        self.sim.update(self.world_cfg.delta_hrs)
        if self.sim.is_running:
            self.rover.update(self.world_cfg.delta_hrs)

    def _advance_until_not_moving(self, tick_limit: Optional[int] = None) -> int:
        limit = tick_limit or self.world_cfg.action_tick_limit
        ticks = 0
        while self.rover.status == STATUS.MOVE and self.sim.is_running and ticks < limit:
            self._advance_once()
            ticks += 1
        return ticks

    def _advance_until_not_mining(self, tick_limit: Optional[int] = None) -> int:
        limit = tick_limit or self.world_cfg.action_tick_limit
        ticks = 0
        while self.rover.status == STATUS.MINE and self.sim.is_running and ticks < limit:
            self._advance_once()
            ticks += 1
        return ticks

    def _action_set_gear(self, gear) -> float:
        self.control.set_gear(gear)
        self._advance_once()
        return -0.01

    def _action_target_marker(self, marker: str) -> float:
        target = self.map_obj.nearest_tile(self.rover.pos, marker)
        if target is None:
            self._advance_once()
            return -self.reward_cfg.invalid_action_penalty

        _, path_len = self.control.astar(self.rover.pos, target)
        if path_len == 0 and self.map_obj.manhattan_distance(self.rover.pos, target) > 0:
            self._advance_once()
            return -self.reward_cfg.invalid_action_penalty

        self.control.path_find_to(target, force=True)
        self._advance_until_not_moving()

        if self.rover.status == STATUS.IDLE:
            self.control.mine()
            self._advance_until_not_mining()

        return 0.0

    def _action_target_nearest_any(self) -> float:
        nearest = self.map_obj.nearest_mineral(self.rover.pos, self.minerals)
        if nearest is None:
            self._advance_once()
            return -self.reward_cfg.invalid_action_penalty
        marker, _, _ = nearest
        return self._action_target_marker(marker)

    def _action_mine_current_tile(self) -> float:
        mined = self.control.mine()
        if not mined:
            self._advance_once()
            return -self.reward_cfg.invalid_action_penalty
        self._advance_until_not_mining()
        return 0.1

    def _action_wait(self) -> float:
        self._advance_once()
        return -self.reward_cfg.wait_penalty

    def _default_action_specs(self) -> list[ActionSpec]:
        # Edit this list to change the neural-network output space.
        return [
            ActionSpec("set_gear_slow", lambda env: env._action_set_gear(GEARS.SLOW)),
            ActionSpec("set_gear_normal", lambda env: env._action_set_gear(GEARS.NORMAL)),
            ActionSpec("set_gear_fast", lambda env: env._action_set_gear(GEARS.FAST)),
            ActionSpec("target_nearest_B", lambda env: env._action_target_marker("B")),
            ActionSpec("target_nearest_Y", lambda env: env._action_target_marker("Y")),
            ActionSpec("target_nearest_G", lambda env: env._action_target_marker("G")),
            ActionSpec("target_nearest_any", lambda env: env._action_target_nearest_any()),
            ActionSpec("mine_current_tile", lambda env: env._action_mine_current_tile()),
            ActionSpec("wait", lambda env: env._action_wait()),
        ]

    def _default_feature_specs(self) -> list[FeatureSpec]:
        # Edit this list to change the neural-network input space.
        return [
            FeatureSpec("rover_x_norm", lambda env: env.rover.pos.x / max(1, env.map_obj.width - 1)),
            FeatureSpec("rover_y_norm", lambda env: env.rover.pos.y / max(1, env.map_obj.height - 1)),
            FeatureSpec("battery_norm", lambda env: env.rover.battery / env.rover.MAX_BATTERY_CHARGE),
            FeatureSpec("elapsed_hrs_norm_240", lambda env: env.sim.elapsed_hrs / 240.0),
            FeatureSpec("run_hrs_norm_240", lambda env: env.sim.run_hrs / 240.0),
            FeatureSpec("elapsed_ratio", lambda env: env.sim.elapsed_hrs / max(1.0, env.sim.run_hrs)),
            FeatureSpec("remaining_ratio", lambda env: env.sim.remaining_hrs() / max(1.0, env.sim.run_hrs)),
            FeatureSpec("time_in_cycle_norm", lambda env: env.sim.get_time_in_cycle() / max(1.0, env.sim.get_cycle_hrs())),
            FeatureSpec("is_day", lambda env: float(env.sim.is_day)),
            FeatureSpec("gear_index_norm", lambda env: env.rover.gear_index() / max(1, len(list(GEARS)) - 1)),
            FeatureSpec("gear_value_norm", lambda env: env.rover.gear.value / GEARS.FAST.value),
            FeatureSpec("status_idle", lambda env: float(env.rover.status == STATUS.IDLE)),
            FeatureSpec("status_move", lambda env: float(env.rover.status == STATUS.MOVE)),
            FeatureSpec("status_mine", lambda env: float(env.rover.status == STATUS.MINE)),
            FeatureSpec("status_dead", lambda env: float(env.rover.status == STATUS.DEAD)),
            FeatureSpec("path_len_norm", lambda env: len(env.rover.path) / env._max_map_distance()),
            FeatureSpec("move_progress", lambda env: env.rover.move_progress),
            FeatureSpec("mine_process_norm", lambda env: env.rover.mine_process_hrs / max(0.1, env.rover.MINING_TIME_HRS)),
            FeatureSpec("can_mine_now", lambda env: float(env.rover.can_mine())),
            FeatureSpec(
                "nearest_B_dist_norm",
                lambda env: env._nearest_marker_distance("B") / env._max_map_distance(),
            ),
            FeatureSpec(
                "nearest_Y_dist_norm",
                lambda env: env._nearest_marker_distance("Y") / env._max_map_distance(),
            ),
            FeatureSpec(
                "nearest_G_dist_norm",
                lambda env: env._nearest_marker_distance("G") / env._max_map_distance(),
            ),
            FeatureSpec("remaining_B_norm", lambda env: env._mineral_count_norm("B")),
            FeatureSpec("remaining_Y_norm", lambda env: env._mineral_count_norm("Y")),
            FeatureSpec("remaining_G_norm", lambda env: env._mineral_count_norm("G")),
            FeatureSpec("remaining_total_norm", lambda env: env._remaining_minerals() / max(1, env.initial_mineral_count)),
            FeatureSpec(
                "move_cost_now_norm",
                lambda env: env.control.movement_cost(env.world_cfg.delta_hrs) / env.rover.MAX_BATTERY_CHARGE,
            ),
            FeatureSpec(
                "move_cost_slow_norm",
                lambda env: env.control.movement_cost(env.world_cfg.delta_hrs, GEARS.SLOW) / env.rover.MAX_BATTERY_CHARGE,
            ),
            FeatureSpec(
                "move_cost_normal_norm",
                lambda env: env.control.movement_cost(env.world_cfg.delta_hrs, GEARS.NORMAL) / env.rover.MAX_BATTERY_CHARGE,
            ),
            FeatureSpec(
                "move_cost_fast_norm",
                lambda env: env.control.movement_cost(env.world_cfg.delta_hrs, GEARS.FAST) / env.rover.MAX_BATTERY_CHARGE,
            ),
            FeatureSpec(
                "energy_if_idle_norm",
                lambda env: env.control.energy_consumed(env.world_cfg.delta_hrs, STATUS.IDLE) / env.rover.MAX_BATTERY_CHARGE,
            ),
            FeatureSpec(
                "energy_if_move_norm",
                lambda env: env.control.energy_consumed(env.world_cfg.delta_hrs, STATUS.MOVE, env.rover.gear) / env.rover.MAX_BATTERY_CHARGE,
            ),
            FeatureSpec(
                "energy_if_mine_norm",
                lambda env: env.control.energy_consumed(env.world_cfg.delta_hrs, STATUS.MINE) / env.rover.MAX_BATTERY_CHARGE,
            ),
            FeatureSpec(
                "energy_produced_norm",
                lambda env: env.control.energy_produced(env.world_cfg.delta_hrs) / env.rover.MAX_BATTERY_CHARGE,
            ),
            FeatureSpec("distance_norm", lambda env: env.rover.distance_travelled / env._max_map_distance()),
        ]

    def _build_state(self) -> np.ndarray:
        values = [spec.getter(self) for spec in self.feature_specs]
        return np.array(values, dtype=np.float32)

    def _current_metrics(self) -> dict:
        return {
            "storage_total": float(sum(self.rover.storage.values())),
            "battery": float(self.rover.battery),
            "elapsed": float(self.sim.elapsed_hrs),
            "distance": float(self.rover.distance_travelled),
        }

    def _shape_reward(self, base_reward: float, before: dict, after: dict) -> float:
        mined_delta = after["storage_total"] - before["storage_total"]
        elapsed_delta = after["elapsed"] - before["elapsed"]
        distance_delta = after["distance"] - before["distance"]
        battery_delta = after["battery"] - before["battery"]

        reward = base_reward
        reward += self.reward_cfg.mined_reward * mined_delta
        reward -= self.reward_cfg.elapsed_time_penalty * elapsed_delta
        reward -= self.reward_cfg.distance_penalty * distance_delta
        reward += self.reward_cfg.battery_gain_reward * battery_delta

        if self.rover.status == STATUS.DEAD:
            reward -= self.reward_cfg.death_penalty
        if self._remaining_minerals() == 0:
            reward += self.reward_cfg.completion_bonus

        return float(reward)

    def _is_terminal(self) -> bool:
        return bool(
            self.rover.status == STATUS.DEAD
            or (not self.sim.is_running)
            or self._remaining_minerals() == 0
            or self.steps >= self.max_steps_per_episode
        )

    def reset(self):
        self.map_obj, self.sim, self.rover = self._build_world()
        self.steps = 0
        self.initial_mineral_count = self.map_obj.count_minerals(self.minerals)
        return self._build_state()

    def step(self, action: int):
        self.steps += 1

        if self._is_terminal():
            return self._build_state(), -5.0, True

        before = self._current_metrics()
        base_reward = -self.reward_cfg.invalid_action_penalty

        idx = int(action)
        if 0 <= idx < self.action_dim:
            base_reward = self.action_specs[idx].handler(self)
        else:
            self._advance_once()

        after = self._current_metrics()
        reward = self._shape_reward(base_reward, before, after)
        done = self._is_terminal()
        return self._build_state(), reward, done


class RoverDQNExperiment:
    def __init__(
        self,
        world_cfg: Optional[RoverWorldConfig] = None,
        reward_cfg: Optional[RewardConfig] = None,
        model_cfg: Optional[DQNModelConfig] = None,
        train_cfg: Optional[DQNTrainConfig] = None,
    ):
        self.world_cfg = world_cfg or RoverWorldConfig()
        self.reward_cfg = reward_cfg or RewardConfig()
        self.model_cfg = model_cfg or DQNModelConfig()
        self.train_cfg = train_cfg or DQNTrainConfig()

        self.env = RoverDQNEnv(world_cfg=self.world_cfg, reward_cfg=self.reward_cfg)
        self.agent = DQNAgent(
            state_dim=self.env.state_dim,
            action_dim=self.env.action_dim,
            lr=self.model_cfg.lr,
            gamma=self.model_cfg.gamma,
            hidden_sizes=self.model_cfg.hidden_sizes,
        )
        self.trainer = DQNTrainer(
            env=self.env,
            agent=self.agent,
            buffer_size=self.model_cfg.buffer_size,
            batch_size=self.model_cfg.batch_size,
            initial_exploration=self.model_cfg.initial_exploration,
            train_frequency=self.model_cfg.train_frequency,
            target_update_freq=self.model_cfg.target_update_freq,
            min_buffer_size_to_learn=self.model_cfg.min_buffer_size_to_learn,
        )

    @property
    def trained_dir(self) -> Path:
        return MARS_ROVER_PATH / "MachineLearning" / "trained"

    def _normalize_model_name(self, model_name: str) -> str:
        safe = (model_name or "").strip().replace(" ", "_")
        if safe.endswith(".pth"):
            safe = safe[:-4]
        if not safe:
            safe = "rover_dqn"
        return safe

    def model_paths(self, model_name: str) -> tuple[Path, Path]:
        safe_name = self._normalize_model_name(model_name)
        weights_path = self.trained_dir / f"{safe_name}.pth"
        checkpoint_path = self.trained_dir / f"{safe_name}.ckpt.pt"
        return weights_path, checkpoint_path

    def load_training_state(self, model_name: str) -> tuple[str, float, int]:
        safe_name = self._normalize_model_name(model_name)
        weights_path, checkpoint_path = self.model_paths(safe_name)
        epsilon = self.train_cfg.epsilon_start
        episodes_trained = 0

        if checkpoint_path.exists():
            checkpoint = torch.load(str(checkpoint_path), map_location=self.agent.device)
            if isinstance(checkpoint, dict) and "q_net" in checkpoint:
                self.agent.q_net.load_state_dict(checkpoint["q_net"])
                if "target_q_net" in checkpoint:
                    self.agent.target_q_net.load_state_dict(checkpoint["target_q_net"])
                else:
                    self.agent.target_q_net.load_state_dict(self.agent.q_net.state_dict())

                if "optimizer" in checkpoint:
                    try:
                        self.agent.optimizer.load_state_dict(checkpoint["optimizer"])
                    except Exception:
                        # If optimizer state is incompatible, continue with fresh optimizer state.
                        pass

                self.trainer.total_steps = int(checkpoint.get("trainer_total_steps", 0))
                epsilon = float(checkpoint.get("epsilon", self.train_cfg.epsilon_start))
                episodes_trained = int(checkpoint.get("episodes_trained", 0))
                print(f"Loaded checkpoint: {checkpoint_path}")
                return safe_name, epsilon, episodes_trained

        if weights_path.exists():
            self.agent.load(str(weights_path))
            print(f"Loaded model weights: {weights_path}")
        else:
            print(f"No existing model found for '{safe_name}'. Starting new model.")

        return safe_name, epsilon, episodes_trained

    def save_training_state(self, model_name: str, epsilon: float, episodes_trained: int) -> tuple[Path, Path]:
        weights_path, checkpoint_path = self.model_paths(model_name)
        self.trained_dir.mkdir(parents=True, exist_ok=True)

        # Keep a plain weights file for inference compatibility.
        self.agent.save(str(weights_path))

        checkpoint = {
            "q_net": self.agent.q_net.state_dict(),
            "target_q_net": self.agent.target_q_net.state_dict(),
            "optimizer": self.agent.optimizer.state_dict(),
            "trainer_total_steps": int(self.trainer.total_steps),
            "epsilon": float(epsilon),
            "episodes_trained": int(episodes_trained),
            "world_cfg": asdict(self.world_cfg),
            "model_cfg": asdict(self.model_cfg),
            "train_cfg": asdict(self.train_cfg),
            "feature_names": [f.name for f in self.env.feature_specs],
            "action_names": [a.name for a in self.env.action_specs],
        }
        torch.save(checkpoint, str(checkpoint_path))
        return weights_path, checkpoint_path

    def train_resume(
        self,
        model_name: str,
        training_minutes: Optional[float] = None,
        chunk_episodes: int = 25,
    ) -> dict:
        safe_name, epsilon, episodes_trained = self.load_training_state(model_name)
        start_time = time.time()
        time_limit_seconds = None if training_minutes is None or training_minutes <= 0 else training_minutes * 60.0
        has_episode_cap = self.train_cfg.max_episodes > 0
        interrupted = False

        print(f"Training model '{safe_name}'...")
        try:
            while True:
                if has_episode_cap and episodes_trained >= self.train_cfg.max_episodes:
                    break
                if time_limit_seconds is not None and (time.time() - start_time) >= time_limit_seconds:
                    break

                if has_episode_cap:
                    episodes_left = self.train_cfg.max_episodes - episodes_trained
                    current_chunk = max(1, min(chunk_episodes, episodes_left))
                else:
                    current_chunk = max(1, chunk_episodes)

                self.trainer.train(
                    max_episodes=current_chunk,
                    max_steps_per_episode=self.env.max_steps_per_episode,
                    epsilon_start=epsilon,
                    epsilon_final=self.train_cfg.epsilon_final,
                    epsilon_decay=self.train_cfg.epsilon_decay,
                    verbose=self.train_cfg.verbose,
                    eval_every=0,
                    eval_episodes=self.train_cfg.eval_episodes,
                )

                episodes_trained += current_chunk
                epsilon = max(
                    self.train_cfg.epsilon_final,
                    epsilon * (self.train_cfg.epsilon_decay ** current_chunk),
                )
        except KeyboardInterrupt:
            interrupted = True
            print("\nTraining interrupted by user. Saving current state...")

        elapsed_minutes = (time.time() - start_time) / 60.0
        weights_path, checkpoint_path = self.save_training_state(
            safe_name,
            epsilon=epsilon,
            episodes_trained=episodes_trained,
        )
        return {
            "model_name": safe_name,
            "episodes_trained": episodes_trained,
            "epsilon": epsilon,
            "elapsed_minutes": elapsed_minutes,
            "interrupted": interrupted,
            "weights_path": weights_path,
            "checkpoint_path": checkpoint_path,
        }

    def _fixed_world_cfg(self, run_hrs: float) -> RoverWorldConfig:
        data = asdict(self.world_cfg)
        data.update(
            {
                "run_hrs": float(run_hrs),
                "run_hrs_min": float(run_hrs),
                "run_hrs_max": float(run_hrs),
                "randomize_run_hrs": False,
            }
        )
        return RoverWorldConfig(**data)

    def greedy_rollout(self, run_hrs: Optional[float] = None) -> dict:
        eval_world_cfg = self.world_cfg if run_hrs is None else self._fixed_world_cfg(run_hrs)
        env = RoverDQNEnv(
            world_cfg=eval_world_cfg,
            reward_cfg=self.reward_cfg,
            feature_specs=self.env.feature_specs,
            action_specs=self.env.action_specs,
        )
        state = env.reset()
        done = False
        total_reward = 0.0

        while not done:
            action = self.agent.act(state, epsilon=0.0)
            state, reward, done = env.step(action)
            total_reward += reward

        return {
            "reward": float(total_reward),
            "mined": dict(env.rover.storage),
            "distance": int(env.rover.distance_travelled),
            "battery": float(env.rover.battery),
            "elapsed_hrs": float(env.sim.elapsed_hrs),
            "run_hrs": float(env.sim.run_hrs),
        }

    def evaluate_run_hrs_sweep(
        self,
        run_hours: Sequence[float] = (24, 48, 72, 96, 120, 144, 168, 192, 216, 240),
    ) -> list[dict]:
        results = []
        for hrs in run_hours:
            result = self.greedy_rollout(run_hrs=float(hrs))
            results.append(result)
        return results


def _ask_model_name(default_name: str = "rover_dqn") -> str:
    raw = input(f"Model name [{default_name}]: ").strip()
    return raw or default_name


def _ask_optional_float(prompt: str) -> Optional[float]:
    raw = input(prompt).strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _ask_optional_int(prompt: str, default_value: int) -> int:
    raw = input(prompt).strip()
    if not raw:
        return default_value
    try:
        return int(raw)
    except ValueError:
        return default_value


if __name__ == "__main__":
    experiment = RoverDQNExperiment()
    experiment.env.describe_io()

    model_name = _ask_model_name("rover_dqn")
    training_minutes = _ask_optional_float(
        "Training time in minutes (blank or 0 = no time limit): "
    )
    experiment.train_cfg.max_episodes = _ask_optional_int(
        f"Max episodes [{experiment.train_cfg.max_episodes}] (0 = unlimited): ",
        experiment.train_cfg.max_episodes,
    )
    chunk_episodes = max(
        1,
        _ask_optional_int("Save/checkpoint chunk size in episodes [25]: ", 25),
    )

    session = experiment.train_resume(
        model_name=model_name,
        training_minutes=training_minutes,
        chunk_episodes=chunk_episodes,
    )
    print(f"Saved model weights to: {session['weights_path']}")
    print(f"Saved training checkpoint to: {session['checkpoint_path']}")
    print(
        f"Session summary: episodes={session['episodes_trained']}, "
        f"epsilon={session['epsilon']:.4f}, elapsed_min={session['elapsed_minutes']:.2f}, "
        f"interrupted={session['interrupted']}"
    )

    summary = experiment.greedy_rollout()
    print("Greedy rollout finished")
    print(f"Reward: {summary['reward']:.2f}")
    print(f"Mined: {summary['mined']}")
    print(f"Distance: {summary['distance']}")
    print(f"Battery: {summary['battery']:.2f}")
    print(f"Elapsed hrs: {summary['elapsed_hrs']:.2f} / Run hrs: {summary['run_hrs']:.2f}")

    print("Run-hrs sweep (24..240):")
    for result in experiment.evaluate_run_hrs_sweep():
        print(
            f"  run_hrs={result['run_hrs']:.0f} | reward={result['reward']:.2f} | "
            f"mined={sum(result['mined'].values())} | battery={result['battery']:.2f} | "
            f"distance={result['distance']}"
        )
