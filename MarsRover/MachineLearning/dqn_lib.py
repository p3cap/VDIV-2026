"""
DQN helper library used by the MarsRover project.

This file provides:
1) A replay buffer for storing transitions.
2) A feed-forward Q-network.
3) A DQN agent with epsilon-greedy action selection.
4) A trainer that runs the train/eval loops.
5) A base environment class for easier customization.

Revised for ease of use:
- Exposed more parameters with sensible default values (based on common optimal settings for DQN).
- Added detailed logging options (e.g., per-step or per-episode details).
- Generalized for multi-step episodes (default max_steps_per_episode=200).
- Added warm-up phase to fill replay buffer with random actions.
- Generalized evaluation to compute average episode reward (instead of binary success).
- Made it flexible for any environment providing reset() -> np.ndarray and step(action) -> (next_state: np.ndarray or None, reward: float, done: bool).
- Environment handles reward logic and simulation logic, making it easy to customize.
- Added docstrings for clarity.
- The library supports unsupervised reinforcement learning, where the agent learns optimal policies from interactions without labeled data.
- Added BaseDQNEnv for easier env implementation with hooks for state features, actions, and rewards.
"""

import random  # Random sampling for replay and epsilon-greedy exploration.
import collections  # Efficient fixed-size queue (deque) for experience replay.
from typing import Optional, Sequence, Tuple, Dict, Any  # Type hints.
import numpy as np  # Numeric array operations for states and mini-batches.
import torch  # PyTorch base package (tensors, devices, serialization).
import torch.nn as nn  # Neural network layers and loss functions.
import torch.optim as optim  # Optimizers (Adam).
from abc import ABC, abstractmethod  # For abstract base class.


class ReplayBuffer:
    """
    Replay buffer stores transitions and returns random mini-batches.
    """
    def __init__(self, capacity: int = 100000):
        """
        :param capacity: Maximum number of transitions to keep (default: 100,000 for good memory efficiency).
        """
        self.capacity = int(capacity)
        self.buffer = collections.deque(maxlen=self.capacity)

    def push(self, state, action, reward, next_state, done):
        """Store one experience tuple: (s, a, r, s', done)."""
        self.buffer.append((state, action, reward, next_state, done))

    def sample(self, batch_size: int):
        """Uniformly sample without replacement from stored experiences."""
        batch = random.sample(self.buffer, batch_size)
        states, actions, rewards, next_states, dones = zip(*batch)
        return (
            np.stack(states),
            np.array(actions),
            np.array(rewards, dtype=np.float32),
            np.stack([ns if ns is not None else np.zeros_like(states[0]) for ns in next_states]),
            np.array(dones, dtype=np.uint8),
        )

    def __len__(self):
        return len(self.buffer)


class QNetwork(nn.Module):
    """
    Simple multi-layer perceptron that predicts Q-values for each action.
    """
    def __init__(self, input_dim: int, output_dim: int, hidden_sizes: Sequence[int] = (128, 128)):
        """
        :param input_dim: Dimension of the state space.
        :param output_dim: Dimension of the action space (number of discrete actions).
        :param hidden_sizes: List of hidden layer sizes (default: [128, 128] for balanced capacity).
        """
        super().__init__()
        layers = []
        last = input_dim
        for h in hidden_sizes:
            layers.append(nn.Linear(last, h))
            layers.append(nn.ReLU())
            last = h
        layers.append(nn.Linear(last, output_dim))
        self.net = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class DQNAgent:
    """
    DQN agent contains behavior and target networks plus optimization logic.
    """
    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        lr: float = 5e-4,
        gamma: float = 0.99,
        device: Optional[str] = None,
        hidden_sizes: Sequence[int] = (128, 128),
    ):
        """
        :param state_dim: Dimension of the state space.
        :param action_dim: Number of discrete actions.
        :param lr: Learning rate for Adam optimizer (default: 5e-4, common for DQN stability).
        :param gamma: Discount factor for future rewards (default: 0.99).
        :param device: Device to use ('cuda' or 'cpu'; auto-detects if None).
        :param hidden_sizes: Hidden layers for Q-network (default: [128, 128]).
        """
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.gamma = gamma

        self.q_net = QNetwork(state_dim, action_dim, hidden_sizes).to(self.device)
        self.target_q_net = QNetwork(state_dim, action_dim, hidden_sizes).to(self.device)
        self.target_q_net.load_state_dict(self.q_net.state_dict())
        self.optimizer = optim.Adam(self.q_net.parameters(), lr=lr)

    def act(self, state: np.ndarray, epsilon: float) -> int:
        """Epsilon-greedy action selection."""
        if random.random() < epsilon:
            return random.randrange(self.action_dim)
        st = torch.FloatTensor(state).unsqueeze(0).to(self.device)
        with torch.no_grad():
            q = self.q_net(st)
            return int(torch.argmax(q, dim=1).item())

    def save(self, path: str):
        """Save online network weights."""
        torch.save(self.q_net.state_dict(), path)

    def load(self, path: str):
        """Load online network weights and sync target."""
        self.q_net.load_state_dict(torch.load(path, map_location=self.device))
        self.target_q_net.load_state_dict(self.q_net.state_dict())

    def update_target(self):
        """Hard update target network."""
        self.target_q_net.load_state_dict(self.q_net.state_dict())

    def learn_from_batch(self, batch, batch_size: int, loss_fn=nn.MSELoss()):
        """Perform one gradient update from a mini-batch."""
        states, actions, rewards, next_states, dones = batch
        states_v = torch.FloatTensor(states).to(self.device)
        next_states_v = torch.FloatTensor(next_states).to(self.device)
        actions_v = torch.LongTensor(actions).to(self.device)
        rewards_v = torch.FloatTensor(rewards).to(self.device)
        dones_v = torch.FloatTensor(dones).to(self.device)

        q_values = self.q_net(states_v)
        q_value = q_values.gather(1, actions_v.unsqueeze(1)).squeeze(1)

        with torch.no_grad():
            next_q_values = self.target_q_net(next_states_v)
            max_next_q = next_q_values.max(1)[0]

        target = rewards_v + (1.0 - dones_v) * self.gamma * max_next_q
        loss = loss_fn(q_value, target)

        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

        return loss.item()


