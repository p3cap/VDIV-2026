import random
import sys
from pathlib import Path
from typing import Optional

import numpy as np

from dqn_lib import DQNAgent, DQNTrainer

from Global import Vector2
from MapClass import Map, matrix_from_csv
from RoverClass import Rover, STATUS, GEARS
from Simulation import Simulation


class RoverDQNEnv:
    """
    DQN environment around the rover simulation.

    Action space:
      0 -> target nearest 'B'
      1 -> target nearest 'Y'
      2 -> target nearest 'G'

    One step means:
      - choose a mineral type
      - pathfind to nearest matching tile
      - simulate until rover becomes IDLE again (arrived + mined), or terminal state
    """

    def __init__(self, map_csv: str, run_hrs: float = 24.0, delta_hrs: float = 0.5):
        self.map_csv = map_csv
        self.run_hrs = run_hrs
        self.delta_hrs = delta_hrs
        self.minerals = ["B", "Y", "G"]
        self.max_steps_per_episode = 80
        self.reset()

    def _build_world(self):
        map_obj = Map(map_data=matrix_from_csv(self.map_csv))
        sim = Simulation(
            map_obj=map_obj,
            sim_time_multiplier=15000,
            run_hrs=self.run_hrs,
            day_hrs=16.0,
            night_hrs=8.0,
        )
        rover = Rover(id="dqn_rover", sim=sim)
        rover.gear = GEARS.SLOW
        return map_obj, sim, rover

    def _nearest_tile(self, marker: str) -> Optional[Vector2]:
        candidates = self.map_obj.get_poses_of_tile(marker)
        if not candidates:
            return None
        return min(candidates, key=lambda p: abs(p.x - self.rover.pos.x) + abs(p.y - self.rover.pos.y))

    def _remaining_minerals(self) -> int:
        return sum(len(self.map_obj.get_poses_of_tile(m)) for m in self.minerals)

    def _advance(self):
        """Advance sim+rover one tick and keep run_hrs terminal semantics."""
        self.sim.update(self.delta_hrs)
        # Simulation.update currently flips is_running using `>`; normalize here for RL loop.
        self.sim.is_running = self.sim.elapsed_hrs < self.sim.run_hrs
        self.rover.update(self.delta_hrs)

    def _state(self) -> np.ndarray:
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
            tile = self._nearest_tile(marker)
            if tile is None:
                features.append(1.0)
                features.append(0.0)
            else:
                dist = abs(tile.x - self.rover.pos.x) + abs(tile.y - self.rover.pos.y)
                features.append(dist / max_dist)
                features.append(1.0)

        return np.array(features, dtype=np.float32)

    def reset(self):
        self.map_obj, self.sim, self.rover = self._build_world()
        self.steps = 0
        self.prev_storage_total = 0
        return self._state()

    def step(self, action: int):
        self.steps += 1

        if self.rover.status == STATUS.DEAD or not self.sim.is_running:
            return self._state(), -5.0, True

        marker = self.minerals[action]
        target = self._nearest_tile(marker)

        # Invalid choice (no mineral of requested type).
        if target is None:
            done = self._remaining_minerals() == 0 or self.steps >= self.max_steps_per_episode
            return self._state(), -0.5, done

        # Decide, then execute similarly to main.py loop until rover is idle again.
        if self.rover.status == STATUS.IDLE:
            self.rover.path_find_to(target)

        safety_ticks = 0
        while self.rover.status != STATUS.IDLE and self.rover.status != STATUS.DEAD and self.sim.is_running:
            self._advance()
            safety_ticks += 1
            if safety_ticks > 5000:
                break

        if self.rover.status == STATUS.IDLE:
            self.rover.mine()
            while self.rover.status == STATUS.MINE and self.rover.status != STATUS.DEAD and self.sim.is_running:
                self._advance()
                safety_ticks += 1
                if safety_ticks > 5000:
                    break

        storage_total = sum(self.rover.storage.values())
        mined_now = storage_total - self.prev_storage_total
        self.prev_storage_total = storage_total

        # Reward shaping: prioritize mining, weakly prefer efficiency.
        reward = (2.0 * mined_now) - (0.01 * safety_ticks)

        done = (
            self.rover.status == STATUS.DEAD
            or (not self.sim.is_running)
            or self._remaining_minerals() == 0
            or self.steps >= self.max_steps_per_episode
        )

        if self.rover.status == STATUS.DEAD:
            reward -= 3.0
        if self._remaining_minerals() == 0:
            reward += 5.0

        return self._state(), float(reward), bool(done)


if __name__ == "__main__":
    env = RoverDQNEnv(map_csv=str(ROOT_DIR / "data" / "mars_map_50x50.csv"), run_hrs=24.0, delta_hrs=0.5)

    state_dim = len(env.reset())
    action_dim = 3

    agent = DQNAgent(
        state_dim=state_dim,
        action_dim=action_dim,
        lr=5e-4,
        gamma=0.99,
        hidden_sizes=(128, 128),
    )

    trainer = DQNTrainer(
        env=env,
        agent=agent,
        buffer_size=20000,
        batch_size=128,
        initial_exploration=200,
        train_frequency=1,
        target_update_freq=500,
        min_buffer_size_to_learn=500,
    )

    print("Training rover DQN...")
    trainer.train(
        max_episodes=600,
        max_steps_per_episode=env.max_steps_per_episode,
        epsilon_start=1.0,
        epsilon_final=0.05,
        epsilon_decay=0.995,
        verbose=True,
        eval_every=0,
    )

    out_path = ROOT_DIR / "MachineLearning" / "trained" / "rover_dqn.pth"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    agent.save(str(out_path))
    print(f"Saved rover model to: {out_path}")

    # Greedy test rollout
    test_env = RoverDQNEnv(map_csv=str(ROOT_DIR / "data" / "mars_map_50x50.csv"), run_hrs=24.0, delta_hrs=0.5)
    state = test_env.reset()
    done = False
    total_reward = 0.0

    while not done:
        action = agent.act(state, epsilon=0.0)
        state, reward, done = test_env.step(action)
        total_reward += reward

    print("Test rollout finished")
    print(f"Reward: {total_reward:.2f}")
    print(f"Mined: {test_env.rover.storage}")
    print(f"Distance: {test_env.rover.distance_travelled}")
    print(f"Battery: {test_env.rover.battery:.2f}")
    print(f"Elapsed hrs: {test_env.sim.elapsed_hrs:.2f}")
