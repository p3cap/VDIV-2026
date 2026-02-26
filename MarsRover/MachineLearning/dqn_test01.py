from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import torch

# Project paths
ML_DIR = Path(__file__).resolve().parent
ROOT_DIR = ML_DIR.parent

from dqn_lib import DQNAgent, DQNTrainer, BaseDQNEnv, FeatureSpec, ActionSpec
from Global import MARS_ROVER_PATH, Vector2
from MapClass import Map, matrix_from_csv
from RoverClass import GEARS, STATUS, Rover
from Simulation import Simulation

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
    warmup_steps: int = 500
    train_frequency: int = 1
    target_update_freq: int = 500
    min_buffer_size_to_learn: int = 500

@dataclass
class DQNTrainConfig:
    max_episodes: int = 600
    epsilon_start: float = 1.0
    epsilon_final: float = 0.05
    epsilon_decay_steps: int = 50000
    eval_every: int = 0
    eval_episodes: int = 100
    verbose: int = 1

class RoverDQNEnv(BaseDQNEnv):
    minerals = ("B", "Y", "G")

    def __init__(
        self,
        world_cfg: Optional[RoverWorldConfig] = None,
        reward_cfg: Optional[RewardConfig] = None,
    ):
        self.world_cfg = world_cfg or RoverWorldConfig()
        self.reward_cfg = reward_cfg or RewardConfig()
        self.feature_specs = self._default_feature_specs()
        self.action_specs = self._default_action_specs()
        self.reset()

    @property
    def state_dim(self) -> int:
        return len(self.feature_specs)

    @property
    def action_dim(self) -> int:
        return len(self.action_specs)

    def describe_io(self):
        print("State features:")
        for idx, spec in enumerate(self.feature_specs):
            print(f"  [{idx:02d}] {spec.name}")
        print("Actions:")
        for idx, spec in enumerate(self.action_specs):
            print(f"  [{idx:02d}] {spec.name}")

    def _default_feature_specs(self):
        def control_snap(env):
            return env.rover.get_control_snapshot(env.world_cfg.delta_hrs)

        def sim_ctx(env):
            return env.sim.get_context()

        def max_map_dist(env):
            return max(1.0, float(env.map_obj.width + env.map_obj.height))

        return [
            FeatureSpec("rover_x_norm", lambda env: env.rover.pos.x / max(1, env.map_obj.width - 1)),
            FeatureSpec("rover_y_norm", lambda env: env.rover.pos.y / max(1, env.map_obj.height - 1)),
            FeatureSpec("battery_norm", lambda env: control_snap(env)["battery_norm"]),
            FeatureSpec("elapsed_hrs_norm_240", lambda env: sim_ctx(env)["elapsed_hrs"] / 240.0),
            FeatureSpec("run_hrs_norm_240", lambda env: sim_ctx(env)["run_hrs"] / 240.0),
            FeatureSpec("elapsed_ratio", lambda env: sim_ctx(env)["elapsed_hrs"] / max(1.0, sim_ctx(env)["run_hrs"])),
            FeatureSpec("remaining_ratio", lambda env: sim_ctx(env)["remaining_hrs"] / max(1.0, sim_ctx(env)["run_hrs"])),
            FeatureSpec("time_in_cycle_norm", lambda env: sim_ctx(env)["time_in_cycle"] / max(1.0, sim_ctx(env)["cycle_hrs"])),
            FeatureSpec("is_day", lambda env: float(sim_ctx(env)["is_day"])),
            FeatureSpec("gear_index_norm", lambda env: control_snap(env)["gear_index"] / (len(list(GEARS)) - 1)),
            FeatureSpec("gear_value_norm", lambda env: control_snap(env)["gear_value"] / GEARS.FAST.value),
            FeatureSpec("status_idle", lambda env: float(env.rover.status == STATUS.IDLE)),
            FeatureSpec("status_move", lambda env: float(env.rover.status == STATUS.MOVE)),
            FeatureSpec("status_mine", lambda env: float(env.rover.status == STATUS.MINE)),
            FeatureSpec("status_dead", lambda env: float(env.rover.status == STATUS.DEAD)),
            FeatureSpec("path_len_norm", lambda env: len(env.rover.path) / max_map_dist(env)),
            FeatureSpec("move_progress", lambda env: env.rover.move_progress),
            FeatureSpec("mine_process_norm", lambda env: env.rover.mine_process_hrs / max(0.1, env.rover.MINING_TIME_HRS)),
            FeatureSpec("can_mine_now", lambda env: float(env.map_obj.get_tile(env.rover.pos) in env.minerals)),
            FeatureSpec("nearest_B_dist_norm", lambda env: env._nearest_marker_distance("B") / max_map_dist(env)),
            FeatureSpec("nearest_Y_dist_norm", lambda env: env._nearest_marker_distance("Y") / max_map_dist(env)),
            FeatureSpec("nearest_G_dist_norm", lambda env: env._nearest_marker_distance("G") / max_map_dist(env)),
            FeatureSpec("remaining_B_norm", lambda env: env._mineral_count_norm("B")),
            FeatureSpec("remaining_Y_norm", lambda env: env._mineral_count_norm("Y")),
            FeatureSpec("remaining_G_norm", lambda env: env._mineral_count_norm("G")),
            FeatureSpec("remaining_total_norm", lambda env: env._remaining_minerals() / max(1, env.initial_mineral_count)),
            FeatureSpec("move_cost_now_norm", lambda env: env.rover.movement_cost(env.world_cfg.delta_hrs) / env.rover.MAX_BATTERY_CHARGE),
            FeatureSpec("move_cost_slow_norm", lambda env: env.rover.movement_cost_for_gear(env.world_cfg.delta_hrs, GEARS.SLOW) / env.rover.MAX_BATTERY_CHARGE),
            FeatureSpec("move_cost_normal_norm", lambda env: env.rover.movement_cost_for_gear(env.world_cfg.delta_hrs, GEARS.NORMAL) / env.rover.MAX_BATTERY_CHARGE),
            FeatureSpec("move_cost_fast_norm", lambda env: env.rover.movement_cost_for_gear(env.world_cfg.delta_hrs, GEARS.FAST) / env.rover.MAX_BATTERY_CHARGE),
            FeatureSpec("energy_if_idle_norm", lambda env: env.rover.energy_consumed(env.world_cfg.delta_hrs, STATUS.IDLE) / env.rover.MAX_BATTERY_CHARGE),
            FeatureSpec("energy_if_move_norm", lambda env: env.rover.energy_consumed(env.world_cfg.delta_hrs, STATUS.MOVE) / env.rover.MAX_BATTERY_CHARGE),
            FeatureSpec("energy_if_mine_norm", lambda env: env.rover.energy_consumed(env.world_cfg.delta_hrs, STATUS.MINE) / env.rover.MAX_BATTERY_CHARGE),
            FeatureSpec("energy_produced_norm", lambda env: env.rover.energy_produced(env.world_cfg.delta_hrs) / env.rover.MAX_BATTERY_CHARGE),
            FeatureSpec("distance_norm", lambda env: env.rover.distance_travelled / max_map_dist(env)),
        ]

    def _default_action_specs(self):
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

    def _sample_run_hrs(self) -> float:
        if not self.world_cfg.randomize_run_hrs:
            return self.world_cfg.run_hrs
        return np.random.uniform(self.world_cfg.run_hrs_min, self.world_cfg.run_hrs_max)

    def _build_world(self):
        map_obj = Map(map_data=matrix_from_csv(self.world_cfg.map_csv))
        sim = Simulation(map_obj=map_obj, sim_time_multiplier=self.world_cfg.sim_time_multiplier, run_hrs=self._sample_run_hrs(), day_hrs=self.world_cfg.day_hrs, night_hrs=self.world_cfg.night_hrs)
        rover = Rover(id=self.world_cfg.rover_id, sim=sim)
        return map_obj, sim, rover

    def _remaining_minerals(self) -> int:
        return len(self.map_obj.find_tiles(list(self.minerals)))

    def _nearest_marker_distance(self, marker: str) -> float:
        nearest = self.map_obj.nearest_tiles(self.rover.pos, [marker])
        return self.rover.pos.distance_to(nearest) if isinstance(nearest, Vector2) else self._max_map_distance()

    def _mineral_count_norm(self, marker: str) -> float:
        count = len(self.map_obj.find_tiles([marker]))
        return count / self.initial_mineral_count if self.initial_mineral_count > 0 else 0.0

    def _max_map_distance(self) -> float:
        return max(1.0, float(self.map_obj.width + self.map_obj.height))

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
        self.rover.set_gear(gear)
        self._advance_once()
        return -0.01

    def _action_target_marker(self, marker: str) -> float:
        target = self.map_obj.nearest_tiles(self.rover.pos, [marker])
        if not isinstance(target, Vector2):
            self._advance_once()
            return -self.reward_cfg.invalid_action_penalty

        _, path_len = self.rover.astar(self.rover.pos, target)
        if path_len == 0 and self.rover.pos.distance_to(target) > 0:
            self._advance_once()
            return -self.reward_cfg.invalid_action_penalty

        self.rover.path_find_to(target, force=True)
        self._advance_until_not_moving()

        if self.rover.status == STATUS.IDLE:
            self.rover.mine()
            self._advance_until_not_mining()

        return 0.0

    def _action_target_nearest_any(self) -> float:
        target = self.map_obj.nearest_tiles(self.rover.pos, list(self.minerals))
        if not isinstance(target, Vector2):
            self._advance_once()
            return -self.reward_cfg.invalid_action_penalty
        marker = self.map_obj.get_tile(target)
        return self._action_target_marker(marker)

    def _action_mine_current_tile(self) -> float:
        if not self.rover.mine():
            self._advance_once()
            return -self.reward_cfg.invalid_action_penalty
        self._advance_until_not_mining()
        return 0.1

    def _action_wait(self) -> float:
        self._advance_once()
        return -self.reward_cfg.wait_penalty

    def _current_metrics(self) -> dict:
        return {
            "storage_total": sum(self.rover.storage.values()),
            "battery": self.rover.battery,
            "elapsed": self.sim.elapsed_hrs,
            "distance": self.rover.distance_travelled,
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

        return reward

    def _is_terminal(self) -> bool:
        return (
            self.rover.status == STATUS.DEAD
            or not self.sim.is_running
            or self._remaining_minerals() == 0
            or self.steps >= self.world_cfg.max_steps_per_episode
        )

    def reset(self) -> np.ndarray:
        self.map_obj, self.sim, self.rover = self._build_world()
        self.steps = 0
        self.initial_mineral_count = len(self.map_obj.find_tiles(list(self.minerals)))
        return self._build_state()

    def step(self, action: int) -> tuple[Optional[np.ndarray], float, bool]:
        self.steps += 1

        before = self._current_metrics()
        base_reward = -self.reward_cfg.invalid_action_penalty

        if 0 <= action < self.action_dim:
            base_reward = self.action_specs[action].handler(self)
        else:
            self._advance_once()

        after = self._current_metrics()
        reward = self._shape_reward(base_reward, before, after)
        done = self._is_terminal()
        next_state = self._build_state() if not done else None
        return next_state, reward, done

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
        self.env = RoverDQNEnv(self.world_cfg, self.reward_cfg)
        self.agent = DQNAgent(self.env.state_dim, self.env.action_dim, self.model_cfg.lr, self.model_cfg.gamma, hidden_sizes=self.model_cfg.hidden_sizes)
        self.trainer = DQNTrainer(self.env, self.agent, self.model_cfg.buffer_size, self.model_cfg.batch_size, self.model_cfg.warmup_steps, self.model_cfg.train_frequency, self.model_cfg.target_update_freq, self.model_cfg.min_buffer_size_to_learn)
        self.trained_dir = MARS_ROVER_PATH / "MachineLearning" / "trained"

    def _normalize_model_name(self, model_name: str) -> str:
        safe = model_name.strip().replace(" ", "_").removesuffix(".pth")
        return safe or "rover_dqn"

    def model_paths(self, model_name: str) -> tuple[Path, Path]:
        safe = self._normalize_model_name(model_name)
        return self.trained_dir / f"{safe}.pth", self.trained_dir / f"{safe}.ckpt.pt"

    def load_training_state(self, model_name: str) -> int:
        weights_path, checkpoint_path = self.model_paths(model_name)
        episodes_trained = 0
        if checkpoint_path.exists():
            ckpt = torch.load(checkpoint_path, map_location=self.agent.device)
            self.agent.q_net.load_state_dict(ckpt["q_net"])
            self.agent.target_q_net.load_state_dict(ckpt.get("target_q_net", ckpt["q_net"]))
            try:
                self.agent.optimizer.load_state_dict(ckpt["optimizer"])
            except Exception:
                pass
            self.trainer.total_steps = ckpt.get("trainer_total_steps", 0)
            episodes_trained = ckpt.get("episodes_trained", 0)
            print(f"Loaded checkpoint: {checkpoint_path}")
        elif weights_path.exists():
            self.agent.load(str(weights_path))
            print(f"Loaded model weights: {weights_path}")
        else:
            print(f"No existing model found for '{self._normalize_model_name(model_name)}'. Starting new model.")
        return episodes_trained

    def save_training_state(self, model_name: str, episodes_trained: int) -> tuple[Path, Path]:
        weights_path, checkpoint_path = self.model_paths(model_name)
        self.trained_dir.mkdir(parents=True, exist_ok=True)
        self.agent.save(str(weights_path))
        torch.save({
            "q_net": self.agent.q_net.state_dict(),
            "target_q_net": self.agent.target_q_net.state_dict(),
            "optimizer": self.agent.optimizer.state_dict(),
            "trainer_total_steps": self.trainer.total_steps,
            "episodes_trained": episodes_trained,
            "world_cfg": asdict(self.world_cfg),
            "model_cfg": asdict(self.model_cfg),
            "train_cfg": asdict(self.train_cfg),
            "feature_names": [f.name for f in self.env.feature_specs],
            "action_names": [a.name for a in self.env.action_specs],
        }, str(checkpoint_path))
        return weights_path, checkpoint_path

    def train_resume(
        self,
        model_name: str,
        training_minutes: Optional[float] = None,
        chunk_episodes: int = 25,
    ) -> dict:
        episodes_trained = self.load_training_state(model_name)
        start_time = time.time()
        time_limit_seconds = training_minutes * 60 if training_minutes else float('inf')
        has_episode_cap = self.train_cfg.max_episodes > 0
        interrupted = False

        print(f"Training model '{self._normalize_model_name(model_name)}'...")

        try:
            while True:
                if has_episode_cap and episodes_trained >= self.train_cfg.max_episodes:
                    break
                if time.time() - start_time >= time_limit_seconds:
                    break

                episodes_left = self.train_cfg.max_episodes - episodes_trained if has_episode_cap else chunk_episodes
                current_chunk = min(chunk_episodes, episodes_left)

                self.trainer.train(
                    max_episodes=current_chunk,
                    max_steps_per_episode=self.world_cfg.max_steps_per_episode,
                    epsilon_start=self.train_cfg.epsilon_start,
                    epsilon_final=self.train_cfg.epsilon_final,
                    epsilon_decay_steps=self.train_cfg.epsilon_decay_steps,
                    verbose=self.train_cfg.verbose,
                    eval_every=self.train_cfg.eval_every,
                    eval_episodes=self.train_cfg.eval_episodes,
                )

                episodes_trained += current_chunk
        except KeyboardInterrupt:
            interrupted = True
            print("\nTraining interrupted by user. Saving current state...")

        elapsed_minutes = (time.time() - start_time) / 60.0
        weights_path, checkpoint_path = self.save_training_state(model_name, episodes_trained)
        return {
            "model_name": self._normalize_model_name(model_name),
            "episodes_trained": episodes_trained,
            "elapsed_minutes": elapsed_minutes,
            "interrupted": interrupted,
            "weights_path": weights_path,
            "checkpoint_path": checkpoint_path,
        }

    def _fixed_world_cfg(self, run_hrs: float) -> RoverWorldConfig:
        data = asdict(self.world_cfg)
        data.update(run_hrs=run_hrs, run_hrs_min=run_hrs, run_hrs_max=run_hrs, randomize_run_hrs=False)
        return RoverWorldConfig(**data)

    def greedy_rollout(self, run_hrs: Optional[float] = None) -> dict:
        cfg = self.world_cfg if run_hrs is None else self._fixed_world_cfg(run_hrs)
        env = RoverDQNEnv(cfg, self.reward_cfg)
        state = env.reset()
        total_reward = 0.0
        done = False
        while not done:
            action = self.agent.act(state, epsilon=0.0)
            state, reward, done = env.step(action)
            total_reward += reward
        return {
            "reward": total_reward,
            "mined": env.rover.storage,
            "distance": env.rover.distance_travelled,
            "battery": env.rover.battery,
            "elapsed_hrs": env.sim.elapsed_hrs,
            "run_hrs": env.sim.run_hrs,
        }

    def evaluate_run_hrs_sweep(
        self,
        run_hours: Sequence[float] = (24, 48, 72, 96, 120, 144, 168, 192, 216, 240),
    ) -> list[dict]:
        results = []
        for hrs in run_hours:
            result = self.greedy_rollout(hrs)
            results.append(result)
        return results

def _ask_model_name(default_name: str = "rover_dqn") -> str:
    return input(f"Model name [{default_name}]: ").strip() or default_name

def _ask_optional_float(prompt: str) -> Optional[float]:
    raw = input(prompt).strip()
    try:
        return float(raw) if raw else None
    except ValueError:
        return None

def _ask_optional_int(prompt: str, default_value: int) -> int:
    raw = input(prompt).strip()
    try:
        return int(raw) if raw else default_value
    except ValueError:
        return default_value

if __name__ == "__main__":
    experiment = RoverDQNExperiment()
    experiment.env.describe_io()

    model_name = _ask_model_name("rover_dqn")
    training_minutes = _ask_optional_float("Training time in minutes (blank or 0 = no time limit): ")
    experiment.train_cfg.max_episodes = _ask_optional_int(f"Max episodes [{experiment.train_cfg.max_episodes}] (0 = unlimited): ", experiment.train_cfg.max_episodes)
    chunk_episodes = max(1, _ask_optional_int("Save/checkpoint chunk size in episodes [25]: ", 25))

    session = experiment.train_resume(model_name=model_name, training_minutes=training_minutes, chunk_episodes=chunk_episodes)
    print(f"Saved model weights to: {session['weights_path']}")
    print(f"Saved training checkpoint to: {session['checkpoint_path']}")
    print(f"Session summary: episodes={session['episodes_trained']}, elapsed_min={session['elapsed_minutes']:.2f}, interrupted={session['interrupted']}")

    summary = experiment.greedy_rollout()
    print("Greedy rollout finished")
    print(f"Reward: {summary['reward']:.2f}")
    print(f"Mined: {summary['mined']}")
    print(f"Distance: {summary['distance']}")
    print(f"Battery: {summary['battery']:.2f}")
    print(f"Elapsed hrs: {summary['elapsed_hrs']:.2f} / Run hrs: {summary['run_hrs']:.2f}")

    print("Run-hrs sweep (24..240):")
    for result in experiment.evaluate_run_hrs_sweep():
        print(f"  run_hrs={result['run_hrs']:.0f} | reward={result['reward']:.2f} | mined={sum(result['mined'].values())} | battery={result['battery']:.2f} | distance={result['distance']}")