class DQNTrainer:
    """
    Trainer orchestrates environment interaction, replay updates, and evaluation.
    Expected environment API:
    - reset() -> state (np.ndarray)
    - step(action) -> (next_state: np.ndarray or None, reward: float, done: bool)
    """
    def __init__(
        self,
        env,
        agent: DQNAgent,
        buffer_size: int = 100000,
        batch_size: int = 64,
        warmup_steps: int = 1000,
        train_frequency: int = 4,
        target_update_freq: int = 1000,
        min_buffer_size_to_learn: int = 1000,
    ):
        """
        :param env: Environment object (user-provided simulation with reward logic).
        :param agent: DQNAgent instance.
        :param buffer_size: Replay buffer capacity (default: 100,000).
        :param batch_size: Mini-batch size for updates (default: 64).
        :param warmup_steps: Number of random steps to fill buffer before learning (default: 1,000).
        :param train_frequency: Environment steps between gradient updates (default: 4).
        :param target_update_freq: Steps between target network updates (default: 1,000).
        :param min_buffer_size_to_learn: Minimum buffer size to start learning (default: 1,000).
        """
        self.env = env
        self.agent = agent
        self.replay = ReplayBuffer(buffer_size)
        self.batch_size = batch_size
        self.warmup_steps = warmup_steps
        self.train_frequency = train_frequency
        self.target_update_freq = target_update_freq
        self.min_buffer_size_to_learn = min_buffer_size_to_learn
        self.total_steps = 0

    def _store_transition(self, s, a, r, ns, done):
        self.replay.push(s, a, r, ns if ns is not None else None, done)

    def train(
        self,
        max_episodes: int = 2000,
        max_steps_per_episode: int = 200,
        epsilon_start: float = 1.0,
        epsilon_final: float = 0.05,
        epsilon_decay_steps: int = 50000,
        verbose: int = 1,  # 0: silent, 1: episode summaries, 2: per-step details
        eval_every: int = 100,
        eval_episodes: int = 10,
    ):
        """
        Train the agent.
        :param max_episodes: Maximum training episodes (default: 2,000).
        :param max_steps_per_episode: Max steps per episode (default: 200 for multi-step tasks).
        :param epsilon_start: Starting epsilon (default: 1.0).
        :param epsilon_final: Minimum epsilon (default: 0.05).
        :param epsilon_decay_steps: Total steps over which to linearly decay epsilon (default: 50,000).
        :param verbose: Logging level (0: none, 1: episode, 2: step).
        :param eval_every: Evaluate every N episodes (default: 100; 0 to disable).
        :param eval_episodes: Number of episodes for evaluation (default: 10).
        :return: Dict with training stats.
        """
        stats = {"episode": [], "train_avg_reward": [], "eval_avg_reward": []}
        epsilon = epsilon_start

        # Warm-up: Fill buffer with random actions.
        if self.warmup_steps > 0 and verbose >= 1:
            print(f"[Warm-up] Collecting {self.warmup_steps} random transitions...")
        s = self.env.reset()
        for _ in range(self.warmup_steps):
            a = random.randrange(self.agent.action_dim)
            ns, r, done = self.env.step(a)
            self._store_transition(s, a, r, ns, done)
            s = self.env.reset() if done else (ns if ns is not None else s)
            self.total_steps += 1
            if verbose >= 2:
                print(f"  Warm-up step {self.total_steps}: action={a}, reward={r}, done={done}")

        for ep in range(1, max_episodes + 1):
            s = self.env.reset()
            ep_reward = 0.0
            ep_steps = 0
            done = False

            while not done and ep_steps < max_steps_per_episode:
                a = self.agent.act(s, epsilon)
                ns, r, done = self.env.step(a)
                next_state_for_storage = ns if ns is not None else None
                self._store_transition(s, a, r, next_state_for_storage, float(done))
                s = ns if ns is not None else s
                ep_reward += r
                ep_steps += 1
                self.total_steps += 1

                # Linear epsilon decay over total steps.
                epsilon = max(epsilon_final, epsilon_start - (epsilon_start - epsilon_final) * (self.total_steps / epsilon_decay_steps))

                if len(self.replay) >= self.min_buffer_size_to_learn and (self.total_steps % self.train_frequency == 0):
                    batch = self.replay.sample(self.batch_size)
                    loss = self.agent.learn_from_batch(batch, self.batch_size)
                    if verbose >= 2:
                        print(f"  Step {ep_steps} (total {self.total_steps}): action={a}, reward={r}, done={done}, loss={loss:.4f}")

                if self.total_steps % self.target_update_freq == 0:
                    self.agent.update_target()
                    if verbose >= 2:
                        print(f"  Updated target network at step {self.total_steps}")

            if verbose >= 1:
                print(f"[Train] Episode {ep}: reward={ep_reward:.3f}, steps={ep_steps}, epsilon={epsilon:.3f}, buffer_size={len(self.replay)}")

            stats["episode"].append(ep)
            stats["train_avg_reward"].append(ep_reward / max(1, ep_steps))  # Per-step avg for normalization.

            if eval_every > 0 and ep % eval_every == 0:
                eval_reward = self.evaluate(eval_episodes, max_steps_per_episode, verbose)
                stats["eval_avg_reward"].append(eval_reward)
                if verbose >= 1:
                    print(f"  -> Episode {ep} Eval avg reward (over {eval_episodes} episodes): {eval_reward:.3f}")

        return stats

    def evaluate(self, episodes: int = 10, max_steps: int = 200, verbose: int = 1) -> float:
        """
        Evaluate the agent with greedy policy (epsilon=0).
        :return: Average reward per episode.
        """
        total_reward = 0.0
        for ep in range(episodes):
            s = self.env.reset()
            ep_reward = 0.0
            ep_steps = 0
            done = False
            while not done and ep_steps < max_steps:
                a = self.agent.act(s, epsilon=0.0)
                ns, r, done = self.env.step(a)
                s = ns if ns is not None else s
                ep_reward += r
                ep_steps += 1
            total_reward += ep_reward
            if verbose >= 2:
                print(f"  Eval episode {ep + 1}: reward={ep_reward:.3f}, steps={ep_steps}")
        return total_reward / episodes if episodes > 0 else 0.0


class BaseDQNEnv(ABC):
    """
    Base class for DQN environments. Subclass this to define custom envs with easy hooks for features, actions, and rewards.
    """
    @abstractmethod
    def reset(self) -> np.ndarray:
        """Reset the environment and return initial state."""
        pass

    @abstractmethod
    def step(self, action: int) -> Tuple[Optional[np.ndarray], float, bool]:
        """Take an action and return (next_state or None if terminal, reward, done)."""
        pass

    def _default_feature_specs(self) -> list:
        """Override to define default state features."""
        return []

    def _default_action_specs(self) -> list:
        """Override to define default actions."""
        return []

    def _default_reward_cfg(self) -> Dict[str, Any]:
        """Override to define default reward parameters."""
        return {}

    def _build_state(self) -> np.ndarray:
        """Build state from features. Override if needed."""
        return np.array([spec.getter(self) for spec in self.feature_specs], dtype=np.float32)

    def _shape_reward(self, base_reward: float, metrics_delta: Dict[str, float]) -> float:
        """Shape the reward. Override for custom reward logic."""
        return base_reward