import numpy as np
import random
from typing import Tuple, Optional, Sequence
from dqn_lib import DQNTrainer, DQNAgent, ReplayBuffer


# ---------------------------
# Small demo environment: AddEnv (same as yours)
# ---------------------------
class AddEnv:
    """
    Simple one-step environment:
    state: [a/9, b/9] where a,b in 0..9
    action: predicted sum in 0..18
    reward: +1 if correct, -1 otherwise
    """
    def __init__(self):
        self.max_value = 9
        self._state = None

    def reset(self):
        self.a = random.randint(0, self.max_value)
        self.b = random.randint(0, self.max_value)
        self._state = np.array([self.a / 9.0, self.b / 9.0], dtype=np.float32)
        return self._state

    def step(self, action: int) -> Tuple[Optional[np.ndarray], float, bool]:
        correct = (action == (self.a + self.b))
        reward = 1.0 if correct else -1.0
        done = True
        return None, reward, done

# ---------------------------
# Demo script (runs when executed directly)
# ---------------------------
if __name__ == "__main__":
    # Demo: train DQN on AddEnv until 100% eval accuracy or max episodes reached.
    env = AddEnv()
    state_dim = 2
    action_dim = 19

    agent = DQNAgent(state_dim, action_dim, lr=1e-3, gamma=0.99, hidden_sizes=(128, 128))
    trainer = DQNTrainer(
        env,
        agent,
        buffer_size=2000,
        batch_size=128,
        initial_exploration=100,
        train_frequency=1,
        target_update_freq=500,
        min_buffer_size_to_learn=200
    )

    print("Starting training (demo on AddEnv). This may take a bit.")
    stats = trainer.train(
        max_episodes=100000,
        max_steps_per_episode=1,
        epsilon_start=1.0,
        epsilon_final=0.01,
        epsilon_decay=0.995,
        verbose=True,
        eval_every=100,
        eval_episodes=200
    )

    # Save model
    agent.save("dqn_add_demo.pth")
    print("Model saved to dqn_add_demo.pth")

    # Interactive test
    agent.q_net.eval()
    print("\nInteractive test (enter 'q' to quit). Inputs 0..9 only.")
    while True:
        s = input("Enter two ints 0-9 separated by space: ")
        if s.lower().strip() == "q":
            break
        try:
            a_str, b_str = s.strip().split()
            a, b = int(a_str), int(b_str)
            if not (0 <= a <= 9 and 0 <= b <= 9):
                raise ValueError
        except Exception:
            print("Invalid input. Example: '3 7'")
            continue

        state = np.array([a / 9.0, b / 9.0], dtype=np.float32)
        pred = agent.act(state, epsilon=0.0)
        print(f"Predicted: {pred} | Correct: {a + b} | {'OK' if pred == a + b else 'WRONG'}")