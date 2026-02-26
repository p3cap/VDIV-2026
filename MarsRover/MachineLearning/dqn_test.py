"""
Simple DQN rover-like example with 2 input features (state dim=2), 2 outputs (action dim=2), and basic reward.
Uses the dqn_lib for structure.

Environment: Simplified rover on 1D line (position 0-4, start 0, goal 4).
State: [position_norm, battery_norm].
Actions: 0 (wait/charge), 1 (move forward).
Reward: -0.01 per step, +1 at goal, -0.5 if battery low.
Battery drains on move, charges on wait.
"""

import numpy as np
from dqn_lib import DQNAgent, DQNTrainer, BaseDQNEnv, FeatureSpec, ActionSpec
from typing import Optional  

class SimpleRoverEnv(BaseDQNEnv):
    def __init__(self):
        self.steps = 0
        self.max_steps = 20
        self.feature_specs = self._default_feature_specs()
        self.action_specs = self._default_action_specs()
        self.closest_mineral_monitor_amount = 30

    def _default_feature_specs(self):
        return [
            FeatureSpec("input_1", lambda env: env.position / (env.line_length - 1)),  # position_norm
            FeatureSpec("input_2", lambda env: env.battery / env.max_battery),  # battery_norm
        ]

    def _default_action_specs(self):
        return [
            ActionSpec("goto_mineral_index", lambda env: ), 
            ActionSpec("set_gear", lambda env: ), 
            ActionSpec("mine", lambda env:), 

        ]

    def reset(self) -> np.ndarray:
        self.position = 0.0
        self.battery = self.max_battery
        self.steps = 0
        return self._build_state()

    def step(self, action: int) -> tuple[Optional[np.ndarray], float, bool]:
        base_reward = self.action_specs[action].handler(self) if 0 <= action < len(self.action_specs) else -0.5

        self.steps += 1
        done = self.position >= self.line_length - 1 or self.battery <= 0 or self.steps >= self.max_steps

        reward = base_reward
        if self.position >= self.line_length - 1:
            reward += 1.0
        if self.battery <= 0:
            reward -= 0.5

        next_state = None if done else self._build_state()
        return next_state, reward, done


    def _action_move(self) -> float: # retrun score after input?
        if self.battery <= 0:
            return -0.5  # invalid
        return -0.01  # small time penalty

if __name__ == "__main__":
    env = SimpleRoverEnv()
    agent = DQNAgent(state_dim=2, action_dim=2)
    trainer = DQNTrainer(env, agent)

    # Train
    stats = trainer.train(max_episodes=500, verbose=1)

    # Evaluate
    print("Final eval avg reward:", trainer.evaluate(episodes=10))

    # Sample rollout with reward check
    state = env.reset()
    total_reward = 0.0
    done = False
    while not done:
        action = agent.act(state, epsilon=0.0)
        state, reward, done = env.step(action)
        total_reward += reward
        print(f"Action: {action}, Reward: {reward}, State: {state if state is not None else 'Terminal'}")
    print(f"Total reward: {total_reward}")